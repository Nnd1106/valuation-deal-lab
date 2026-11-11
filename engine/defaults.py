"""defaults.py: the documented rules that turn history into starting assumptions.

Nothing here is a forecast. These are transparent, mechanical starting points
that every user is expected to override in the interface:
  - growth starts at the historical revenue CAGR, bounded to
    [terminal growth, 15%], and fades to terminal growth;
  - the EBIT margin reverts from the last fiscal year to the company's own
    multi-year average over five years;
  - D&A and working capital intensity stay at their historical averages;
  - capex starts at its historical average and converges to a steady state:
    growth capex (the part above depreciation) shrinks in proportion to
    growth, is capped at the reinvestment the terminal value itself assumes,
    and capex never ends below depreciation;
  - new investment after the horizon earns exactly the cost of capital
    (RONIC = WACC), so growth beyond year ten adds no value.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from . import wacc as wacc_mod

GROWTH_CAP = 0.15
NWC_PCT_BOUNDS = (-0.20, 0.50)
N_YEARS = 10
HIGH_GROWTH_YEARS = 3
MARGIN_CONVERGE_YEARS = 5


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def company_wacc(mkt: Dict, market_cap: float, debt: float, interest_coverage: Optional[float],
                 unlevered_beta: float) -> Dict:
    """Cost of capital for one company.

    Risk-free rate = 10-year government yield less the sovereign default
    spread; the equity risk premium already contains the country premium, so
    country risk is counted once. Cost of debt = government yield plus the
    company's synthetic-rating spread.
    """
    tax = mkt["tax_rate"]
    risk_free = mkt["gsec_10y"] - mkt["sovereign_spread"]
    debt_to_equity = debt / market_cap
    beta = wacc_mod.relever_beta(unlevered_beta, debt_to_equity, tax)
    cost_equity = wacc_mod.cost_of_equity(risk_free, beta, mkt["erp"])
    rating, spread = wacc_mod.synthetic_rating(interest_coverage)
    pretax_kd = mkt["gsec_10y"] + spread
    w = wacc_mod.wacc(market_cap, debt, cost_equity, pretax_kd, tax)
    return {
        "risk_free": risk_free, "erp": mkt["erp"], "unlevered_beta": unlevered_beta,
        "debt_to_equity": debt_to_equity, "levered_beta": beta, "cost_equity": cost_equity,
        "interest_coverage": interest_coverage, "rating": rating, "default_spread": spread,
        "pretax_cost_debt": pretax_kd, "after_tax_cost_debt": w["after_tax_cost_debt"],
        "weight_equity": w["weight_equity"], "weight_debt": w["weight_debt"],
        "tax_rate": tax, "wacc": w["wacc"],
    }


def terminal_capex_pct(capex_pct: float, da_pct: float, growth_start: float, growth_terminal: float,
                       wacc: float, margin_target: float, tax_rate: float, nwc_pct: float) -> float:
    """Steady-state capex as a share of revenue: the lower of two estimates,
    floored at depreciation.

    (a) History scaled to growth. Capex above depreciation is growth capex,
        so it shrinks in proportion to growth. Capex at or below depreciation
        converges up to depreciation, since a business cannot under-invest
        relative to wear for ever.
    (b) What the terminal value assumes. With new investment earning the cost
        of capital, net investment is NOPAT x g / WACC; taking out the working
        capital part leaves the capex consistent with the continuing value.

    Taking the lower one stops a temporary expansion phase from being
    projected for ever, while leaving capital-light businesses on their own
    history through the explicit forecast.
    """
    net = capex_pct - da_pct
    if net <= 0:
        return da_pct
    scaled = da_pct + net * growth_terminal / growth_start if growth_start > growth_terminal > 0 else capex_pct
    net_investment = growth_terminal / wacc * margin_target * (1.0 - tax_rate)
    consistent = da_pct + net_investment - nwc_pct * growth_terminal / (1.0 + growth_terminal)
    return max(da_pct, min(scaled, consistent))


def default_dcf(fye: Dict, hist: Dict, cost: Dict, mkt: Dict, shares: float,
                years_since_fye: float, dividends_since_fye: Sequence[Sequence[float]]) -> Dict:
    """Starting DCF assumptions from the last fiscal year and its history."""
    g_t = min(mkt["terminal_growth"], cost["risk_free"])
    cagr = hist["revenue_cagr"] if hist["revenue_cagr"] is not None else g_t
    growth_start = clamp(cagr, g_t, GROWTH_CAP)
    return {
        "n_years": N_YEARS,
        "base_revenue": fye["revenue"],
        "growth_start": growth_start,
        "growth_terminal": g_t,
        "high_growth_years": HIGH_GROWTH_YEARS,
        "margin_start": fye["ebit"] / fye["revenue"],
        "margin_target": hist["avg_ebit_margin"],
        "margin_converge_years": MARGIN_CONVERGE_YEARS,
        "tax_rate": mkt["tax_rate"],
        "da_pct": hist["da_pct"],
        "capex_pct": hist["capex_pct"],
        "capex_pct_terminal": terminal_capex_pct(
            hist["capex_pct"], hist["da_pct"], growth_start, g_t, cost["wacc"],
            hist["avg_ebit_margin"], mkt["tax_rate"], clamp(hist["nwc_pct"], *NWC_PCT_BOUNDS)),
        "nwc_pct": clamp(hist["nwc_pct"], *NWC_PCT_BOUNDS),
        "wacc": cost["wacc"],
        "terminal_ronic": cost["wacc"],
        "ronic_tied": True,
        "mid_year": True,
        "cash": fye["cash"],
        "lt_investments": fye["lt_investments"],
        "debt": fye["debt"],
        "minority": fye["minority"],
        "shares": shares,
        "cost_equity": cost["cost_equity"],
        "years_since_fye": years_since_fye,
        "dividends_since_fye": [list(d) for d in dividends_since_fye],
    }


def default_lbo(dcf_a: Dict, market_cap: float, bs: Dict, ebitda_ltm: float, mkt: Dict) -> Dict:
    """Illustrative take-private at a control premium, sharing the DCF operating case."""
    entry_equity = market_cap * (1.0 + mkt["lbo_premium"])
    entry_ev = entry_equity + bs["debt"] + bs["minority"] - bs["cash"] - bs["lt_investments"]
    a = {k: dcf_a[k] for k in (
        "n_years", "base_revenue", "growth_start", "growth_terminal", "high_growth_years",
        "margin_start", "margin_target", "margin_converge_years", "tax_rate",
        "da_pct", "capex_pct", "capex_pct_terminal", "nwc_pct")}
    a.update({
        "entry_ev": entry_ev,
        "ebitda_ltm": ebitda_ltm,
        "fee_pct": mkt["lbo_fee_pct"],
        "senior_x": mkt["lbo_senior_x"],
        "senior_rate": mkt["gsec_10y"] + mkt["lbo_senior_spread"],
        "senior_amort_pct": mkt["lbo_senior_amort_pct"],
        "sweep_pct": 1.0,
        "sub_x": mkt["lbo_sub_x"],
        "sub_rate": mkt["gsec_10y"] + mkt["lbo_sub_spread"],
        "hold_years": 5,
        "exit_multiple": entry_ev / ebitda_ltm,
        "interest_on_average": True,
    })
    return a


def default_merger(acq: Dict, tgt: Dict, mkt: Dict) -> Dict:
    """Starting accretion/dilution assumptions for an acquirer and a target.

    Each side needs: price, shares, net_income (LTM), book_equity, revenue
    (LTM) and pretax_cost_debt.
    """
    return {
        "acq_price": acq["price"], "acq_shares": acq["shares"], "acq_net_income": acq["net_income"],
        "tgt_price": tgt["price"], "tgt_shares": tgt["shares"], "tgt_net_income": tgt["net_income"],
        "tgt_book_equity": tgt["book_equity"],
        "premium": mkt["ma_premium"],
        "pct_cash": 0.5,
        "cash_from_balance_sheet_pct": 0.5,
        "cost_of_debt": acq["pretax_cost_debt"],
        "yield_on_cash": mkt["cash_yield"],
        "tax_rate": mkt["tax_rate"],
        "synergies_pretax": mkt["ma_synergy_pct_revenue"] * tgt["revenue"],
        "synergy_phase": 1.0,
        "fee_pct": mkt["ma_fee_pct"],
        "intangibles_pct": mkt["ma_intangibles_pct"],
        "amort_years": mkt["ma_amort_years"],
    }


def sector_unlevered_betas(rows: List[Dict], tax_rate: float) -> Dict[str, float]:
    """Median unlevered beta per sector.

    `rows`: one dict per company with sector, raw_beta, debt, market_cap.
    Each raw regression beta is unlevered at the company's own market
    debt-to-equity; the sector median is the bottom-up asset beta.
    """
    by_sector: Dict[str, List[float]] = {}
    for r in rows:
        if r.get("raw_beta") is None:
            continue
        bu = wacc_mod.unlever_beta(r["raw_beta"], r["debt"] / r["market_cap"], tax_rate)
        by_sector.setdefault(r["sector"], []).append(bu)
    return {s: wacc_mod.median(v) for s, v in by_sector.items()}
