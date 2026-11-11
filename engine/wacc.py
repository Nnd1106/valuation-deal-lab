"""wacc.py: cost of capital (beta estimation, CAPM, synthetic rating, WACC)."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

# Synthetic rating table for large non-financial firms: interest coverage
# (EBIT / interest expense) lower bound -> (rating, default spread).
# Source: A. Damodaran, "Ratings, Interest Coverage Ratios and Default Spread",
# January 2026 update. Ordered from the highest coverage band down.
SYNTHETIC_RATING_TABLE: List[Tuple[float, str, float]] = [
    (8.50, "AAA", 0.0040),
    (6.50, "AA", 0.0055),
    (5.50, "A+", 0.0070),
    (4.25, "A", 0.0078),
    (3.00, "A-", 0.0089),
    (2.50, "BBB", 0.0111),
    (2.25, "BB+", 0.0138),
    (2.00, "BB", 0.0184),
    (1.75, "B+", 0.0275),
    (1.50, "B", 0.0321),
    (1.25, "B-", 0.0509),
    (0.80, "CCC", 0.0885),
    (0.65, "CC", 0.1261),
    (0.20, "C", 0.1600),
    (-math.inf, "D", 0.1900),
]


def beta_ols(asset_returns: Sequence[float], market_returns: Sequence[float]) -> Dict[str, float]:
    """OLS market-model regression r_asset = alpha + beta * r_market + e.

    Returns beta, alpha (per period), R squared, the standard error of beta
    and the number of observations.
    """
    n = len(asset_returns)
    if n != len(market_returns):
        raise ValueError("return series must have equal length")
    if n < 3:
        raise ValueError("need at least 3 observations")
    mean_a = sum(asset_returns) / n
    mean_m = sum(market_returns) / n
    sxx = sum((m - mean_m) ** 2 for m in market_returns)
    sxy = sum((m - mean_m) * (a - mean_a) for a, m in zip(asset_returns, market_returns))
    syy = sum((a - mean_a) ** 2 for a in asset_returns)
    if sxx / n < 1e-12:
        raise ValueError("market returns have (numerically) zero variance")
    beta = sxy / sxx
    alpha = mean_a - beta * mean_m
    sse = max(syy - beta * sxy, 0.0)
    r2 = 1.0 - sse / syy if syy > 0 else 0.0
    se = math.sqrt(sse / (n - 2) / sxx)
    return {"beta": beta, "alpha": alpha, "r2": r2, "se": se, "n": n}


def blume_adjust(raw_beta: float) -> float:
    """Blume adjustment toward the market beta of 1."""
    return 2.0 / 3.0 * raw_beta + 1.0 / 3.0


def unlever_beta(levered_beta: float, debt_to_equity: float, tax_rate: float) -> float:
    """Hamada: asset beta from an equity beta (debt beta assumed zero)."""
    return levered_beta / (1.0 + (1.0 - tax_rate) * debt_to_equity)


def relever_beta(unlevered_beta: float, debt_to_equity: float, tax_rate: float) -> float:
    """Hamada: equity beta at a target debt-to-equity ratio."""
    return unlevered_beta * (1.0 + (1.0 - tax_rate) * debt_to_equity)


def cost_of_equity(risk_free: float, beta: float, equity_risk_premium: float) -> float:
    """CAPM."""
    return risk_free + beta * equity_risk_premium


def synthetic_rating(interest_coverage: Optional[float],
                     table: Sequence[Tuple[float, str, float]] = SYNTHETIC_RATING_TABLE) -> Tuple[str, float]:
    """Map interest coverage to (rating, default spread).

    A firm with no interest expense (coverage None or infinite) maps to the
    top band.
    """
    if interest_coverage is None or math.isinf(interest_coverage):
        return table[0][1], table[0][2]
    for lower, rating, spread in table:
        if interest_coverage >= lower:
            return rating, spread
    return table[-1][1], table[-1][2]


def wacc(equity_value: float, debt_value: float, cost_equity: float,
         pretax_cost_debt: float, tax_rate: float) -> Dict[str, float]:
    """Weighted average cost of capital on market-value weights."""
    total = equity_value + debt_value
    if equity_value <= 0 or debt_value < 0 or total <= 0:
        raise ValueError("equity must be positive and debt non-negative")
    we = equity_value / total
    wd = debt_value / total
    after_tax_kd = pretax_cost_debt * (1.0 - tax_rate)
    return {
        "wacc": we * cost_equity + wd * after_tax_kd,
        "weight_equity": we,
        "weight_debt": wd,
        "after_tax_cost_debt": after_tax_kd,
    }


def median(values: Sequence[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        raise ValueError("median of empty sequence")
    mid = n // 2
    return s[mid] if n % 2 else 0.5 * (s[mid - 1] + s[mid])
