import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def base_dcf():
    """A plain, internally consistent DCF case used across the test suite."""
    return {
        "n_years": 10, "base_revenue": 1000.0, "growth_start": 0.12, "growth_terminal": 0.05,
        "high_growth_years": 3, "margin_start": 0.18, "margin_target": 0.20,
        "margin_converge_years": 5, "tax_rate": 0.2517, "da_pct": 0.03, "capex_pct": 0.05,
        "capex_pct_terminal": 0.04, "nwc_pct": 0.10, "wacc": 0.11, "terminal_ronic": 0.11, "ronic_tied": True,
        "mid_year": True, "cash": 150.0, "lt_investments": 50.0, "debt": 200.0,
        "minority": 10.0, "shares": 25.0, "cost_equity": 0.125, "years_since_fye": 0.6,
        "dividends_since_fye": [[0.3, 2.0]],
    }


def base_lbo():
    a = {k: base_dcf()[k] for k in (
        "n_years", "base_revenue", "growth_start", "growth_terminal", "high_growth_years",
        "margin_start", "margin_target", "margin_converge_years", "tax_rate",
        "da_pct", "capex_pct", "capex_pct_terminal", "nwc_pct")}
    a.update({
        "entry_ev": 2100.0, "ebitda_ltm": 210.0, "fee_pct": 0.02, "senior_x": 3.0,
        "senior_rate": 0.10, "senior_amort_pct": 0.05, "sweep_pct": 1.0, "sub_x": 1.5,
        "sub_rate": 0.13, "hold_years": 5, "exit_multiple": 10.0, "interest_on_average": True,
    })
    return a


def base_merger():
    return {
        "acq_price": 500.0, "acq_shares": 100.0, "acq_net_income": 2500.0,
        "tgt_price": 200.0, "tgt_shares": 40.0, "tgt_net_income": 500.0,
        "tgt_book_equity": 3000.0, "premium": 0.25, "pct_cash": 0.5,
        "cash_from_balance_sheet_pct": 0.5, "cost_of_debt": 0.085, "yield_on_cash": 0.065,
        "tax_rate": 0.2517, "synergies_pretax": 120.0, "synergy_phase": 1.0, "fee_pct": 0.01,
        "intangibles_pct": 0.25, "amort_years": 10,
    }
