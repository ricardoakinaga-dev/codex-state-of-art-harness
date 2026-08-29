"""Bounded pilot-composition comparison records for Phase 5 evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


class Phase5BenchmarkError(ValueError):
    """Raised when a pilot comparison is incomplete or unbounded."""


@dataclass(frozen=True, slots=True)
class CompositionBenchmark:
    benchmark_id: str
    evidence_label: str
    baseline_score: float
    composition_score: float
    baseline_defects: int
    composition_defects: int
    baseline_latency_ms: int
    composition_latency_ms: int
    builder_invocations: int
    verifier_invocations: int
    critic_invocations: int
    repair_invocations: int
    baseline_reviewer: str
    composition_reviewer: str

    def __post_init__(self) -> None:
        if not self.benchmark_id or "\x00" in self.benchmark_id:
            raise Phase5BenchmarkError("benchmark_id is invalid")
        if self.evidence_label != "PILOT_COMPOSITION_EVIDENCE":
            raise Phase5BenchmarkError("pilot comparison must use the evidence label")
        for name in ("baseline_score", "composition_score"):
            value = getattr(self, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not 0 <= value <= 100
            ):
                raise Phase5BenchmarkError(f"{name} must be between 0 and 100")
        for name in (
            "baseline_defects",
            "composition_defects",
            "baseline_latency_ms",
            "composition_latency_ms",
            "builder_invocations",
            "verifier_invocations",
            "critic_invocations",
            "repair_invocations",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise Phase5BenchmarkError(f"{name} must be a non-negative integer")
        if self.builder_invocations > 2 or self.verifier_invocations > 2:
            raise Phase5BenchmarkError("benchmark exceeds the Phase 5 invocation budget")
        if self.critic_invocations > 2 or self.repair_invocations > 1:
            raise Phase5BenchmarkError("benchmark exceeds the Phase 5 review budget")
        if not self.baseline_reviewer or not self.composition_reviewer:
            raise Phase5BenchmarkError("independent reviewer identities are required")

    @property
    def score_delta(self) -> float:
        return float(self.composition_score - self.baseline_score)

    @property
    def defect_delta(self) -> int:
        return self.baseline_defects - self.composition_defects

    @property
    def latency_delta_ms(self) -> int:
        return self.composition_latency_ms - self.baseline_latency_ms

    def as_mapping(self) -> Mapping[str, object]:
        return MappingProxyType(
            {
                "benchmark_id": self.benchmark_id,
                "evidence_label": self.evidence_label,
                "baseline": {
                    "score": self.baseline_score,
                    "defects": self.baseline_defects,
                    "latency_ms": self.baseline_latency_ms,
                    "reviewer": self.baseline_reviewer,
                },
                "composition": {
                    "score": self.composition_score,
                    "defects": self.composition_defects,
                    "latency_ms": self.composition_latency_ms,
                    "reviewer": self.composition_reviewer,
                    "builder_invocations": self.builder_invocations,
                    "verifier_invocations": self.verifier_invocations,
                    "critic_invocations": self.critic_invocations,
                    "repair_invocations": self.repair_invocations,
                },
                "delta": {
                    "score": self.score_delta,
                    "defects_reduced": self.defect_delta,
                    "latency_ms": self.latency_delta_ms,
                },
                "interpretation": (
                    "Pilot evidence compares this bounded composition with a native minimal "
                    "baseline; "
                    "it is not causal proof or a production benchmark."
                ),
            }
        )


def compare_compositions(
    *,
    baseline_score: float,
    composition_score: float,
    baseline_defects: int,
    composition_defects: int,
    baseline_latency_ms: int,
    composition_latency_ms: int,
    builder_invocations: int,
    verifier_invocations: int,
    critic_invocations: int,
    repair_invocations: int,
    baseline_reviewer: str,
    composition_reviewer: str,
    benchmark_id: str = "P5-BENCH-1",
) -> Mapping[str, object]:
    """Return a bounded comparison and explicitly label its evidentiary limits."""

    return CompositionBenchmark(
        benchmark_id=benchmark_id,
        evidence_label="PILOT_COMPOSITION_EVIDENCE",
        baseline_score=baseline_score,
        composition_score=composition_score,
        baseline_defects=baseline_defects,
        composition_defects=composition_defects,
        baseline_latency_ms=baseline_latency_ms,
        composition_latency_ms=composition_latency_ms,
        builder_invocations=builder_invocations,
        verifier_invocations=verifier_invocations,
        critic_invocations=critic_invocations,
        repair_invocations=repair_invocations,
        baseline_reviewer=baseline_reviewer,
        composition_reviewer=composition_reviewer,
    ).as_mapping()
