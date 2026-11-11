"""statements.py: turn raw provider statements into one standard schema.

Input is the snapshot format written by pipeline/fetch.py:
    {"income": {period_end: {line: value}}, "balance": {...}, "cashflow": {...},
     "q_income": {...}, "q_balance": {...}, "info": {...}}
with values in the reporting currency's base unit.

Output values are in INR crore (1 crore = 10 million); share counts are in
crore shares, so value / shares is rupees per share.

Definitions used throughout the lab:
  EBIT            operating income, before other/investment income
  EBITDA          EBIT + depreciation and amortisation
  cash            cash, equivalents and short-term investments
  lt_investments  non-current financial investments + equity-method investments
  debt            total borrowings including lease obligations
  NWC             (current assets - cash) - (current liabilities - current debt)
  invested capital  equity + minority + debt - cash - lt_investments
"""

from __future__ import annotations

import math
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

CRORE = 1e7


def _num(d: Dict, *keys: str) -> Optional[float]:
    """First present, finite value among the candidate line names."""
    for k in keys:
        v = d.get(k)
        if v is not None and isinstance(v, (int, float)) and math.isfinite(v):
            return float(v)
    return None


def _zero(d: Dict, *keys: str) -> float:
    v = _num(d, *keys)
    return 0.0 if v is None else v


def _parse(iso: str) -> date:
    y, m, d = (int(x) for x in iso.split("-"))
    return date(y, m, d)


def _months_between(later: str, earlier: str) -> int:
    a, b = _parse(later), _parse(earlier)
    return (a.year - b.year) * 12 + (a.month - b.month)


# ---------------------------------------------------------------- raw extractors

def _operating_income(row: Dict) -> Optional[float]:
    """Operating income before other and investment income.

    The provider sometimes files genuine operating costs under "other
    non-operating" items (HCL Technologies carries about 14% of revenue there),
    so negative amounts on that line are treated as operating costs. Positive
    amounts are treasury and investment income and stay out of EBIT: the
    assets that earn them are valued separately in the equity bridge.
    """
    reported = _num(row, "Operating Income", "Total Operating Income As Reported")
    if reported is None:
        return None
    return reported + min(0.0, _zero(row, "Other Non Operating Income Expenses"))


def _ebit_bottom_up(row: Dict) -> Optional[float]:
    """Independent rebuild of operating income from pre-tax profit, used only
    as a cross-check on the provider's classification."""
    pretax = _num(row, "Pretax Income")
    if pretax is None:
        return None
    return (pretax + _zero(row, "Interest Expense", "Interest Expense Non Operating")
            - _zero(row, "Interest Income", "Interest Income Non Operating")
            - max(0.0, _zero(row, "Other Non Operating Income Expenses"))
            - _zero(row, "Total Unusual Items"))


def _income(row: Dict) -> Dict[str, Optional[float]]:
    return {
        "revenue": _num(row, "Total Revenue", "Operating Revenue"),
        "ebit": _operating_income(row),
        "ebit_reported": _num(row, "Operating Income", "Total Operating Income As Reported"),
        "ebit_bottom_up": _ebit_bottom_up(row),
        "da": _num(row, "Reconciled Depreciation", "Depreciation And Amortization In Income Statement"),
        "interest_expense": _num(row, "Interest Expense", "Interest Expense Non Operating"),
        "pretax": _num(row, "Pretax Income"),
        "tax": _num(row, "Tax Provision"),
        "net_income": _num(row, "Net Income Common Stockholders", "Net Income"),
        "eps": _num(row, "Diluted EPS", "Basic EPS"),
        "shares_diluted": _num(row, "Diluted Average Shares", "Basic Average Shares"),
    }


def _balance(row: Dict) -> Dict[str, Optional[float]]:
    cash = _num(row, "Cash Cash Equivalents And Short Term Investments")
    if cash is None:
        c = _num(row, "Cash And Cash Equivalents")
        cash = None if c is None else c + _zero(row, "Other Short Term Investments")
    debt = _num(row, "Total Debt")
    if debt is None:
        parts = [_num(row, "Long Term Debt And Capital Lease Obligation", "Long Term Debt"),
                 _num(row, "Current Debt And Capital Lease Obligation", "Current Debt")]
        debt = None if all(p is None for p in parts) else sum(p or 0.0 for p in parts)
    return {
        "cash": cash,
        "lt_investments": _zero(row, "Investmentin Financial Assets") + _zero(row, "Long Term Equity Investment"),
        "debt": debt,
        "current_debt": _zero(row, "Current Debt And Capital Lease Obligation", "Current Debt"),
        "equity": _num(row, "Stockholders Equity", "Common Stock Equity"),
        "minority": _zero(row, "Minority Interest"),
        "total_assets": _num(row, "Total Assets"),
        "total_liabilities": _num(row, "Total Liabilities Net Minority Interest"),
        "current_assets": _num(row, "Current Assets"),
        "current_liabilities": _num(row, "Current Liabilities"),
        "receivables": _zero(row, "Accounts Receivable"),
        "inventory": _zero(row, "Inventory"),
        "payables": _zero(row, "Accounts Payable"),
        "net_ppe": _zero(row, "Net PPE"),
        "goodwill_intangibles": _zero(row, "Goodwill And Other Intangible Assets"),
        "shares_out": _num(row, "Ordinary Shares Number", "Share Issued"),
    }


def _cashflow(row: Dict) -> Dict[str, Optional[float]]:
    capex = _num(row, "Capital Expenditure")
    dividends = _num(row, "Cash Dividends Paid", "Common Stock Dividend Paid")
    return {
        "cfo": _num(row, "Operating Cash Flow"),
        "capex": None if capex is None else -capex,
        "dividends": 0.0 if dividends is None else -dividends,
    }


INCOME_CORE = ("revenue", "ebit", "da", "pretax", "tax", "net_income")
BALANCE_CORE = ("cash", "debt", "equity", "total_assets", "total_liabilities",
                "current_assets", "current_liabilities", "shares_out")
CASHFLOW_CORE = ("cfo", "capex")
FLOW_FIELDS = ("revenue", "ebit", "ebit_reported", "ebit_bottom_up", "da", "interest_expense", "pretax", "tax", "net_income",
               "eps", "cfo", "capex", "dividends")
STOCK_FIELDS = ("cash", "lt_investments", "debt", "current_debt", "equity", "minority",
                "total_assets", "total_liabilities", "current_assets", "current_liabilities",
                "receivables", "inventory", "payables", "net_ppe", "goodwill_intangibles")


def _complete(row: Dict, core: Tuple[str, ...]) -> bool:
    return all(row.get(k) is not None for k in core)


# ---------------------------------------------------------------- currency

def detect_reporting_currency(raw: Dict, usdinr: float) -> Optional[str]:
    """Infer whether the statements are in INR or USD.

    The provider's currency tag is unreliable for Indian companies that also
    file in the US, so the statements' own EPS is compared with the trailing
    EPS quoted in rupees (or, failing that, with the share price).
    Returns "INR", "USD" or None when neither reading is plausible.
    """
    info = raw.get("info", {})
    stmt_eps = None
    q = raw.get("q_income", {})
    quarters = sorted(q.keys(), reverse=True)[:4]
    if len(quarters) == 4:
        vals = [_num(q[p], "Diluted EPS", "Basic EPS") for p in quarters]
        if all(v is not None for v in vals):
            stmt_eps = sum(vals)
    if stmt_eps is None:
        annual = raw.get("income", {})
        for p in sorted(annual.keys(), reverse=True):
            stmt_eps = _num(annual[p], "Diluted EPS", "Basic EPS")
            if stmt_eps is not None:
                break
    if stmt_eps is None or stmt_eps <= 0:
        return None
    ref_eps = info.get("trailingEps")
    plausible = []
    for ccy, fx in (("INR", 1.0), ("USD", usdinr)):
        if ref_eps and ref_eps > 0:
            ok = 1.0 / 3.0 < stmt_eps * fx / ref_eps < 3.0
        else:
            price = info.get("currentPrice") or info.get("previousClose")
            ok = bool(price) and 2.0 < price / (stmt_eps * fx) < 250.0
        if ok:
            plausible.append(ccy)
    return plausible[0] if len(plausible) == 1 else None


# ---------------------------------------------------------------- normalisation

def _scale(row: Dict, flow_fx: float, stock_fx: float) -> Dict:
    """Convert to INR crore. EPS is per share so it is only FX-converted."""
    out = dict(row)
    for k in FLOW_FIELDS:
        if out.get(k) is not None:
            out[k] = out[k] * flow_fx / (1.0 if k == "eps" else CRORE)
    for k in STOCK_FIELDS:
        if out.get(k) is not None:
            out[k] = out[k] * stock_fx / CRORE
    for k in ("shares_out", "shares_diluted"):
        if out.get(k) is not None:
            out[k] = out[k] / CRORE
    return out


def _derive(row: Dict) -> Dict:
    """Add the metrics that are pure functions of one period's lines."""
    r = dict(row)
    if r.get("ebit") is not None and r.get("da") is not None:
        r["ebitda"] = r["ebit"] + r["da"]
    if all(r.get(k) is not None for k in ("current_assets", "cash", "current_liabilities")):
        r["nwc"] = (r["current_assets"] - r["cash"]) - (r["current_liabilities"] - r.get("current_debt", 0.0))
    if all(r.get(k) is not None for k in ("equity", "debt", "cash")):
        r["invested_capital"] = (r["equity"] + r.get("minority", 0.0) + r["debt"]
                                 - r["cash"] - r.get("lt_investments", 0.0))
        r["net_debt"] = r["debt"] - r["cash"]
    return r


def fiscal_years(raw: Dict, max_years: int = 4) -> List[str]:
    """Most recent run of consecutive, complete fiscal years (newest first)."""
    periods = []
    for p in sorted(raw.get("income", {}).keys(), reverse=True):
        inc = _income(raw["income"][p])
        bal = _balance(raw.get("balance", {}).get(p, {}))
        cf = _cashflow(raw.get("cashflow", {}).get(p, {}))
        if _complete(inc, INCOME_CORE) and _complete(bal, BALANCE_CORE) and _complete(cf, CASHFLOW_CORE):
            if periods and _months_between(periods[-1], p) != 12:
                break
            periods.append(p)
            if len(periods) == max_years:
                break
        elif periods:
            break
    return periods


def normalize(raw: Dict, usdinr_spot: float,
              fx_avg: Optional[Callable[[str, str], float]] = None,
              fx_at: Optional[Callable[[str], float]] = None) -> Dict:
    """Standardise one company's statements.

    `fx_avg(start_iso, end_iso)` and `fx_at(iso)` give the USDINR average over
    a period and the rate on a date; they are only used for USD reporters
    (flows at the period average, balances at the period-end rate).

    Returns {"currency", "annual" (oldest first), "ltm", "latest_bs", "flags"}.
    "annual" is empty when the company cannot be used.
    """
    flags: List[str] = []
    ccy = detect_reporting_currency(raw, usdinr_spot)
    if ccy is None:
        return {"currency": None, "annual": [], "ltm": None, "latest_bs": None,
                "flags": ["reporting currency could not be verified"]}
    if ccy == "USD":
        if fx_avg is None or fx_at is None:
            raise ValueError("USD reporter needs fx_avg and fx_at")
        flags.append("statements reported in USD: flows converted at period-average USDINR, "
                     "balances at period-end USDINR")

    def flow_fx(end_iso: str, months: int) -> float:
        if ccy == "INR":
            return 1.0
        e = _parse(end_iso)
        month_index = e.year * 12 + (e.month - 1) - months + 1
        start = date(month_index // 12, month_index % 12 + 1, 1)
        return fx_avg(start.isoformat(), end_iso)

    def stock_fx(end_iso: str) -> float:
        return 1.0 if ccy == "INR" else fx_at(end_iso)

    annual = []
    for p in reversed(fiscal_years(raw)):
        row = {"period_end": p, "fy": _parse(p).year}
        row.update(_income(raw["income"][p]))
        row.update(_balance(raw["balance"][p]))
        row.update(_cashflow(raw["cashflow"][p]))
        if row["interest_expense"] is None:
            row["interest_expense"] = 0.0
            flags.append(f"FY{row['fy']}: no interest expense reported, treated as zero")
        annual.append(_derive(_scale(row, flow_fx(p, 12), stock_fx(p))))

    return {
        "currency": ccy,
        "annual": annual,
        "ltm": _ltm(raw, flow_fx),
        "latest_bs": _latest_balance(raw, stock_fx),
        "flags": flags,
    }


def _ltm(raw: Dict, flow_fx: Callable[[str, int], float]) -> Optional[Dict]:
    """Last twelve months as the sum of the four most recent consecutive quarters."""
    q = raw.get("q_income", {})
    periods = sorted(q.keys(), reverse=True)
    for start in range(0, max(0, len(periods) - 3)):
        window = periods[start:start + 4]
        rows = [_income(q[p]) for p in window]
        consecutive = all(_months_between(window[i], window[i + 1]) == 3 for i in range(3))
        if not consecutive or not all(_complete(r, INCOME_CORE) for r in rows):
            continue
        out: Dict = {"period_end": window[0], "quarters": list(reversed(window))}
        scaled = [_scale(r, flow_fx(p, 3), 1.0) for r, p in zip(rows, window)]
        for k in ("revenue", "ebit", "da", "pretax", "tax", "net_income"):
            out[k] = sum(r[k] for r in scaled)
        out["interest_expense"] = sum(r["interest_expense"] or 0.0 for r in scaled)
        out["ebitda"] = out["ebit"] + out["da"]
        eps = [r["eps"] for r in scaled]
        out["eps"] = sum(eps) if all(e is not None for e in eps) else None
        return out
    return None


def _latest_balance(raw: Dict, stock_fx: Callable[[str], float]) -> Optional[Dict]:
    """Most recent balance sheet (interim if available) with the bridge items."""
    candidates = [(p, raw["q_balance"][p]) for p in raw.get("q_balance", {})]
    candidates += [(p, raw["balance"][p]) for p in raw.get("balance", {})]
    for p, row in sorted(candidates, key=lambda x: x[0], reverse=True):
        b = _balance(row)
        if all(b.get(k) is not None for k in ("cash", "debt", "equity", "shares_out")):
            out = {"period_end": p}
            out.update(b)
            return _derive(_scale(out, 1.0, stock_fx(p)))
    return None


# ---------------------------------------------------------------- history metrics

def history_metrics(annual: List[Dict], tax_rate: float) -> Dict:
    """Ratios across the fiscal years that drive the default forecast."""
    if not annual:
        raise ValueError("no fiscal years")
    first, last = annual[0], annual[-1]
    n = len(annual)
    growth = [annual[i]["revenue"] / annual[i - 1]["revenue"] - 1.0 for i in range(1, n)]
    revenue_cagr = (last["revenue"] / first["revenue"]) ** (1.0 / (n - 1)) - 1.0 if n > 1 else None

    def avg(fn):
        vals = [fn(r) for r in annual]
        return sum(vals) / len(vals)

    roic = []
    for i in range(1, n):
        ic = 0.5 * (annual[i]["invested_capital"] + annual[i - 1]["invested_capital"])
        nopat = annual[i]["ebit"] * (1.0 - tax_rate)
        meaningful = ic > 0.05 * annual[i]["revenue"]
        roic.append(nopat / ic if meaningful else None)
    eff_tax = [r["tax"] / r["pretax"] if r["pretax"] > 0 else None for r in annual]
    return {
        "years": [r["fy"] for r in annual],
        "revenue_growth": growth,
        "revenue_cagr": revenue_cagr,
        "ebit_margin": [r["ebit"] / r["revenue"] for r in annual],
        "ebitda_margin": [r["ebitda"] / r["revenue"] for r in annual],
        "net_margin": [r["net_income"] / r["revenue"] for r in annual],
        "avg_ebit_margin": avg(lambda r: r["ebit"] / r["revenue"]),
        "da_pct": avg(lambda r: r["da"] / r["revenue"]),
        "capex_pct": avg(lambda r: r["capex"] / r["revenue"]),
        "nwc_pct": avg(lambda r: r["nwc"] / r["revenue"]),
        "roic": roic,
        "effective_tax": eff_tax,
        "cash_conversion": [r["cfo"] / r["ebitda"] if r["ebitda"] > 0 else None for r in annual],
        "interest_coverage": (last["ebit"] / last["interest_expense"]
                              if last["interest_expense"] > 0 else None),
    }
