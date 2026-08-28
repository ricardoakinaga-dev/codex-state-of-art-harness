"""Small, local Phase 1 performance baselines.

The benchmark runner measures contract operations only.  It loads declarative
manifest data, builds immutable snapshots, and never imports or executes a
capability, provider, tool, or user supplied module.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .classification import classify_task
from .models import CapabilityManifest, LifecycleState, TelemetryEventType
from .registry import CapabilityRegistry
from .routing import minimum_route
from .serialization import from_json
from .state import can_transition
from .telemetry import TelemetryLog, create_event
from .validation import validate

MAX_MANIFEST_BYTES = 1 * 1024 * 1024
BENCHMARK_SCHEMA_VERSION = "P1-BENCH-1"
REQUIRED_OPERATIONS = (
    "manifest_validation",
    "registry_loading",
    "route_validation",
    "state_transition",
    "telemetry_append",
)


def _load_manifest(path: Path) -> CapabilityManifest:
    if not path.is_file():
        raise ValueError("benchmark manifest path is not a regular file")
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("benchmark manifest exceeds size limit")
    try:
        payload = path.read_bytes()
        return from_json(payload, CapabilityManifest)
    except OSError as exc:
        raise ValueError("benchmark manifest could not be read") from exc


def _measure(operation: Callable[[], object], iterations: int) -> dict[str, int]:
    operation()
    started = time.perf_counter_ns()
    samples: list[int] = []
    for _ in range(iterations):
        sample_started = time.perf_counter_ns()
        operation()
        samples.append(max(1, time.perf_counter_ns() - sample_started))
    elapsed = max(1, time.perf_counter_ns() - started)
    ordered = sorted(samples)
    return {
        "iterations": iterations,
        "duration_ns_total": elapsed,
        "duration_ns_per_op": max(1, elapsed // iterations),
        "min_ns": ordered[0],
        "median_ns": ordered[len(ordered) // 2],
        "max_ns": ordered[-1],
    }


def run_microbenchmarks(manifest_path: Path, *, iterations: int = 100) -> dict[str, object]:
    """Run bounded baselines for the five required Phase 1 kernel paths."""

    if not isinstance(iterations, int) or isinstance(iterations, bool) or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    manifest = _load_manifest(manifest_path)
    profile = classify_task(
        "Validate a local capability manifest without executing it",
        requested_outcome="A deterministic validation result",
        task_id="TASK-BENCHMARK-1",
        run_id="RUN-BENCHMARK-1",
        evidence_refs=("EVID-BENCHMARK-INPUT",),
        source_refs=(str(manifest_path),),
        created_at="2026-08-28T12:00:00Z",
    )
    registry = CapabilityRegistry.from_manifests((manifest,))
    route = minimum_route(profile, registry, decision_id="ROUTE-BENCHMARK-1")
    event = create_event(
        event_id="EVT-BENCHMARK-1",
        event_sequence=1,
        timestamp="2026-08-28T12:00:00Z",
        task_id=profile.task_id,
        run_id=profile.run_id,
        event_type=TelemetryEventType.TASK_RECEIVED,
    )
    empty_log = TelemetryLog()

    operations: dict[str, dict[str, int]] = {
        "manifest_validation": _measure(lambda: validate(manifest), iterations),
        "registry_loading": _measure(
            lambda: CapabilityRegistry.from_manifests((manifest,)), iterations
        ),
        "route_validation": _measure(lambda: validate(route), iterations),
        "state_transition": _measure(
            lambda: can_transition(LifecycleState.NEW, LifecycleState.CLASSIFIED), iterations
        ),
        "telemetry_append": _measure(lambda: empty_log.append(event), iterations),
    }
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(aliased=True),
        "manifest": manifest.capability_id,
        "iterations": iterations,
        "operations": operations,
        "limitations": (
            "Local microbenchmark baseline only; it does not measure provider latency, "
            "quality, causal impact, or production SLOs."
        ),
    }


def write_benchmark_report(
    manifest_path: Path,
    destination: Path,
    *,
    project_root: Path,
    iterations: int = 100,
) -> dict[str, object]:
    """Run baselines and write a deterministic JSON shape inside ``project_root``."""

    report = run_microbenchmarks(manifest_path, iterations=iterations)
    try:
        resolved_root = project_root.resolve(strict=True)
        resolved_destination = destination.resolve(strict=False)
        resolved_destination.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("benchmark destination must remain inside project_root") from exc
    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    resolved_destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
