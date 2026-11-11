"""Time-value primitives and cost of capital against closed forms."""

import math

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from engine import fin, wacc


def test_npv_matches_hand_calculation():
    assert fin.npv(0.10, [-100, 60, 60]) == pytest.approx(-100 + 60 / 1.1 + 60 / 1.21)


def test_npv_with_fractional_times():
    assert fin.npv(0.08, [100.0], [2.5]) == pytest.approx(100 / 1.08 ** 2.5)


@given(rate=st.one_of(st.just(0.0), st.floats(1e-6, 0.5)), n=st.integers(1, 30), c=st.floats(1.0, 1e6))
def test_annuity_closed_form(rate, n, c):
    pv = fin.npv(rate, [0.0] + [c] * n)
    # expm1/log1p keep the textbook annuity formula accurate at small rates
    expected = c * n if rate == 0 else c * -math.expm1(-n * math.log1p(rate)) / rate
    assert pv == pytest.approx(expected, rel=1e-9)


@given(r=st.floats(-0.5, 3.0), n=st.integers(1, 15), stake=st.floats(1.0, 1e6))
def test_irr_recovers_zero_coupon_rate(r, n, stake):
    flows = [-stake] + [0.0] * (n - 1) + [stake * (1 + r) ** n]
    assert fin.irr(flows) == pytest.approx(r, abs=1e-9)


@given(r=st.floats(0.01, 0.6), n=st.integers(2, 12))
def test_npv_at_irr_is_zero(r, n):
    flows = [-1000.0] + [1000.0 * r] * (n - 1) + [1000.0 * (1 + r)]
    found = fin.irr(flows)
    assert found == pytest.approx(r, abs=1e-9)
    assert fin.npv(found, flows) == pytest.approx(0.0, abs=1e-6)


def test_irr_none_without_sign_change():
    assert fin.irr([100.0, 50.0, 25.0]) is None
    assert fin.irr([-100.0, -50.0]) is None


def test_cagr():
    assert fin.cagr(100.0, 133.1, 3) == pytest.approx(0.10)
    assert fin.cagr(0.0, 100.0, 3) is None
    assert fin.cagr(100.0, 120.0, 0) is None


def test_bisect_root():
    assert fin.bisect_root(lambda x: x ** 3 - 8, 0, 10) == pytest.approx(2.0, abs=1e-10)
    assert fin.bisect_root(lambda x: x ** 2 + 1, -5, 5) is None


# ---------------------------------------------------------------- beta

def test_beta_exact_linear_relationship():
    market = [0.01, -0.02, 0.03, 0.005, -0.015, 0.02]
    asset = [0.002 + 1.3 * m for m in market]
    out = wacc.beta_ols(asset, market)
    assert out["beta"] == pytest.approx(1.3)
    assert out["alpha"] == pytest.approx(0.002)
    assert out["r2"] == pytest.approx(1.0)
    assert out["se"] == pytest.approx(0.0, abs=1e-9)
    assert out["n"] == 6


@settings(max_examples=50, deadline=None)
@given(seed=st.integers(0, 10_000), n=st.integers(30, 300), true_beta=st.floats(-0.5, 2.5))
def test_beta_matches_numpy_least_squares(seed, n, true_beta):
    rng = np.random.default_rng(seed)
    market = rng.normal(0.002, 0.02, n)
    asset = 0.001 + true_beta * market + rng.normal(0, 0.015, n)
    out = wacc.beta_ols(list(asset), list(market))
    slope, intercept = np.polyfit(market, asset, 1)
    assert out["beta"] == pytest.approx(slope, rel=1e-8, abs=1e-10)
    assert out["alpha"] == pytest.approx(intercept, rel=1e-8, abs=1e-10)
    assert out["r2"] == pytest.approx(np.corrcoef(market, asset)[0, 1] ** 2, rel=1e-8, abs=1e-10)
    resid = asset - (intercept + slope * market)
    se = math.sqrt(resid @ resid / (n - 2) / ((market - market.mean()) ** 2).sum())
    assert out["se"] == pytest.approx(se, rel=1e-6)


def test_beta_rejects_bad_input():
    with pytest.raises(ValueError):
        wacc.beta_ols([0.1, 0.2], [0.1, 0.2])
    with pytest.raises(ValueError):
        wacc.beta_ols([0.1, 0.2, 0.3], [0.1, 0.1, 0.1])
    with pytest.raises(ValueError):
        wacc.beta_ols([0.1, 0.2, 0.3], [0.1, 0.2])


def test_blume():
    assert wacc.blume_adjust(1.0) == pytest.approx(1.0)
    assert wacc.blume_adjust(1.6) == pytest.approx(1.4)
    assert wacc.blume_adjust(0.4) == pytest.approx(0.6)


@given(beta=st.floats(0.1, 3.0), de=st.floats(0.0, 5.0), tax=st.floats(0.0, 0.5))
def test_unlever_relever_round_trip(beta, de, tax):
    assert wacc.relever_beta(wacc.unlever_beta(beta, de, tax), de, tax) == pytest.approx(beta)


def test_unlevered_beta_below_levered_when_debt_present():
    assert wacc.unlever_beta(1.2, 0.5, 0.25) == pytest.approx(1.2 / 1.375)
    assert wacc.unlever_beta(1.2, 0.0, 0.25) == pytest.approx(1.2)


# ---------------------------------------------------------------- rating and WACC

@pytest.mark.parametrize("coverage,rating", [
    (100.0, "AAA"), (8.5, "AAA"), (8.49, "AA"), (6.5, "AA"), (6.49, "A+"), (5.5, "A+"),
    (4.25, "A"), (3.0, "A-"), (2.5, "BBB"), (2.25, "BB+"), (2.0, "BB"), (1.75, "B+"),
    (1.5, "B"), (1.25, "B-"), (0.8, "CCC"), (0.65, "CC"), (0.2, "C"), (0.19, "D"), (-3.0, "D"),
])
def test_synthetic_rating_boundaries(coverage, rating):
    assert wacc.synthetic_rating(coverage)[0] == rating


def test_synthetic_rating_no_interest_is_top_band():
    assert wacc.synthetic_rating(None) == ("AAA", 0.0040)
    assert wacc.synthetic_rating(math.inf) == ("AAA", 0.0040)


def test_rating_spreads_never_fall_as_coverage_falls():
    spreads = [s for _, _, s in wacc.SYNTHETIC_RATING_TABLE]
    assert spreads == sorted(spreads)
    lowers = [l for l, _, _ in wacc.SYNTHETIC_RATING_TABLE]
    assert lowers == sorted(lowers, reverse=True)


def test_wacc_hand_calculation():
    out = wacc.wacc(800.0, 200.0, 0.12, 0.08, 0.25)
    assert out["wacc"] == pytest.approx(0.8 * 0.12 + 0.2 * 0.08 * 0.75)
    assert out["weight_equity"] + out["weight_debt"] == pytest.approx(1.0)


@given(e=st.floats(1.0, 1e7), d=st.floats(0.0, 1e7), ke=st.floats(0.05, 0.3),
       kd=st.floats(0.01, 0.2), tax=st.floats(0.0, 0.5))
def test_wacc_lies_between_component_costs(e, d, ke, kd, tax):
    out = wacc.wacc(e, d, ke, kd, tax)
    lo, hi = sorted([ke, kd * (1 - tax)])
    assert lo - 1e-12 <= out["wacc"] <= hi + 1e-12


def test_wacc_all_equity_equals_cost_of_equity():
    assert wacc.wacc(500.0, 0.0, 0.13, 0.09, 0.25)["wacc"] == pytest.approx(0.13)


def test_wacc_rejects_non_positive_equity():
    with pytest.raises(ValueError):
        wacc.wacc(0.0, 100.0, 0.12, 0.08, 0.25)


def test_capm():
    assert wacc.cost_of_equity(0.0525, 1.1, 0.0708) == pytest.approx(0.0525 + 1.1 * 0.0708)


def test_median():
    assert wacc.median([3, 1, 2]) == 2
    assert wacc.median([4, 1, 3, 2]) == 2.5
    with pytest.raises(ValueError):
        wacc.median([])
