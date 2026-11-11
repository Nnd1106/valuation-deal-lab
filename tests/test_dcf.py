"""DCF engine against closed-form results and structural properties."""

import pytest
from hypothesis import assume, given, settings, strategies as st

from conftest import base_dcf
from engine import dcf


def constant_growth_case(g, wacc, margin, tax, nwc_pct, n, mid_year):
    """A firm whose FCFF grows at g for ever: explicit reinvestment is set so
    that it equals the terminal value-driver reinvestment g / RONIC."""
    ronic = margin * (1 - tax) * (1 + g) / nwc_pct
    a = base_dcf()
    a.update({
        "n_years": n, "growth_start": g, "growth_terminal": g, "high_growth_years": 0,
        "margin_start": margin, "margin_target": margin, "tax_rate": tax,
        "da_pct": 0.04, "capex_pct": 0.04, "capex_pct_terminal": 0.04, "nwc_pct": nwc_pct, "wacc": wacc,
        "terminal_ronic": ronic, "ronic_tied": False, "mid_year": mid_year,
    })
    return a


# ---------------------------------------------------------------- paths

def test_growth_path_holds_then_fades_to_terminal():
    path = dcf.growth_path(10, 0.12, 0.05, 3)
    assert path[:3] == [0.12, 0.12, 0.12]
    assert path[-1] == pytest.approx(0.05)
    steps = [path[i] - path[i + 1] for i in range(3, 9)]
    assert all(s == pytest.approx(0.01) for s in steps)


@given(n=st.integers(1, 30), h=st.integers(0, 40), g0=st.floats(-0.1, 0.5), gt=st.floats(0.0, 0.08))
def test_growth_path_always_ends_at_terminal_growth(n, h, g0, gt):
    path = dcf.growth_path(n, g0, gt, h)
    assert len(path) == n
    assert path[-1] == pytest.approx(gt)
    lo, hi = min(g0, gt), max(g0, gt)
    assert all(lo - 1e-12 <= g <= hi + 1e-12 for g in path)


def test_capex_path_fades_on_the_growth_schedule_and_feeds_fcff():
    a = base_dcf()
    a.update({"capex_pct": 0.10, "capex_pct_terminal": 0.04})
    rows = dcf.run_dcf(a)["rows"]
    ratios = [r["capex"] / r["revenue"] for r in rows]
    assert ratios[:3] == pytest.approx([0.10, 0.10, 0.10])
    assert ratios[-1] == pytest.approx(0.04)
    assert all(ratios[i] >= ratios[i + 1] - 1e-12 for i in range(9))
    for r in rows:
        assert r["fcff"] == pytest.approx(r["nopat"] + r["da"] - r["capex"] - r["delta_nwc"])


def test_project_fcff_rejects_mismatched_paths():
    with pytest.raises(ValueError):
        dcf.project_fcff(1000.0, [0.1, 0.1], [0.2, 0.2], 0.25, 0.03, [0.05], 0.10)


def test_margin_path_converges_linearly_then_holds():
    path = dcf.margin_path(8, 0.10, 0.20, 5)
    assert path[:5] == pytest.approx([0.12, 0.14, 0.16, 0.18, 0.20])
    assert path[5:] == pytest.approx([0.20, 0.20, 0.20])


def test_project_fcff_first_year_by_hand():
    rows = dcf.project_fcff(1000.0, [0.10], [0.20], 0.25, 0.03, [0.05], 0.10)
    r = rows[0]
    assert r["revenue"] == pytest.approx(1100.0)
    assert r["ebit"] == pytest.approx(220.0)
    assert r["nopat"] == pytest.approx(165.0)
    assert r["da"] == pytest.approx(33.0)
    assert r["capex"] == pytest.approx(55.0)
    assert r["delta_nwc"] == pytest.approx(10.0)
    assert r["fcff"] == pytest.approx(165.0 + 33.0 - 55.0 - 10.0)
    assert r["ebitda"] == pytest.approx(253.0)


# ---------------------------------------------------------------- closed forms

@settings(max_examples=200, deadline=None)
@given(g=st.floats(0.0, 0.06), spread=st.floats(0.02, 0.12), margin=st.floats(0.08, 0.35),
       tax=st.floats(0.15, 0.35), nwc_pct=st.floats(0.05, 0.30), n=st.integers(1, 25),
       mid_year=st.booleans())
def test_constant_growth_firm_equals_gordon_formula(g, spread, margin, tax, nwc_pct, n, mid_year):
    wacc = g + spread
    a = constant_growth_case(g, wacc, margin, tax, nwc_pct, n, mid_year)
    out = dcf.run_dcf(a)
    fcff_1 = out["rows"][0]["fcff"]
    assume(fcff_1 > 0)
    gordon = fcff_1 / (wacc - g) * ((1 + wacc) ** 0.5 if mid_year else 1.0)
    assert out["enterprise_value"] == pytest.approx(gordon, rel=1e-9)


@settings(max_examples=100, deadline=None)
@given(g=st.floats(0.0, 0.06), spread=st.floats(0.02, 0.12), n1=st.integers(1, 20), n2=st.integers(1, 20))
def test_value_does_not_depend_on_horizon_for_constant_growth_firm(g, spread, n1, n2):
    wacc = g + spread
    ev1 = dcf.run_dcf(constant_growth_case(g, wacc, 0.2, 0.25, 0.15, n1, True))["enterprise_value"]
    ev2 = dcf.run_dcf(constant_growth_case(g, wacc, 0.2, 0.25, 0.15, n2, True))["enterprise_value"]
    assert ev1 == pytest.approx(ev2, rel=1e-9)


@given(nopat=st.floats(1.0, 1e6), g=st.floats(0.0, 0.07), spread=st.floats(0.01, 0.15))
def test_terminal_value_is_growth_neutral_when_ronic_equals_wacc(nopat, g, spread):
    wacc = g + spread
    tv = dcf.terminal_value(nopat, g, wacc, wacc)
    assert tv["value"] == pytest.approx(tv["nopat_next"] / wacc, rel=1e-10)


@given(nopat=st.floats(1.0, 1e6), wacc=st.floats(0.08, 0.16), g1=st.floats(0.0, 0.03),
       dg=st.floats(0.001, 0.03), premium=st.floats(0.01, 0.2))
def test_growth_creates_value_only_when_ronic_exceeds_wacc(nopat, wacc, g1, dg, premium):
    def tv_per_nopat_next(g, ronic):
        t = dcf.terminal_value(nopat, g, wacc, ronic)
        return t["value"] / t["nopat_next"]
    g2 = g1 + dg
    assert tv_per_nopat_next(g2, wacc + premium) > tv_per_nopat_next(g1, wacc + premium)
    assert tv_per_nopat_next(g2, wacc - 0.02) < tv_per_nopat_next(g1, wacc - 0.02)


def test_terminal_value_by_hand():
    tv = dcf.terminal_value(100.0, 0.05, 0.11, 0.15)
    assert tv["nopat_next"] == pytest.approx(105.0)
    assert tv["reinvestment_rate"] == pytest.approx(1 / 3)
    assert tv["fcff_next"] == pytest.approx(70.0)
    assert tv["value"] == pytest.approx(70.0 / 0.06)


def test_terminal_value_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        dcf.terminal_value(100.0, 0.11, 0.11, 0.15)
    with pytest.raises(ValueError):
        dcf.terminal_value(100.0, 0.05, 0.11, 0.0)
    with pytest.raises(ValueError):
        dcf.terminal_value(100.0, -0.01, 0.11, 0.15)


@given(wacc=st.floats(0.06, 0.2))
def test_mid_year_convention_scales_value_by_half_a_year(wacc):
    a = base_dcf()
    a["wacc"] = wacc
    mid = dcf.run_dcf(a)["enterprise_value"]
    a["mid_year"] = False
    end = dcf.run_dcf(a)["enterprise_value"]
    assert mid / end == pytest.approx((1 + wacc) ** 0.5, rel=1e-12)


def test_enterprise_value_by_hand():
    out = dcf.enterprise_value([100.0, 110.0], 1500.0, 0.10, mid_year=False)
    assert out["pv_explicit"] == pytest.approx(100 / 1.1 + 110 / 1.21)
    assert out["pv_terminal"] == pytest.approx(1500 / 1.21)
    assert out["terminal_share"] == pytest.approx(out["pv_terminal"] / out["enterprise_value"])
    mid = dcf.enterprise_value([100.0, 110.0], 1500.0, 0.10, mid_year=True)
    assert mid["pv_explicit"] == pytest.approx(100 / 1.1 ** 0.5 + 110 / 1.1 ** 1.5)
    assert mid["pv_terminal"] == pytest.approx(1500 / 1.1 ** 1.5)


# ---------------------------------------------------------------- bridge and roll-forward

def test_equity_bridge_identity():
    out = dcf.equity_bridge(1000.0, 150.0, 50.0, 200.0, 10.0, 25.0)
    assert out["equity_value"] == pytest.approx(990.0)
    assert out["per_share"] == pytest.approx(39.6)
    with pytest.raises(ValueError):
        dcf.equity_bridge(1000.0, 0, 0, 0, 0, 0)


def test_roll_forward_closed_form():
    assert dcf.roll_forward(100.0, 0.12, 0.0) == pytest.approx(100.0)
    assert dcf.roll_forward(100.0, 0.12, 1.0) == pytest.approx(112.0)
    value = dcf.roll_forward(100.0, 0.12, 0.75, [[0.25, 3.0]])
    assert value == pytest.approx(100 * 1.12 ** 0.75 - 3 * 1.12 ** 0.5)


def test_roll_forward_ignores_dividends_outside_the_window():
    assert dcf.roll_forward(100.0, 0.12, 0.5, [[0.8, 5.0], [-0.1, 5.0]]) == pytest.approx(100 * 1.12 ** 0.5)


@given(v=st.floats(1.0, 1e5), ke=st.floats(0.05, 0.25), t=st.floats(0.0, 1.5),
       t_div=st.floats(0.0, 1.5), d=st.floats(0.0, 50.0))
def test_roll_forward_preserves_present_value(v, ke, t, t_div, d):
    """Holding the share to the valuation date is worth the same as the
    starting value: PV(rolled value) + PV(dividend) = starting value."""
    assume(t_div <= t)
    rolled = dcf.roll_forward(v, ke, t, [[t_div, d]])
    pv = rolled / (1 + ke) ** t + d / (1 + ke) ** t_div
    assert pv == pytest.approx(v, rel=1e-10)


# ---------------------------------------------------------------- full model

def test_run_dcf_reconciles_internally():
    a = base_dcf()
    out = dcf.run_dcf(a)
    assert out["enterprise_value"] == pytest.approx(out["pv_explicit"] + out["pv_terminal"])
    assert sum(r["pv_fcff"] for r in out["rows"]) == pytest.approx(out["pv_explicit"])
    assert out["equity_value"] == pytest.approx(
        out["enterprise_value"] + a["cash"] + a["lt_investments"] - a["debt"] - a["minority"])
    assert out["per_share_fye"] == pytest.approx(out["equity_value"] / a["shares"])
    assert out["ronic_used"] == a["wacc"]
    assert out["rows"][-1]["growth"] == pytest.approx(a["growth_terminal"])
    assert 0 < out["terminal_share"] < 1


def test_run_dcf_requires_every_assumption():
    a = base_dcf()
    del a["wacc"]
    with pytest.raises(KeyError):
        dcf.run_dcf(a)


def test_untied_ronic_is_used_as_given():
    a = base_dcf()
    a["ronic_tied"] = False
    a["terminal_ronic"] = 0.20
    out = dcf.run_dcf(a)
    assert out["ronic_used"] == 0.20
    assert out["terminal"]["reinvestment_rate"] == pytest.approx(0.05 / 0.20)


@given(w1=st.floats(0.07, 0.2), dw=st.floats(0.001, 0.05))
def test_value_falls_as_wacc_rises(w1, dw):
    a = base_dcf()
    a["wacc"] = w1
    high = dcf.run_dcf(a)["per_share"]
    a["wacc"] = w1 + dw
    assert dcf.run_dcf(a)["per_share"] < high


@given(m1=st.floats(0.05, 0.4), dm=st.floats(0.001, 0.1))
def test_value_rises_with_margin(m1, dm):
    a = base_dcf()
    a["margin_target"] = m1
    low = dcf.run_dcf(a)["per_share"]
    a["margin_target"] = m1 + dm
    assert dcf.run_dcf(a)["per_share"] > low


def test_sensitivity_grid_centre_matches_base_case():
    a = base_dcf()
    waccs = [0.10, 0.11, 0.12]
    gs = [0.04, 0.05, 0.06]
    grid = dcf.sensitivity(a, "wacc", waccs, "growth_terminal", gs)
    assert grid[1][1] == pytest.approx(dcf.run_dcf(a)["per_share"])
    assert all(grid[r][0] > grid[r][2] for r in range(3))


def test_sensitivity_marks_undefined_cells():
    a = base_dcf()
    grid = dcf.sensitivity(a, "wacc", [0.05, 0.11], "growth_terminal", [0.05])
    assert grid[0][0] is None and grid[0][1] is not None


@settings(max_examples=50, deadline=None)
@given(g=st.floats(0.02, 0.30))
def test_reverse_dcf_recovers_the_growth_that_produced_the_price(g):
    a = base_dcf()
    a["growth_start"] = g
    price = dcf.run_dcf(a)["per_share"]
    a["growth_start"] = 0.10
    assert dcf.implied_growth(a, price) == pytest.approx(g, abs=1e-8)


@settings(max_examples=50, deadline=None)
@given(m=st.floats(0.05, 0.5))
def test_reverse_dcf_recovers_the_margin_that_produced_the_price(m):
    a = base_dcf()
    a["margin_target"] = m
    price = dcf.run_dcf(a)["per_share"]
    a["margin_target"] = 0.2
    assert dcf.implied_margin(a, price) == pytest.approx(m, abs=1e-8)


def test_reverse_dcf_returns_none_when_price_is_unreachable():
    assert dcf.implied_growth(base_dcf(), 1e12) is None
