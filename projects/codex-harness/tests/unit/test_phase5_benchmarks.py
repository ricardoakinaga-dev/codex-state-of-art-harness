from __future__ import annotations

import pytest

from harness_kernel.phase5_benchmarks import (
    Phase5BenchmarkError,
    compare_compositions,
)


def test_benchmark_is_explicitly_pilot_evidence_and_reports_deltas() -> None:
    report = compare_compositions(
        baseline_score=61,
        composition_score=88,
        baseline_defects=4,
        composition_defects=1,
        baseline_latency_ms=12,
        composition_latency_ms=38,
        builder_invocations=1,
        verifier_invocations=1,
        critic_invocations=1,
        repair_invocations=0,
        baseline_reviewer="NATIVE_MINIMAL",
        composition_reviewer="INDEPENDENT_BLIND_CRITIC",
    )
    assert report["evidence_label"] == "PILOT_COMPOSITION_EVIDENCE"
    assert report["delta"] == {"score": 27.0, "defects_reduced": 3, "latency_ms": 26}


def test_benchmark_rejects_unbounded_or_causal_claims() -> None:
    with pytest.raises(Phase5BenchmarkError):
        compare_compositions(
            baseline_score=61,
            composition_score=88,
            baseline_defects=4,
            composition_defects=1,
            baseline_latency_ms=12,
            composition_latency_ms=38,
            builder_invocations=3,
            verifier_invocations=1,
            critic_invocations=1,
            repair_invocations=0,
            baseline_reviewer="NATIVE_MINIMAL",
            composition_reviewer="INDEPENDENT_BLIND_CRITIC",
        )
