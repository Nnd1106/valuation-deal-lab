"""gates.py: data-quality and model-integrity gates.

A gate is a named yes/no check with a severity:
  fail  the company is excluded from the published data
  warn  the company is published with the issue disclosed next to its numbers

The build exits non-zero (so nothing is committed and the last good data
stays live) when too few companies survive, a peer group gets too thin, or
any engine invariant breaks.
"""

from __future__ import annotations

import math
from typing import Dict, List


class Gates:
    def __init__(self) -> None:
        self.results: List[Dict] = []

    def check(self, gate_id: str, ok: bool, detail: str, level: str = "fail") -> bool:
        self.results.append({"id": gate_id, "level": level, "ok": bool(ok), "detail": detail})
        return bool(ok)

    @property
    def failed(self) -> List[Dict]:
        return [r for r in self.results if r["level"] == "fail" and not r["ok"]]

    @property
    def warnings(self) -> List[Dict]:
        return [r for r in self.results if r["level"] == "warn" and not r["ok"]]

    @property
    def passed(self) -> bool:
        return not self.failed


def finite(*values) -> bool:
    return all(v is not None and isinstance(v, (int, float)) and math.isfinite(v) for v in values)


def close(a: float, b: float, rel: float = 1e-9, abs_tol: float = 1e-9) -> bool:
    return finite(a, b) and abs(a - b) <= max(abs_tol, rel * max(abs(a), abs(b)))
