"""lbo.py: leveraged buyout returns model.

Structure:
  Uses    = entry enterprise value + transaction fees
  Sources = senior term loan + subordinated notes + sponsor equity (the plug)

The deal is struck on a cash-free, debt-free basis: existing debt is
refinanced and existing cash and financial investments are netted in the
entry enterprise value, so the new capital structure starts with no cash.

Each year the senior loan takes a mandatory amortisation plus a cash sweep
of a share of the remaining free cash flow. Interest is charged on the
average senior balance, which makes interest and the sweep mutually
dependent; the loop below solves that circularity by fixed-point iteration.
Subordinated notes pay cash interest and are repaid at exit.

If cash flow cannot cover interest, tax, investment and mandatory
amortisation, the gap is drawn on a revolver (carried as negative cash). The
revolver is charged the senior rate on its opening balance and is repaid
before any cash is swept to the term loan, so a structure that runs short of
cash pays for it instead of borrowing for free.

`run_lbo` shares the DCF operating case (same growth and margin paths) so
the two models can never drift apart.
"""

from __future__ import annotations

from typing import Dict, List

from . import dcf, fin

REQUIRED_KEYS = (
    "entry_ev", "ebitda_ltm", "fee_pct", "senior_x", "senior_rate", "senior_amort_pct",
    "sweep_pct", "sub_x", "sub_rate", "hold_years", "exit_multiple", "interest_on_average",
    "n_years", "base_revenue", "growth_start", "growth_terminal", "high_growth_years",
    "margin_start", "margin_target", "margin_converge_years", "tax_rate",
    "da_pct", "capex_pct", "capex_pct_terminal", "nwc_pct",
)


def sources_and_uses(entry_ev: float, ebitda_ltm: float, fee_pct: float,
                     senior_x: float, sub_x: float) -> Dict[str, float]:
    fees = entry_ev * fee_pct
    senior = senior_x * ebitda_ltm
    sub = sub_x * ebitda_ltm
    uses = entry_ev + fees
    equity = uses - senior - sub
    return {
        "entry_ev": entry_ev, "fees": fees, "total_uses": uses,
        "senior_debt": senior, "sub_debt": sub, "sponsor_equity": equity,
        "total_sources": senior + sub + equity,
        "entry_multiple": entry_ev / ebitda_ltm,
        "leverage_x": (senior + sub) / ebitda_ltm,
        "equity_pct": equity / uses,
    }


def run_lbo(a: Dict) -> Dict:
    missing = [k for k in REQUIRED_KEYS if k not in a]
    if missing:
        raise KeyError(f"missing LBO assumptions: {missing}")
    hold = int(a["hold_years"])
    n = int(a["n_years"])
    if not 1 <= hold <= n:
        raise ValueError("hold_years must be between 1 and n_years")
    if a["ebitda_ltm"] <= 0:
        raise ValueError("LTM EBITDA must be positive")

    su = sources_and_uses(a["entry_ev"], a["ebitda_ltm"], a["fee_pct"], a["senior_x"], a["sub_x"])
    if su["sponsor_equity"] <= 0:
        raise ValueError("debt exceeds total uses: sponsor equity must be positive")

    growth = dcf.growth_path(n, a["growth_start"], a["growth_terminal"], a["high_growth_years"])[:hold]
    margins = dcf.margin_path(n, a["margin_start"], a["margin_target"], a["margin_converge_years"])[:hold]
    capex = dcf.capex_path(n, a["capex_pct"], a["capex_pct_terminal"], a["high_growth_years"])[:hold]
    ops = dcf.project_fcff(a["base_revenue"], growth, margins, a["tax_rate"],
                           a["da_pct"], capex, a["nwc_pct"])

    tax_rate = a["tax_rate"]
    senior_initial = su["senior_debt"]
    sub = su["sub_debt"]
    senior = senior_initial
    cash = 0.0
    rows: List[Dict[str, float]] = []
    shortfall = False

    for op in ops:
        senior_beg = senior
        revolver_beg = max(0.0, -cash)
        mandatory = min(senior_beg, a["senior_amort_pct"] * senior_initial)
        other_interest = a["sub_rate"] * sub + a["senior_rate"] * revolver_beg
        interest = a["senior_rate"] * senior_beg + other_interest
        for _ in range(500):
            ebt = op["ebit"] - interest
            tax = max(ebt, 0.0) * tax_rate
            net_income = ebt - tax
            cfads = net_income + op["da"] - op["capex"] - op["delta_nwc"]
            sweep = min(senior_beg - mandatory,
                        max(0.0, cfads - mandatory - revolver_beg) * a["sweep_pct"])
            senior_end = senior_beg - mandatory - sweep
            base = 0.5 * (senior_beg + senior_end) if a["interest_on_average"] else senior_beg
            new_interest = a["senior_rate"] * base + other_interest
            converged = abs(new_interest - interest) <= 1e-13 * max(1.0, abs(interest))
            interest = new_interest
            if converged:
                break
        ebt = op["ebit"] - interest
        tax = max(ebt, 0.0) * tax_rate
        net_income = ebt - tax
        cfads = net_income + op["da"] - op["capex"] - op["delta_nwc"]
        sweep = min(senior_beg - mandatory,
                    max(0.0, cfads - mandatory - revolver_beg) * a["sweep_pct"])
        senior = senior_beg - mandatory - sweep
        cash = cash + cfads - mandatory - sweep
        if cash < -1e-9:
            shortfall = True
        revolver = max(0.0, -cash)
        total_debt = senior + sub + revolver
        rows.append({
            "year": op["year"], "revenue": op["revenue"], "ebitda": op["ebitda"], "ebit": op["ebit"],
            "interest": interest, "ebt": ebt, "tax": tax, "net_income": net_income,
            "da": op["da"], "capex": op["capex"], "delta_nwc": op["delta_nwc"], "cfads": cfads,
            "mandatory": mandatory, "sweep": sweep, "senior_beg": senior_beg, "senior_end": senior,
            "sub_debt": sub, "cash_end": cash, "revolver": revolver, "total_debt": total_debt,
            "net_debt": senior + sub - cash,
            "debt_to_ebitda": total_debt / op["ebitda"] if op["ebitda"] > 0 else None,
            "interest_cover": op["ebitda"] / interest if interest > 0 else None,
        })

    final = rows[-1]
    exit_ev = a["exit_multiple"] * final["ebitda"]
    exit_net_debt = final["net_debt"]
    exit_equity = exit_ev - exit_net_debt
    equity_in = su["sponsor_equity"]
    flows = [-equity_in] + [0.0] * (hold - 1) + [exit_equity]
    irr = fin.irr(flows) if exit_equity > 0 else None
    entry_net_debt = senior_initial + sub
    entry_multiple = su["entry_multiple"]
    attribution = {
        "ebitda_growth": (final["ebitda"] - a["ebitda_ltm"]) * entry_multiple,
        "multiple_expansion": (a["exit_multiple"] - entry_multiple) * final["ebitda"],
        "deleveraging": entry_net_debt - exit_net_debt,
        "fees": -su["fees"],
    }
    return {
        "sources_uses": su,
        "rows": rows,
        "exit_ev": exit_ev,
        "exit_net_debt": exit_net_debt,
        "exit_equity": exit_equity,
        "moic": exit_equity / equity_in,
        "irr": irr,
        "value_creation": exit_equity - equity_in,
        "attribution": attribution,
        "liquidity_shortfall": shortfall,
    }


def entry_ev_for_irr(a: Dict, target_irr: float):
    """Highest entry enterprise value at which the sponsor still earns
    `target_irr`, holding the exit multiple and financing terms fixed.

    Returns None when no feasible entry value reaches the target.
    """
    # Start a quarter-turn of EBITDA above the point where sponsor equity
    # would be zero, so the search never begins on a degenerate structure.
    floor = (a["senior_x"] + a["sub_x"]) * a["ebitda_ltm"] / (1.0 + a["fee_pct"]) + 0.25 * a["ebitda_ltm"]

    def gap(ev):
        b = dict(a)
        b["entry_ev"] = ev
        try:
            irr = run_lbo(b)["irr"]
        except ValueError:
            return float("nan")
        return (irr if irr is not None else -1.0) - target_irr

    return fin.bisect_root(gap, floor, 200.0 * a["ebitda_ltm"])


def irr_grid(a: Dict, key_x: str, values_x, key_y: str, values_y) -> List[List]:
    """IRR grid: rows follow values_y, columns follow values_x. Infeasible
    structures (non-positive sponsor equity or exit equity) are None."""
    grid = []
    for vy in values_y:
        row = []
        for vx in values_x:
            b = dict(a)
            b[key_x] = vx
            b[key_y] = vy
            try:
                row.append(run_lbo(b)["irr"])
            except ValueError:
                row.append(None)
        grid.append(row)
    return grid
