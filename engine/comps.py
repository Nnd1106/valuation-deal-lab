"""comps.py: trading multiples and peer-implied values.

Enterprise value is defined consistently with the operating metrics it is
divided by: EBITDA and EBIT exclude investment income, so EV excludes the
cash and financial investments that generate it.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

EV_MULTIPLES = {"ev_ebitda": "ebitda", "ev_ebit": "ebit", "ev_sales": "revenue"}
EQUITY_MULTIPLES = ("pe", "pb")
ALL_MULTIPLES = tuple(EV_MULTIPLES) + EQUITY_MULTIPLES


def enterprise_value(market_cap: float, debt: float, minority: float,
                     cash: float, lt_investments: float) -> float:
    return market_cap + debt + minority - cash - lt_investments


def _ratio(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or den is None or den <= 0 or num <= 0:
        return None
    return num / den


def multiples(c: Dict) -> Dict[str, Optional[float]]:
    """Trading multiples for one company.

    `c` needs: price, shares, debt, minority, cash, lt_investments, revenue,
    ebitda, ebit, eps, book_equity. A multiple is None when its numerator or
    denominator is not positive (not meaningful).
    """
    market_cap = c["price"] * c["shares"]
    ev = enterprise_value(market_cap, c["debt"], c["minority"], c["cash"], c["lt_investments"])
    bvps = c["book_equity"] / c["shares"] if c["shares"] > 0 else None
    return {
        "market_cap": market_cap,
        "enterprise_value": ev,
        "ev_ebitda": _ratio(ev, c["ebitda"]),
        "ev_ebit": _ratio(ev, c["ebit"]),
        "ev_sales": _ratio(ev, c["revenue"]),
        "pe": _ratio(c["price"], c["eps"]),
        "pb": _ratio(c["price"], bvps),
    }


def quantile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile (numpy default, type 7)."""
    s = sorted(values)
    if not s:
        raise ValueError("quantile of empty sequence")
    idx = q * (len(s) - 1)
    lo, hi = math.floor(idx), math.ceil(idx)
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (idx - lo)


def summary(values: Sequence[Optional[float]]) -> Optional[Dict[str, float]]:
    """Distribution of a multiple across peers, ignoring non-meaningful values."""
    v = [x for x in values if x is not None]
    if not v:
        return None
    return {
        "n": len(v), "min": min(v), "q1": quantile(v, 0.25), "median": quantile(v, 0.5),
        "q3": quantile(v, 0.75), "max": max(v), "mean": sum(v) / len(v),
    }


def implied_per_share(target: Dict, multiple: str, value: float) -> Optional[float]:
    """Per-share value of the target at a given peer multiple."""
    if value is None:
        return None
    if multiple in EV_MULTIPLES:
        metric = target[EV_MULTIPLES[multiple]]
        if metric is None or metric <= 0:
            return None
        equity = (value * metric - target["debt"] - target["minority"]
                  + target["cash"] + target["lt_investments"])
        return equity / target["shares"]
    if multiple == "pe":
        return value * target["eps"] if target["eps"] and target["eps"] > 0 else None
    if multiple == "pb":
        bvps = target["book_equity"] / target["shares"]
        return value * bvps if bvps > 0 else None
    raise KeyError(multiple)


def peer_valuation(target: Dict, peers: List[Dict]) -> Dict[str, Optional[Dict]]:
    """For each multiple: the peer distribution and the target's implied
    per-share value at the peer first quartile, median and third quartile."""
    peer_multiples = [multiples(p) for p in peers]
    out = {}
    for m in ALL_MULTIPLES:
        stats = summary([pm[m] for pm in peer_multiples])
        if stats is None:
            out[m] = None
            continue
        out[m] = {
            "stats": stats,
            "implied_low": implied_per_share(target, m, stats["q1"]),
            "implied_mid": implied_per_share(target, m, stats["median"]),
            "implied_high": implied_per_share(target, m, stats["q3"]),
        }
    return out
