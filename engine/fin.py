"""fin.py: time-value primitives shared by every model."""

from __future__ import annotations

import math
from typing import Optional, Sequence


def npv(rate: float, cashflows: Sequence[float], times: Optional[Sequence[float]] = None) -> float:
    """Present value of cashflows at the given times (default 0, 1, 2, ...)."""
    if rate <= -1.0:
        raise ValueError("rate must be greater than -100%")
    if times is None:
        times = range(len(cashflows))
    return sum(cf / (1.0 + rate) ** t for cf, t in zip(cashflows, times))


def irr(cashflows: Sequence[float], times: Optional[Sequence[float]] = None,
        lo: float = -0.99, hi: float = 100.0) -> Optional[float]:
    """Internal rate of return by bisection.

    Returns None when NPV does not change sign on [lo, hi], which covers
    all-positive or all-negative flows. For conventional flows (one sign
    change) the root is unique, so bisection finds the IRR.
    """
    if times is None:
        times = list(range(len(cashflows)))
    f_lo = npv(lo, cashflows, times)
    f_hi = npv(hi, cashflows, times)
    if not (math.isfinite(f_lo) and math.isfinite(f_hi)) or f_lo * f_hi > 0:
        return None
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        f_mid = npv(mid, cashflows, times)
        if f_mid == 0 or (hi - lo) < 1e-14:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)


def cagr(first: float, last: float, years: float) -> Optional[float]:
    """Compound annual growth rate; None when undefined."""
    if first is None or last is None or years <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1.0 / years) - 1.0


def bisect_root(fn, lo: float, hi: float, iterations: int = 200) -> Optional[float]:
    """Root of fn on [lo, hi] by bisection; None without a sign change."""
    f_lo, f_hi = fn(lo), fn(hi)
    if not (math.isfinite(f_lo) and math.isfinite(f_hi)) or f_lo * f_hi > 0:
        return None
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        f_mid = fn(mid)
        if f_mid == 0 or (hi - lo) < 1e-14:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)
