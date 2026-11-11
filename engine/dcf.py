"""dcf.py: unlevered free-cash-flow valuation.

Model, in order:
  1. Revenue grows at `growth_start` for `high_growth_years`, then fades
     linearly to `growth_terminal` by the final explicit year.
  2. EBIT margin moves linearly from `margin_start` to `margin_target` over
     `margin_converge_years`, then holds.
  3. FCFF = EBIT x (1 - tax) + D&A - capex - change in net working capital.
     D&A is a share of revenue and working capital investment a share of the
     change in revenue. Capex follows the same shape as growth: it holds at
     `capex_pct` through the high-growth years and then fades linearly to
     `capex_pct_terminal`, because growth capex is not needed once growth
     slows.
  4. Continuing value uses the value-driver formula
        TV = NOPAT_(n+1) x (1 - g / RONIC) / (WACC - g)
     so terminal growth has to be paid for with reinvestment.
  5. Mid-year convention: explicit flows are discounted at t - 0.5 and the
     Gordon terminal value is grossed up by (1 + WACC)^0.5 so that it is
     consistent with mid-year flows after the horizon.
  6. Enterprise value is bridged to equity, then rolled forward from the
     balance-sheet date to the valuation date at the cost of equity, net of
     dividends paid in between.

`run_dcf` takes a flat assumptions dict so the browser engine can mirror it
exactly and both can be compared number for number.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from . import fin

REQUIRED_KEYS = (
    "n_years", "base_revenue", "growth_start", "growth_terminal", "high_growth_years",
    "margin_start", "margin_target", "margin_converge_years", "tax_rate",
    "da_pct", "capex_pct", "capex_pct_terminal", "nwc_pct", "wacc", "terminal_ronic", "ronic_tied",
    "mid_year", "cash", "lt_investments", "debt", "minority", "shares",
    "cost_equity", "years_since_fye", "dividends_since_fye",
)


def fade_path(n_years: int, start: float, terminal: float, hold_years: int) -> List[float]:
    """Hold `start` for `hold_years`, then move linearly so the final explicit
    year sits exactly at `terminal`."""
    if n_years < 1:
        raise ValueError("n_years must be at least 1")
    h = max(0, min(int(hold_years), n_years - 1))
    path = []
    for t in range(1, n_years + 1):
        if t <= h:
            path.append(start)
        else:
            path.append(start + (terminal - start) * (t - h) / (n_years - h))
    return path


def growth_path(n_years: int, growth_start: float, growth_terminal: float,
                high_growth_years: int) -> List[float]:
    """Revenue growth: high-growth years, then a linear fade to terminal growth."""
    return fade_path(n_years, growth_start, growth_terminal, high_growth_years)


def capex_path(n_years: int, capex_pct: float, capex_pct_terminal: float,
               high_growth_years: int) -> List[float]:
    """Capex as a share of revenue, fading on the same schedule as growth."""
    return fade_path(n_years, capex_pct, capex_pct_terminal, high_growth_years)


def margin_path(n_years: int, margin_start: float, margin_target: float,
                converge_years: int) -> List[float]:
    """Linear convergence from the starting margin to the target margin."""
    k = max(1, int(converge_years))
    return [margin_start + (margin_target - margin_start) * min(t, k) / k
            for t in range(1, n_years + 1)]


def project_fcff(base_revenue: float, growth: Sequence[float], ebit_margin: Sequence[float],
                 tax_rate: float, da_pct: float, capex_pct: Sequence[float],
                 nwc_pct: float) -> List[Dict[str, float]]:
    """Year-by-year operating forecast and free cash flow to the firm."""
    if not len(growth) == len(ebit_margin) == len(capex_pct):
        raise ValueError("growth, margin and capex paths must have equal length")
    rows = []
    prev_revenue = base_revenue
    for t, (g, m, cx) in enumerate(zip(growth, ebit_margin, capex_pct), start=1):
        revenue = prev_revenue * (1.0 + g)
        ebit = revenue * m
        nopat = ebit * (1.0 - tax_rate)
        da = revenue * da_pct
        capex = revenue * cx
        delta_nwc = nwc_pct * (revenue - prev_revenue)
        fcff = nopat + da - capex - delta_nwc
        rows.append({
            "year": t, "growth": g, "revenue": revenue, "ebit_margin": m, "ebit": ebit,
            "ebitda": ebit + da, "nopat": nopat, "da": da, "capex": capex,
            "delta_nwc": delta_nwc, "fcff": fcff,
        })
        prev_revenue = revenue
    return rows


def terminal_value(nopat_final: float, growth_terminal: float, wacc: float, ronic: float) -> Dict[str, float]:
    """Value-driver continuing value at the end of the final explicit year."""
    if wacc <= growth_terminal:
        raise ValueError("WACC must exceed terminal growth")
    if ronic <= 0:
        raise ValueError("RONIC must be positive")
    if growth_terminal < 0:
        raise ValueError("terminal growth must be non-negative")
    nopat_next = nopat_final * (1.0 + growth_terminal)
    reinvestment_rate = growth_terminal / ronic
    fcff_next = nopat_next * (1.0 - reinvestment_rate)
    return {
        "nopat_next": nopat_next,
        "reinvestment_rate": reinvestment_rate,
        "fcff_next": fcff_next,
        "value": fcff_next / (wacc - growth_terminal),
    }


def enterprise_value(fcff: Sequence[float], tv: float, wacc: float, mid_year: bool = True) -> Dict[str, float]:
    """Discount explicit flows and the terminal value to time zero."""
    n = len(fcff)
    shift = 0.5 if mid_year else 0.0
    factors = [(1.0 + wacc) ** -(t - shift) for t in range(1, n + 1)]
    pv_flows = [cf * df for cf, df in zip(fcff, factors)]
    pv_explicit = sum(pv_flows)
    pv_tv = tv * (1.0 + wacc) ** -n * ((1.0 + wacc) ** 0.5 if mid_year else 1.0)
    ev = pv_explicit + pv_tv
    return {
        "discount_factors": factors,
        "pv_flows": pv_flows,
        "pv_explicit": pv_explicit,
        "pv_terminal": pv_tv,
        "enterprise_value": ev,
        "terminal_share": pv_tv / ev if ev != 0 else float("nan"),
    }


def equity_bridge(enterprise_val: float, cash: float, lt_investments: float, debt: float,
                  minority: float, shares: float) -> Dict[str, float]:
    """Enterprise value to equity value per share.

    Cash and short-term investments and long-term financial investments are
    non-operating assets (their income is excluded from EBIT), so both are
    added back; debt (including leases) and minority interests are deducted.
    """
    if shares <= 0:
        raise ValueError("shares must be positive")
    equity = enterprise_val + cash + lt_investments - debt - minority
    return {"equity_value": equity, "per_share": equity / shares}


def roll_forward(value_per_share: float, cost_equity: float, years_elapsed: float,
                 dividends: Optional[Sequence[Sequence[float]]] = None) -> float:
    """Roll a per-share value from the balance-sheet date to the valuation date.

    Equity is expected to earn the cost of equity, part of which has already
    been paid out: each dividend [time_paid, amount] (time in years after the
    balance-sheet date) is deducted with its own accrued return.
    """
    value = value_per_share * (1.0 + cost_equity) ** years_elapsed
    for t_paid, amount in (dividends or []):
        if 0.0 <= t_paid <= years_elapsed:
            value -= amount * (1.0 + cost_equity) ** (years_elapsed - t_paid)
    return value


def run_dcf(a: Dict) -> Dict:
    """Full DCF from a flat assumptions dict (see REQUIRED_KEYS)."""
    missing = [k for k in REQUIRED_KEYS if k not in a]
    if missing:
        raise KeyError(f"missing DCF assumptions: {missing}")
    n = int(a["n_years"])
    wacc = a["wacc"]
    ronic = wacc if a["ronic_tied"] else a["terminal_ronic"]
    growth = growth_path(n, a["growth_start"], a["growth_terminal"], a["high_growth_years"])
    margins = margin_path(n, a["margin_start"], a["margin_target"], a["margin_converge_years"])
    capex = capex_path(n, a["capex_pct"], a["capex_pct_terminal"], a["high_growth_years"])
    rows = project_fcff(a["base_revenue"], growth, margins, a["tax_rate"],
                        a["da_pct"], capex, a["nwc_pct"])
    tv = terminal_value(rows[-1]["nopat"], a["growth_terminal"], wacc, ronic)
    ev = enterprise_value([r["fcff"] for r in rows], tv["value"], wacc, bool(a["mid_year"]))
    for r, df, pv in zip(rows, ev["discount_factors"], ev["pv_flows"]):
        r["discount_factor"] = df
        r["pv_fcff"] = pv
    bridge = equity_bridge(ev["enterprise_value"], a["cash"], a["lt_investments"],
                           a["debt"], a["minority"], a["shares"])
    per_share_today = roll_forward(bridge["per_share"], a["cost_equity"],
                                   a["years_since_fye"], a["dividends_since_fye"])
    final = rows[-1]
    return {
        "rows": rows,
        "terminal": tv,
        "ronic_used": ronic,
        "pv_explicit": ev["pv_explicit"],
        "pv_terminal": ev["pv_terminal"],
        "enterprise_value": ev["enterprise_value"],
        "terminal_share": ev["terminal_share"],
        "implied_exit_ev_ebitda": tv["value"] / final["ebitda"] if final["ebitda"] > 0 else None,
        "equity_value": bridge["equity_value"],
        "per_share_fye": bridge["per_share"],
        "per_share": per_share_today,
    }


def sensitivity(a: Dict, key_x: str, values_x: Sequence[float],
                key_y: str, values_y: Sequence[float]) -> List[List[Optional[float]]]:
    """Per-share value grid: rows follow values_y, columns follow values_x.

    Cells where the model is undefined (WACC not above terminal growth) are None.
    """
    grid = []
    for vy in values_y:
        row = []
        for vx in values_x:
            b = dict(a)
            b[key_x] = vx
            b[key_y] = vy
            try:
                row.append(run_dcf(b)["per_share"])
            except ValueError:
                row.append(None)
        grid.append(row)
    return grid


def implied_growth(a: Dict, price: float, lo: float = -0.20, hi: float = 0.60) -> Optional[float]:
    """Reverse DCF: the starting growth rate at which the model value equals
    the market price, holding every other assumption fixed."""
    def gap(g):
        b = dict(a)
        b["growth_start"] = g
        return run_dcf(b)["per_share"] - price
    return fin.bisect_root(gap, lo, hi)


def implied_margin(a: Dict, price: float, lo: float = 0.0, hi: float = 0.80) -> Optional[float]:
    """Reverse DCF: the target EBIT margin at which the model value equals the
    market price, holding every other assumption fixed."""
    def gap(m):
        b = dict(a)
        b["margin_target"] = m
        return run_dcf(b)["per_share"] - price
    return fin.bisect_root(gap, lo, hi)
