"""Comps, LBO and M&A engines against closed forms and accounting identities."""

import numpy as np
import pytest
from hypothesis import assume, given, settings, strategies as st

from conftest import base_lbo, base_merger
from engine import comps, lbo, merger


def company(**over):
    c = {"price": 400.0, "shares": 50.0, "debt": 3000.0, "minority": 200.0, "cash": 1500.0,
         "lt_investments": 500.0, "revenue": 12000.0, "ebitda": 2400.0, "ebit": 2000.0,
         "eps": 25.0, "book_equity": 8000.0}
    c.update(over)
    return c


# ---------------------------------------------------------------- comps

def test_multiples_by_hand():
    m = comps.multiples(company())
    assert m["market_cap"] == pytest.approx(20000.0)
    assert m["enterprise_value"] == pytest.approx(20000 + 3000 + 200 - 1500 - 500)
    assert m["ev_ebitda"] == pytest.approx(21200 / 2400)
    assert m["ev_ebit"] == pytest.approx(21200 / 2000)
    assert m["ev_sales"] == pytest.approx(21200 / 12000)
    assert m["pe"] == pytest.approx(16.0)
    assert m["pb"] == pytest.approx(400 / 160)


def test_non_meaningful_multiples_are_none():
    m = comps.multiples(company(ebitda=-10.0, eps=-2.0, ebit=0.0))
    assert m["ev_ebitda"] is None and m["pe"] is None and m["ev_ebit"] is None
    assert m["ev_sales"] is not None


@pytest.mark.parametrize("multiple", comps.ALL_MULTIPLES)
def test_valuing_a_company_at_its_own_multiple_returns_its_price(multiple):
    c = company()
    own = comps.multiples(c)[multiple]
    assert comps.implied_per_share(c, multiple, own) == pytest.approx(c["price"])


@settings(max_examples=100)
@given(values=st.lists(st.floats(0.1, 200.0), min_size=1, max_size=40), q=st.floats(0.0, 1.0))
def test_quantile_matches_numpy(values, q):
    assert comps.quantile(values, q) == pytest.approx(float(np.quantile(values, q)), rel=1e-9, abs=1e-9)


def test_summary_ignores_missing_values():
    s = comps.summary([10.0, None, 20.0, 30.0, None])
    assert s["n"] == 3 and s["median"] == 20.0 and s["mean"] == 20.0
    assert s["q1"] == 15.0 and s["q3"] == 25.0
    assert comps.summary([None, None]) is None


def test_peer_valuation_orders_low_mid_high():
    target = company()
    peers = [company(price=p) for p in (300.0, 380.0, 450.0, 520.0)]
    out = comps.peer_valuation(target, peers)
    for m in comps.ALL_MULTIPLES:
        assert out[m]["implied_low"] <= out[m]["implied_mid"] <= out[m]["implied_high"]
        assert out[m]["stats"]["n"] == 4
    assert out["pe"]["implied_mid"] == pytest.approx(415.0)


def test_implied_value_none_when_metric_not_positive():
    assert comps.implied_per_share(company(ebitda=-5.0), "ev_ebitda", 10.0) is None
    assert comps.implied_per_share(company(eps=-1.0), "pe", 10.0) is None
    with pytest.raises(KeyError):
        comps.implied_per_share(company(), "nonsense", 10.0)


# ---------------------------------------------------------------- LBO

def test_sources_equal_uses():
    su = lbo.sources_and_uses(2100.0, 210.0, 0.02, 3.0, 1.5)
    assert su["total_sources"] == pytest.approx(su["total_uses"])
    assert su["fees"] == pytest.approx(42.0)
    assert su["senior_debt"] == pytest.approx(630.0)
    assert su["sub_debt"] == pytest.approx(315.0)
    assert su["sponsor_equity"] == pytest.approx(2142.0 - 945.0)
    assert su["entry_multiple"] == pytest.approx(10.0)
    assert su["leverage_x"] == pytest.approx(4.5)


@settings(max_examples=100, deadline=None)
@given(margin=st.floats(0.1, 0.4), tax=st.floats(0.1, 0.35), mult=st.floats(4.0, 20.0),
       hold=st.integers(1, 10))
def test_unlevered_no_growth_deal_has_closed_form_irr(margin, tax, mult, hold):
    """No debt, no growth, capex = D&A, no fees: the sponsor collects NOPAT
    each year as cash and exits at the entry multiple."""
    a = base_lbo()
    a.update({"growth_start": 0.0, "growth_terminal": 0.0, "margin_start": margin,
              "margin_target": margin, "tax_rate": tax, "da_pct": 0.04, "capex_pct": 0.04,
              "capex_pct_terminal": 0.04, "nwc_pct": 0.0, "senior_x": 0.0, "sub_x": 0.0, "fee_pct": 0.0, "hold_years": hold})
    ebitda = 1000.0 * (margin + 0.04)
    a["ebitda_ltm"] = ebitda
    a["entry_ev"] = mult * ebitda
    a["exit_multiple"] = mult
    out = lbo.run_lbo(a)
    nopat = 1000.0 * margin * (1 - tax)
    expected_moic = (mult * ebitda + hold * nopat) / (mult * ebitda)
    assert out["moic"] == pytest.approx(expected_moic, rel=1e-10)
    assert out["irr"] == pytest.approx(expected_moic ** (1 / hold) - 1, abs=1e-9)


def test_lbo_debt_schedule_and_cash_conservation():
    a = base_lbo()
    a["sweep_pct"] = 0.6
    out = lbo.run_lbo(a)
    rows = out["rows"]
    senior_initial = out["sources_uses"]["senior_debt"]
    for i, r in enumerate(rows):
        assert r["senior_end"] == pytest.approx(r["senior_beg"] - r["mandatory"] - r["sweep"])
        assert r["senior_end"] >= -1e-9
        assert r["sweep"] >= 0 and r["mandatory"] >= 0
        if i:
            assert r["senior_beg"] == pytest.approx(rows[i - 1]["senior_end"])
        assert r["net_income"] == pytest.approx(r["ebt"] - r["tax"])
        assert r["cfads"] == pytest.approx(r["net_income"] + r["da"] - r["capex"] - r["delta_nwc"])
    total_cfads = sum(r["cfads"] for r in rows)
    paydown = senior_initial - rows[-1]["senior_end"]
    assert total_cfads == pytest.approx(paydown + rows[-1]["cash_end"])


def test_lbo_interest_circularity_is_solved():
    a = base_lbo()
    out = lbo.run_lbo(a)
    for r in out["rows"]:
        expected = a["senior_rate"] * 0.5 * (r["senior_beg"] + r["senior_end"]) + a["sub_rate"] * r["sub_debt"]
        assert r["interest"] == pytest.approx(expected, rel=1e-11)
    a["interest_on_average"] = False
    for r in lbo.run_lbo(a)["rows"]:
        assert r["interest"] == pytest.approx(a["senior_rate"] * r["senior_beg"] + a["sub_rate"] * r["sub_debt"])


@settings(max_examples=100, deadline=None)
@given(exit_mult=st.floats(5.0, 18.0), senior_x=st.floats(0.0, 4.0), sub_x=st.floats(0.0, 2.0),
       sweep=st.floats(0.0, 1.0), hold=st.integers(1, 8))
def test_lbo_value_creation_bridge_is_exact(exit_mult, senior_x, sub_x, sweep, hold):
    a = base_lbo()
    a.update({"exit_multiple": exit_mult, "senior_x": senior_x, "sub_x": sub_x,
              "sweep_pct": sweep, "hold_years": hold})
    out = lbo.run_lbo(a)
    assert sum(out["attribution"].values()) == pytest.approx(out["value_creation"], rel=1e-9, abs=1e-6)
    assert out["exit_equity"] == pytest.approx(out["exit_ev"] - out["exit_net_debt"])
    if out["irr"] is not None:
        assert out["irr"] == pytest.approx(out["moic"] ** (1 / hold) - 1, abs=1e-9)


@given(m1=st.floats(6.0, 15.0), dm=st.floats(0.1, 5.0))
def test_lbo_irr_rises_with_exit_multiple(m1, dm):
    a = base_lbo()
    a["exit_multiple"] = m1
    low = lbo.run_lbo(a)["irr"]
    a["exit_multiple"] = m1 + dm
    assert lbo.run_lbo(a)["irr"] > low


def test_leverage_amplifies_returns_when_asset_return_exceeds_cost_of_debt():
    a = base_lbo()
    a.update({"senior_x": 0.0, "sub_x": 0.0})
    unlevered = lbo.run_lbo(a)["irr"]
    a.update({"senior_x": 3.0, "sub_x": 0.0})
    levered = lbo.run_lbo(a)["irr"]
    assert unlevered > a["senior_rate"] * (1 - a["tax_rate"])
    assert levered > unlevered


def test_lbo_rejects_infeasible_structures():
    a = base_lbo()
    a["senior_x"] = 12.0
    with pytest.raises(ValueError):
        lbo.run_lbo(a)
    b = base_lbo()
    b["hold_years"] = 11
    with pytest.raises(ValueError):
        lbo.run_lbo(b)
    c = base_lbo()
    del c["exit_multiple"]
    with pytest.raises(KeyError):
        lbo.run_lbo(c)


def test_lbo_shortfall_is_funded_by_an_interest_bearing_revolver():
    a = base_lbo()
    a.update({"senior_amort_pct": 0.5, "margin_start": 0.02, "margin_target": 0.02})
    out = lbo.run_lbo(a)
    rows = out["rows"]
    assert rows[0]["revolver"] > 0
    for i, r in enumerate(rows):
        revolver_beg = max(0.0, -rows[i - 1]["cash_end"]) if i else 0.0
        expected = (a["senior_rate"] * 0.5 * (r["senior_beg"] + r["senior_end"])
                    + a["sub_rate"] * r["sub_debt"] + a["senior_rate"] * revolver_beg)
        assert r["interest"] == pytest.approx(expected, rel=1e-11)
        assert r["revolver"] == pytest.approx(max(0.0, -r["cash_end"]))
        assert r["total_debt"] == pytest.approx(r["senior_end"] + r["sub_debt"] + r["revolver"])
        assert r["net_debt"] == pytest.approx(r["senior_end"] + r["sub_debt"] - r["cash_end"])
        if revolver_beg > 0 and r["cfads"] - r["mandatory"] <= revolver_beg:
            assert r["sweep"] == 0.0
    free = dict(a, senior_rate=0.0)
    assert sum(x["interest"] for x in rows) > sum(x["interest"] for x in lbo.run_lbo(free)["rows"])
    assert sum(out["attribution"].values()) == pytest.approx(out["value_creation"], rel=1e-9, abs=1e-6)


def test_lbo_flags_liquidity_shortfall():
    a = base_lbo()
    a.update({"senior_amort_pct": 0.5, "margin_start": 0.02, "margin_target": 0.02})
    assert lbo.run_lbo(a)["liquidity_shortfall"] is True
    assert lbo.run_lbo(base_lbo())["liquidity_shortfall"] is False


def test_irr_grid_shape_and_infeasible_cells():
    a = base_lbo()
    grid = lbo.irr_grid(a, "exit_multiple", [8.0, 10.0, 12.0], "senior_x", [2.0, 3.0, 20.0])
    assert len(grid) == 3 and len(grid[0]) == 3
    assert grid[2] == [None, None, None]
    assert grid[1][1] == pytest.approx(lbo.run_lbo(a)["irr"])


# ---------------------------------------------------------------- merger

def all_stock(premium=0.0):
    a = base_merger()
    a.update({"pct_cash": 0.0, "premium": premium, "synergies_pretax": 0.0, "fee_pct": 0.0,
              "intangibles_pct": 0.0})
    return a


@settings(max_examples=200)
@given(acq_pe=st.floats(5.0, 60.0), tgt_pe=st.floats(5.0, 60.0), premium=st.floats(0.0, 0.6))
def test_all_stock_deal_is_accretive_iff_acquirer_pe_exceeds_offer_pe(acq_pe, tgt_pe, premium):
    a = all_stock(premium)
    a["acq_price"] = acq_pe * a["acq_net_income"] / a["acq_shares"]
    a["tgt_price"] = tgt_pe * a["tgt_net_income"] / a["tgt_shares"]
    out = merger.run_merger(a)
    offer_pe = tgt_pe * (1 + premium)
    assume(abs(acq_pe - offer_pe) > 1e-6)
    assert (out["accretion"] > 0) == (acq_pe > offer_pe)
    assert out["offer_pe"] == pytest.approx(offer_pe)
    assert out["acquirer_pe"] == pytest.approx(acq_pe)


def test_all_stock_deal_at_equal_pe_is_eps_neutral():
    a = all_stock()
    a["tgt_price"] = (a["acq_price"] / (a["acq_net_income"] / a["acq_shares"])) * a["tgt_net_income"] / a["tgt_shares"]
    assert merger.run_merger(a)["accretion"] == pytest.approx(0.0, abs=1e-12)


@settings(max_examples=200)
@given(kd=st.floats(0.03, 0.2), tgt_pe=st.floats(4.0, 60.0), premium=st.floats(0.0, 0.5))
def test_debt_funded_cash_deal_is_accretive_iff_earnings_yield_beats_after_tax_cost_of_debt(kd, tgt_pe, premium):
    a = base_merger()
    a.update({"pct_cash": 1.0, "cash_from_balance_sheet_pct": 0.0, "cost_of_debt": kd,
              "premium": premium, "synergies_pretax": 0.0, "fee_pct": 0.0, "intangibles_pct": 0.0})
    a["tgt_price"] = tgt_pe * a["tgt_net_income"] / a["tgt_shares"]
    out = merger.run_merger(a)
    earnings_yield = 1 / (tgt_pe * (1 + premium))
    after_tax_kd = kd * (1 - a["tax_rate"])
    assume(abs(earnings_yield - after_tax_kd) > 1e-6)
    assert (out["accretion"] > 0) == (earnings_yield > after_tax_kd)
    assert out["new_shares"] == 0 and out["acquirer_ownership"] == 1.0


def test_merger_by_hand():
    out = merger.run_merger(base_merger())
    assert out["offer_price"] == pytest.approx(250.0)
    assert out["purchase_price"] == pytest.approx(10000.0)
    assert out["cash_consideration"] == pytest.approx(5000.0)
    assert out["new_shares"] == pytest.approx(10.0)
    assert out["exchange_ratio"] == pytest.approx(0.25)
    assert out["fees"] == pytest.approx(100.0)
    assert out["cash_used"] == pytest.approx(2550.0)
    assert out["new_debt"] == pytest.approx(2550.0)
    assert out["intangibles"] == pytest.approx(1750.0)
    assert out["amortisation"] == pytest.approx(175.0)
    assert out["goodwill"] == pytest.approx(5250.0)
    keep = 1 - 0.2517
    expected_ni = 2500 + 500 + 120 * keep - 2550 * 0.085 * keep - 2550 * 0.065 * keep - 175 * keep
    assert out["pro_forma_net_income"] == pytest.approx(expected_ni)
    assert out["pro_forma_shares"] == pytest.approx(110.0)
    assert out["pro_forma_eps"] == pytest.approx(expected_ni / 110)
    assert out["accretion"] == pytest.approx(expected_ni / 110 / 25 - 1)
    assert out["acquirer_ownership"] + out["target_ownership"] == pytest.approx(1.0)


@settings(max_examples=100)
@given(premium=st.floats(0.0, 0.8), pct_cash=st.floats(0.0, 1.0), bs=st.floats(0.0, 1.0))
def test_breakeven_synergies_make_the_deal_exactly_eps_neutral(premium, pct_cash, bs):
    a = base_merger()
    a.update({"premium": premium, "pct_cash": pct_cash, "cash_from_balance_sheet_pct": bs})
    a["synergies_pretax"] = merger.run_merger(a)["breakeven_synergies_pretax"]
    assert merger.run_merger(a)["accretion"] == pytest.approx(0.0, abs=1e-10)


@given(premium=st.floats(0.0, 1.0), pct_cash=st.floats(0.0, 1.0))
def test_purchase_price_allocation_identity(premium, pct_cash):
    a = base_merger()
    a.update({"premium": premium, "pct_cash": pct_cash})
    out = merger.run_merger(a)
    assert out["goodwill"] + out["intangibles"] + a["tgt_book_equity"] == pytest.approx(out["purchase_price"])
    assert out["cash_consideration"] + out["stock_consideration"] == pytest.approx(out["purchase_price"])
    assert out["cash_used"] + out["new_debt"] == pytest.approx(out["cash_consideration"] + out["fees"])


def test_merger_rejects_bad_input():
    a = base_merger()
    a["pct_cash"] = 1.2
    with pytest.raises(ValueError):
        merger.run_merger(a)
    b = base_merger()
    del b["premium"]
    with pytest.raises(KeyError):
        merger.run_merger(b)


def test_accretion_grid():
    a = base_merger()
    grid = merger.accretion_grid(a, "premium", [0.1, 0.25, 0.4], "pct_cash", [0.0, 0.5, 1.0])
    assert grid[1][1] == pytest.approx(merger.run_merger(a)["accretion"])
    assert all(grid[r][0] > grid[r][2] for r in range(3))
