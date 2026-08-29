"""Small, non-SLO benchmarks for the bounded Phase 4 control plane."""

from __future__ import annotations

import math
import time
from collections.abc import Callable


def benchmark_operation(
    name: str,
    operation: Callable[[], object],
    *,
    iterations: int = 10,
) -> dict[str, object]:
    """Measure a deterministic control-plane operation without invoking a host."""

    if not isinstance(name, str) or not name or "\x00" in name:
        raise ValueError("benchmark name is invalid")
    if not isinstance(iterations, int) or isinstance(iterations, bool) or iterations < 1:
        raise ValueError("benchmark iterations must be positive")
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - started) * 1_000)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * 0.95) - 1))
    return {
        "name": name,
        "sample_count": len(samples),
        "unit": "milliseconds",
        "slo": "informational; no production performance claim",
        "min": round(ordered[0], 3),
        "median": round(ordered[len(ordered) // 2], 3),
        "p95": round(ordered[p95_index], 3),
        "max": round(ordered[-1], 3),
    }
