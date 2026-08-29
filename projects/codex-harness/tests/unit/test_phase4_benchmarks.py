from __future__ import annotations

import pytest

from harness_kernel.phase4_benchmarks import benchmark_operation


def test_benchmark_operation_reports_bounded_samples() -> None:
    result = benchmark_operation("control-plane", lambda: None, iterations=10)

    assert result["sample_count"] == 10
    assert result["unit"] == "milliseconds"
    assert float(result["p95"]) >= 0


def test_benchmark_operation_rejects_unbounded_arguments() -> None:
    with pytest.raises(ValueError):
        benchmark_operation("control-plane", lambda: None, iterations=0)
    with pytest.raises(ValueError):
        benchmark_operation("", lambda: None)
