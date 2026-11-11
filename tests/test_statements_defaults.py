"""Statement normalisation and default-assumption rules on synthetic filings."""

import copy

import pytest

from engine import dcf, defaults, statements, wacc

CR = statements.CRORE
MKT = {"gsec_10y": 0.0712, "sovereign_spread": 0.0187, "erp": 0.0708, "tax_rate": 0.2517,
       "terminal_growth": 0.05, "cash_yield": 0.065, "lbo_premium": 0.25, "lbo_fee_pct": 0.02,
       "lbo_senior_x": 3.0, "lbo_senior_spread": 0.03, "lbo_senior_amort_pct": 0.05,
       "lbo_sub_x": 1.5, "lbo_sub_spread": 0.055, "ma_premium": 0.25,
       "ma_synergy_pct_revenue": 0.02, "ma_fee_pct": 0.01, "ma_intangibles_pct": 0.25,
       "ma_amort_years": 10}


def income(rev, shares=10 * CR, other_non_op=0.0):
    ebit = 0.20 * rev
    pretax = ebit - 0.01 * rev + 0.005 * rev + other_non_op
    tax = 0.25 * pretax
    ni = pretax - tax
    return {"Total Revenue": rev, "Operating Income": ebit, "Reconciled Depreciation": 0.04 * rev,
            "Interest Expense": 0.01 * rev, "Interest Income": 0.005 * rev,
            "Other Non Operating Income Expenses": other_non_op, "Pretax Income": pretax,
            "Tax Provision": tax, "Net Income Common Stockholders": ni,
            "Diluted EPS": ni / shares, "Diluted Average Shares": shares}


def balance(rev, shares=10 * CR):
    return {"Cash Cash Equivalents And Short Term Investments": 0.10 * rev,
            "Investmentin Financial Assets": 0.05 * rev, "Long Term Equity Investment": 0.01 * rev,
            "Total Debt": 0.20 * rev, "Current Debt And Capital Lease Obligation": 0.04 * rev,
            "Stockholders Equity": 0.50 * rev, "Minority Interest": 0.02 * rev,
            "Total Assets": 1.00 * rev, "Total Liabilities Net Minority Interest": 0.48 * rev,
            "Current Assets": 0.40 * rev, "Current Liabilities": 0.25 * rev,
            "Accounts Receivable": 0.12 * rev, "Inventory": 0.10 * rev, "Accounts Payable": 0.09 * rev,
            "Net PPE": 0.40 * rev, "Goodwill And Other Intangible Assets": 0.05 * rev,
            "Ordinary Shares Number": shares}


def cashflow(rev):
    return {"Operating Cash Flow": 0.18 * rev, "Capital Expenditure": -0.06 * rev,
            "Cash Dividends Paid": -0.03 * rev}


def make_raw(revenues=None, quarter_rev=300 * CR, trailing_eps=None):
    """Four fiscal years growing 10% a year, plus five quarters."""
    revenues = revenues or [1000 * CR, 1100 * CR, 1210 * CR, 1331 * CR]
    years = ["2023-03-31", "2024-03-31", "2025-03-31", "2026-03-31"][-len(revenues):]
    quarters = ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"]
    raw = {"income": {}, "balance": {}, "cashflow": {}, "q_income": {}, "q_balance": {}}
    for y, r in zip(years, revenues):
        raw["income"][y], raw["balance"][y], raw["cashflow"][y] = income(r), balance(r), cashflow(r)
    for q in quarters:
        raw["q_income"][q] = income(quarter_rev)
    raw["q_balance"]["2026-09-30"] = balance(1400 * CR)
    ltm_eps = 4 * raw["q_income"]["2026-09-30"]["Diluted EPS"]
    raw["info"] = {"trailingEps": trailing_eps if trailing_eps is not None else ltm_eps,
                   "currentPrice": 20 * ltm_eps, "sharesOutstanding": 10 * CR}
    return raw


# ---------------------------------------------------------------- normalisation

def test_normalize_converts_to_crore_and_keeps_fiscal_order():
    norm = statements.normalize(make_raw(), 90.0)
    assert norm["currency"] == "INR"
    assert [r["fy"] for r in norm["annual"]] == [2023, 2024, 2025, 2026]
    last = norm["annual"][-1]
    assert last["revenue"] == pytest.approx(1331.0)
    assert last["ebit"] == pytest.approx(266.2)
    assert last["ebitda"] == pytest.approx(266.2 + 53.24)
    assert last["capex"] == pytest.approx(79.86)
    assert last["dividends"] == pytest.approx(39.93)
    assert last["shares_out"] == pytest.approx(10.0)
    assert last["eps"] == pytest.approx(last["net_income"] / 10.0)


def test_derived_balance_sheet_definitions():
    last = statements.normalize(make_raw(), 90.0)["annual"][-1]
    rev = 1331.0
    assert last["cash"] == pytest.approx(0.10 * rev)
    assert last["lt_investments"] == pytest.approx(0.06 * rev)
    assert last["nwc"] == pytest.approx((0.40 - 0.10) * rev - (0.25 - 0.04) * rev)
    assert last["invested_capital"] == pytest.approx((0.50 + 0.02 + 0.20 - 0.10 - 0.06) * rev)
    assert last["net_debt"] == pytest.approx(0.10 * rev)
    assert last["total_assets"] == pytest.approx(
        last["total_liabilities"] + last["equity"] + last["minority"])


def test_ltm_sums_the_latest_four_quarters():
    norm = statements.normalize(make_raw(), 90.0)
    ltm = norm["ltm"]
    assert ltm["period_end"] == "2026-09-30"
    assert ltm["quarters"] == ["2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"]
    assert ltm["revenue"] == pytest.approx(1200.0)
    assert ltm["ebit"] == pytest.approx(240.0)
    assert ltm["ebitda"] == pytest.approx(288.0)
    assert ltm["eps"] == pytest.approx(ltm["net_income"] / 10.0)


def test_ltm_skips_an_incomplete_latest_quarter():
    raw = make_raw()
    del raw["q_income"]["2026-09-30"]["Pretax Income"]
    ltm = statements.normalize(raw, 90.0)["ltm"]
    assert ltm["period_end"] == "2026-06-30"


def test_ltm_is_none_without_four_consecutive_quarters():
    raw = make_raw()
    del raw["q_income"]["2026-03-31"]
    assert statements.normalize(raw, 90.0)["ltm"] is None


def test_latest_balance_prefers_the_interim_statement():
    bs = statements.normalize(make_raw(), 90.0)["latest_bs"]
    assert bs["period_end"] == "2026-09-30"
    assert bs["cash"] == pytest.approx(140.0)
    raw = make_raw()
    del raw["q_balance"]["2026-09-30"]["Stockholders Equity"]
    assert statements.normalize(raw, 90.0)["latest_bs"]["period_end"] == "2026-03-31"


def test_fiscal_years_stop_at_a_gap():
    raw = make_raw()
    del raw["balance"]["2024-03-31"]
    assert statements.fiscal_years(raw) == ["2026-03-31", "2025-03-31"]
    raw2 = make_raw()
    raw2["income"]["2022-12-31"] = raw2["income"].pop("2023-03-31")
    raw2["balance"]["2022-12-31"] = raw2["balance"].pop("2023-03-31")
    raw2["cashflow"]["2022-12-31"] = raw2["cashflow"].pop("2023-03-31")
    assert statements.fiscal_years(raw2) == ["2026-03-31", "2025-03-31", "2024-03-31"]


def test_negative_other_non_operating_items_are_operating_costs():
    raw = make_raw()
    rev = 1331 * CR
    raw["income"]["2026-03-31"] = income(rev, other_non_op=-0.08 * rev)
    last = statements.normalize(raw, 90.0)["annual"][-1]
    assert last["ebit_reported"] == pytest.approx(266.2)
    assert last["ebit"] == pytest.approx(266.2 - 0.08 * 1331)
    assert last["ebit"] == pytest.approx(last["ebit_bottom_up"])


def test_positive_other_income_stays_outside_ebit():
    raw = make_raw()
    rev = 1331 * CR
    raw["income"]["2026-03-31"] = income(rev, other_non_op=0.05 * rev)
    last = statements.normalize(raw, 90.0)["annual"][-1]
    assert last["ebit"] == pytest.approx(266.2)
    assert last["ebit_bottom_up"] == pytest.approx(266.2)


# ---------------------------------------------------------------- currency

def test_usd_reporter_is_detected_and_converted():
    raw = make_raw()
    inr_eps = raw["info"]["trailingEps"]
    raw["info"]["trailingEps"] = inr_eps * 90.0
    assert statements.detect_reporting_currency(raw, 90.0) == "USD"
    norm = statements.normalize(raw, 90.0, fx_avg=lambda s, e: 80.0, fx_at=lambda d: 90.0)
    last = norm["annual"][-1]
    assert norm["currency"] == "USD"
    assert last["revenue"] == pytest.approx(1331.0 * 80.0)
    assert last["cash"] == pytest.approx(133.1 * 90.0)
    assert last["eps"] == pytest.approx(last["net_income"] / last["shares_out"])
    assert any("USD" in f for f in norm["flags"])


def test_usd_flow_conversion_uses_the_fiscal_year_window():
    seen = []
    raw = make_raw()
    raw["info"]["trailingEps"] *= 90.0

    def fx_avg(start, end):
        seen.append((start, end))
        return 80.0

    statements.normalize(raw, 90.0, fx_avg=fx_avg, fx_at=lambda d: 90.0)
    assert ("2025-04-01", "2026-03-31") in seen
    assert ("2026-07-01", "2026-09-30") in seen


def test_usd_reporter_needs_fx_functions():
    raw = make_raw()
    raw["info"]["trailingEps"] *= 90.0
    with pytest.raises(ValueError):
        statements.normalize(raw, 90.0)


def test_unverifiable_currency_is_rejected():
    raw = make_raw()
    raw["info"]["trailingEps"] *= 9.0
    assert statements.detect_reporting_currency(raw, 90.0) is None
    norm = statements.normalize(raw, 90.0)
    assert norm["annual"] == [] and norm["currency"] is None


def test_currency_falls_back_to_price_when_trailing_eps_missing():
    raw = make_raw()
    raw["info"]["trailingEps"] = None
    assert statements.detect_reporting_currency(raw, 90.0) == "INR"


# ---------------------------------------------------------------- history metrics

def test_history_metrics():
    norm = statements.normalize(make_raw(), 90.0)
    h = statements.history_metrics(norm["annual"], 0.25)
    assert h["years"] == [2023, 2024, 2025, 2026]
    assert h["revenue_growth"] == pytest.approx([0.10, 0.10, 0.10])
    assert h["revenue_cagr"] == pytest.approx(0.10)
    assert h["avg_ebit_margin"] == pytest.approx(0.20)
    assert h["da_pct"] == pytest.approx(0.04)
    assert h["capex_pct"] == pytest.approx(0.06)
    assert h["nwc_pct"] == pytest.approx(0.09)
    assert h["interest_coverage"] == pytest.approx(20.0)
    ic_avg = 0.56 * (1331 + 1210) / 2
    assert h["roic"][-1] == pytest.approx(266.2 * 0.75 / ic_avg)
    assert h["effective_tax"] == pytest.approx([0.25] * 4)


def test_roic_not_meaningful_for_negligible_invested_capital():
    norm = statements.normalize(make_raw(), 90.0)
    annual = copy.deepcopy(norm["annual"])
    for r in annual:
        r["invested_capital"] = 0.01 * r["revenue"]
    assert statements.history_metrics(annual, 0.25)["roic"] == [None, None, None]


# ---------------------------------------------------------------- default rules

def test_company_wacc_by_hand():
    c = defaults.company_wacc(MKT, 8000.0, 2000.0, 7.0, 0.80)
    rf = 0.0712 - 0.0187
    beta = 0.80 * (1 + (1 - 0.2517) * 0.25)
    ke = rf + beta * 0.0708
    kd = 0.0712 + 0.0055
    assert c["risk_free"] == pytest.approx(rf)
    assert c["levered_beta"] == pytest.approx(beta)
    assert c["cost_equity"] == pytest.approx(ke)
    assert c["rating"] == "AA" and c["pretax_cost_debt"] == pytest.approx(kd)
    assert c["wacc"] == pytest.approx(0.8 * ke + 0.2 * kd * (1 - 0.2517))


def test_terminal_capex_rules():
    args = dict(wacc=0.12, margin_target=0.20, tax_rate=0.25, nwc_pct=0.10)
    # below depreciation: converges up to depreciation
    assert defaults.terminal_capex_pct(0.02, 0.04, 0.10, 0.05, **args) == pytest.approx(0.04)
    # growth capex scales with growth: 4% + 2% x (5 / 10)
    assert defaults.terminal_capex_pct(0.06, 0.04, 0.10, 0.05, **args) == pytest.approx(0.05)
    # heavy expansion is capped at what the terminal value assumes
    consistent = 0.04 + 0.05 / 0.12 * 0.20 * 0.75 - 0.10 * 0.05 / 1.05
    assert defaults.terminal_capex_pct(0.30, 0.04, 0.10, 0.05, **args) == pytest.approx(consistent)
    # no fade in growth: history is kept, still subject to the cap
    assert defaults.terminal_capex_pct(0.05, 0.04, 0.05, 0.05, **args) == pytest.approx(0.05)


def test_terminal_capex_never_below_depreciation():
    out = defaults.terminal_capex_pct(0.10, 0.04, 0.10, 0.05, wacc=0.12, margin_target=0.01,
                                      tax_rate=0.25, nwc_pct=0.50)
    assert out == pytest.approx(0.04)


def test_default_dcf_follows_the_documented_rules():
    norm = statements.normalize(make_raw(), 90.0)
    fye = norm["annual"][-1]
    hist = statements.history_metrics(norm["annual"], MKT["tax_rate"])
    cost = defaults.company_wacc(MKT, 5000.0, fye["debt"], hist["interest_coverage"], 0.9)
    a = defaults.default_dcf(fye, hist, cost, MKT, 10.0, 0.6, [[0.2, 1.5]])
    assert a["growth_start"] == pytest.approx(0.10)
    assert a["growth_terminal"] == pytest.approx(0.05)
    assert a["margin_start"] == pytest.approx(0.20) and a["margin_target"] == pytest.approx(0.20)
    assert a["ronic_tied"] is True and a["terminal_ronic"] == a["wacc"] == cost["wacc"]
    assert a["capex_pct_terminal"] == pytest.approx(0.04 + 0.02 * 0.5)
    assert a["cash"] == fye["cash"] and a["debt"] == fye["debt"]
    out = dcf.run_dcf(a)
    assert out["enterprise_value"] > 0


def test_default_growth_is_bounded():
    norm = statements.normalize(make_raw([1000 * CR, 1500 * CR, 2250 * CR, 3375 * CR]), 90.0)
    hist = statements.history_metrics(norm["annual"], MKT["tax_rate"])
    cost = defaults.company_wacc(MKT, 5000.0, 100.0, None, 0.9)
    a = defaults.default_dcf(norm["annual"][-1], hist, cost, MKT, 10.0, 0.5, [])
    assert a["growth_start"] == defaults.GROWTH_CAP
    shrinking = statements.normalize(make_raw([1331 * CR, 1210 * CR, 1100 * CR, 1000 * CR]), 90.0)
    hist2 = statements.history_metrics(shrinking["annual"], MKT["tax_rate"])
    a2 = defaults.default_dcf(shrinking["annual"][-1], hist2, cost, MKT, 10.0, 0.5, [])
    assert a2["growth_start"] == a2["growth_terminal"]


def test_terminal_growth_never_exceeds_risk_free_rate():
    mkt = dict(MKT, gsec_10y=0.05, sovereign_spread=0.02)
    norm = statements.normalize(make_raw(), 90.0)
    hist = statements.history_metrics(norm["annual"], mkt["tax_rate"])
    cost = defaults.company_wacc(mkt, 5000.0, 100.0, None, 0.9)
    a = defaults.default_dcf(norm["annual"][-1], hist, cost, mkt, 10.0, 0.5, [])
    assert a["growth_terminal"] == pytest.approx(0.03)


def test_sector_unlevered_betas_take_the_median():
    rows = [{"sector": "x", "raw_beta": 1.0, "debt": 0.0, "market_cap": 100.0},
            {"sector": "x", "raw_beta": 1.4, "debt": 0.0, "market_cap": 100.0},
            {"sector": "x", "raw_beta": 0.6, "debt": 0.0, "market_cap": 100.0},
            {"sector": "y", "raw_beta": 1.2, "debt": 50.0, "market_cap": 100.0},
            {"sector": "y", "raw_beta": None, "debt": 50.0, "market_cap": 100.0}]
    out = defaults.sector_unlevered_betas(rows, 0.25)
    assert out["x"] == pytest.approx(1.0)
    assert out["y"] == pytest.approx(wacc.unlever_beta(1.2, 0.5, 0.25))


def test_default_lbo_and_merger_are_runnable():
    from engine import lbo, merger
    norm = statements.normalize(make_raw(), 90.0)
    fye, bs = norm["annual"][-1], norm["latest_bs"]
    hist = statements.history_metrics(norm["annual"], MKT["tax_rate"])
    cost = defaults.company_wacc(MKT, 5000.0, bs["debt"], hist["interest_coverage"], 0.9)
    a = defaults.default_dcf(fye, hist, cost, MKT, 10.0, 0.6, [])
    la = defaults.default_lbo(a, 5000.0, bs, norm["ltm"]["ebitda"], MKT)
    assert la["entry_ev"] == pytest.approx(5000 * 1.25 + bs["debt"] + bs["minority"] - bs["cash"] - bs["lt_investments"])
    assert la["exit_multiple"] == pytest.approx(la["entry_ev"] / la["ebitda_ltm"])
    out = lbo.run_lbo(la)
    assert out["sources_uses"]["total_sources"] == pytest.approx(out["sources_uses"]["total_uses"])
    side = {"price": 500.0, "shares": 10.0, "net_income": 150.0, "book_equity": 700.0,
            "revenue": 1200.0, "pretax_cost_debt": 0.08}
    ma = defaults.default_merger(side, dict(side, price=300.0), MKT)
    assert ma["synergies_pretax"] == pytest.approx(24.0)
    assert merger.run_merger(ma)["pro_forma_shares"] > 10.0


def test_entry_ev_for_irr_round_trip():
    from conftest import base_lbo
    from engine import lbo
    a = base_lbo()
    ev = lbo.entry_ev_for_irr(a, 0.20)
    b = dict(a, entry_ev=ev)
    assert lbo.run_lbo(b)["irr"] == pytest.approx(0.20, abs=1e-9)
    assert lbo.entry_ev_for_irr(a, 0.15) > ev
    assert lbo.entry_ev_for_irr(a, 50.0) is None
