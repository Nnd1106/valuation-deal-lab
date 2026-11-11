"""merger.py: accretion / dilution analysis for an acquisition.

Pro forma net income = acquirer + target
                       + after-tax synergies
                       - after-tax interest on new acquisition debt
                       - after-tax income foregone on balance-sheet cash used
                       - after-tax amortisation of acquired intangibles.
Pro forma shares    = acquirer shares + new shares issued to the target.

One-off transaction fees are funded alongside the cash consideration but are
excluded from run-rate earnings. Deferred tax on the intangible write-up is
ignored.
"""

from __future__ import annotations

from typing import Dict, Optional

REQUIRED_KEYS = (
    "acq_price", "acq_shares", "acq_net_income", "tgt_price", "tgt_shares", "tgt_net_income",
    "tgt_book_equity", "premium", "pct_cash", "cash_from_balance_sheet_pct", "cost_of_debt",
    "yield_on_cash", "tax_rate", "synergies_pretax", "synergy_phase", "fee_pct",
    "intangibles_pct", "amort_years",
)


def run_merger(a: Dict) -> Dict:
    missing = [k for k in REQUIRED_KEYS if k not in a]
    if missing:
        raise KeyError(f"missing merger assumptions: {missing}")
    if not 0.0 <= a["pct_cash"] <= 1.0:
        raise ValueError("pct_cash must be between 0 and 1")
    if a["acq_shares"] <= 0 or a["tgt_shares"] <= 0 or a["acq_price"] <= 0 or a["tgt_price"] <= 0:
        raise ValueError("prices and share counts must be positive")

    tax = a["tax_rate"]
    offer_price = a["tgt_price"] * (1.0 + a["premium"])
    purchase_price = offer_price * a["tgt_shares"]
    cash_consideration = purchase_price * a["pct_cash"]
    stock_consideration = purchase_price - cash_consideration
    new_shares = stock_consideration / a["acq_price"]
    exchange_ratio = new_shares / a["tgt_shares"]

    fees = purchase_price * a["fee_pct"]
    cash_needed = cash_consideration + fees
    cash_used = cash_needed * a["cash_from_balance_sheet_pct"]
    new_debt = cash_needed - cash_used

    excess = max(0.0, purchase_price - a["tgt_book_equity"])
    intangibles = excess * a["intangibles_pct"]
    amortisation = intangibles / a["amort_years"] if a["amort_years"] > 0 else 0.0
    goodwill = purchase_price - a["tgt_book_equity"] - intangibles

    synergies_at = a["synergies_pretax"] * a["synergy_phase"] * (1.0 - tax)
    debt_interest_at = new_debt * a["cost_of_debt"] * (1.0 - tax)
    foregone_at = cash_used * a["yield_on_cash"] * (1.0 - tax)
    amort_at = amortisation * (1.0 - tax)

    standalone_eps = a["acq_net_income"] / a["acq_shares"]
    pf_shares = a["acq_shares"] + new_shares
    pf_ni_ex_synergies = (a["acq_net_income"] + a["tgt_net_income"]
                          - debt_interest_at - foregone_at - amort_at)
    pf_ni = pf_ni_ex_synergies + synergies_at
    pf_eps = pf_ni / pf_shares
    accretion = pf_eps / standalone_eps - 1.0 if standalone_eps > 0 else None

    breakeven_synergies: Optional[float] = None
    realised = (1.0 - tax) * a["synergy_phase"]
    if realised > 0:
        breakeven_synergies = (standalone_eps * pf_shares - pf_ni_ex_synergies) / realised

    acq_pe = a["acq_price"] / standalone_eps if standalone_eps > 0 else None
    tgt_eps = a["tgt_net_income"] / a["tgt_shares"]
    offer_pe = offer_price / tgt_eps if tgt_eps > 0 else None

    return {
        "offer_price": offer_price,
        "purchase_price": purchase_price,
        "cash_consideration": cash_consideration,
        "stock_consideration": stock_consideration,
        "new_shares": new_shares,
        "exchange_ratio": exchange_ratio,
        "fees": fees,
        "cash_used": cash_used,
        "new_debt": new_debt,
        "intangibles": intangibles,
        "amortisation": amortisation,
        "goodwill": goodwill,
        "synergies_after_tax": synergies_at,
        "debt_interest_after_tax": debt_interest_at,
        "foregone_interest_after_tax": foregone_at,
        "amortisation_after_tax": amort_at,
        "standalone_eps": standalone_eps,
        "pro_forma_net_income": pf_ni,
        "pro_forma_shares": pf_shares,
        "pro_forma_eps": pf_eps,
        "accretion": accretion,
        "breakeven_synergies_pretax": breakeven_synergies,
        "acquirer_ownership": a["acq_shares"] / pf_shares,
        "target_ownership": new_shares / pf_shares,
        "acquirer_pe": acq_pe,
        "offer_pe": offer_pe,
    }


def accretion_grid(a: Dict, key_x: str, values_x, key_y: str, values_y):
    """Accretion grid: rows follow values_y, columns follow values_x."""
    grid = []
    for vy in values_y:
        row = []
        for vx in values_x:
            b = dict(a)
            b[key_x] = vx
            b[key_y] = vy
            row.append(run_merger(b)["accretion"])
        grid.append(row)
    return grid
