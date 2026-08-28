"""Small, local Phase 1 performance baselines.

The benchmark runner measures contract operations only.  It loads declarative
manifest data, builds immutable snapshots, and never imports or executes a
capability, provider, tool, or user supplied module.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from .authority import AuthorityAction, AuthorityScope
from .boundary import ProjectBoundary
from .classification import classify_task
from .execution import ExecutionKernel
from .graph import validate_execution_graph
from .models import (
    CapabilityManifest,
    ExecutionGraph,
    ExecutionNode,
    GraphStatus,
    InvocationStatus,
    LifecycleState,
    NodeBudget,
    NodeKind,
    Provenance,
    RecordEnvelope,
    RecordStatus,
    SchemaVersion,
    SourceType,
    TelemetryEventType,
)
from .providers import DeterministicSuccessProvider, ProviderRegistry
from .registry import CapabilityRegistry
from .routing import minimum_route
from .serialization import from_json, to_dict, to_json
from .state import can_transition
from .telemetry import TelemetryLog, create_event
from .validation import validate

MAX_MANIFEST_BYTES = 1 * 1024 * 1024
BENCHMARK_SCHEMA_VERSION = "P1-BENCH-1"
PHASE2_BENCHMARK_SCHEMA_VERSION = "P2-BENCH-1"
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
    resolved_root, relative = _project_relative_destination(project_root, destination)
    ProjectBoundary(resolved_root).atomic_write_bytes(
        relative,
        (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return report


PHASE2_REQUIRED_OPERATIONS = (
    "classification",
    "registry_admission",
    "route_selection",
    "graph_validation_10",
    "graph_validation_100",
    "provider_fixture_execution",
    "serialization",
    "evidence_write",
    "telemetry_append",
)


def _phase2_graph(node_count: int) -> ExecutionGraph:
    timestamp = "2026-08-28T12:00:00Z"
    nodes = tuple(
        ExecutionNode(
            node_id=f"NODE-{index:03d}",
            kind=NodeKind.TOOL,
            capability_id="local.direct",
            owner="phase2-benchmark",
            input_refs=(),
            output_contract="LocalExecutionResult",
            depends_on=(f"NODE-{index - 1:03d}",) if index else (),
            can_parallelize=False,
            required=True,
            budget=NodeBudget(tokens=1, duration_ms=1),
            acceptance_refs=("P2-BENCHMARK",),
            provider_id="local.success",
            node_status=InvocationStatus.REQUESTED,
        )
        for index in range(node_count)
    )
    return ExecutionGraph(
        schema_version=SchemaVersion.EXECUTION_GRAPH,
        graph_id=f"GRAPH-BENCH-{node_count}",
        task_id="TASK-BENCHMARK-P2",
        run_id=f"RUN-BENCHMARK-P2-{node_count}",
        record=RecordEnvelope(
            status=RecordStatus.CURRENT,
            provenance=Provenance(SourceType.GENERATED, ("phase2-benchmark",), timestamp),
        ),
        goal="measure bounded graph validation",
        nodes=nodes,
        edges=(),
        merge_points=(),
        graph_status=GraphStatus.READY,
        stop_policy_ref="STOP-P2-BENCHMARK",
        created_at=timestamp,
        graph_owner="phase2-benchmark",
        graph_budget=NodeBudget(tokens=node_count, duration_ms=node_count),
        acceptance_refs=("P2-BENCHMARK",),
    )


def run_phase2_benchmarks(manifest_path: Path, *, iterations: int = 10) -> dict[str, object]:
    """Measure bounded Phase 2 kernel paths without host or network execution."""

    if not isinstance(iterations, int) or isinstance(iterations, bool) or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    manifest = _load_manifest(manifest_path)
    profile = classify_task(
        "Execute a deterministic local provider and validate its evidence",
        requested_outcome="A bounded local execution result",
        task_id="TASK-BENCHMARK-P2",
        run_id="RUN-BENCHMARK-P2",
        evidence_refs=("EVID-BENCHMARK-P2",),
        source_refs=(str(manifest_path),),
        created_at="2026-08-28T12:00:00Z",
    )
    providers = ProviderRegistry.local_defaults()
    graph_10 = _phase2_graph(10)
    graph_100 = _phase2_graph(100)
    with TemporaryDirectory(prefix="harness-p2-benchmark-") as temporary:
        boundary = ProjectBoundary(Path(temporary))
        kernel = ExecutionKernel(boundary, providers=providers)
        runtime = kernel.run(
            profile,
            provider_id="local.success",
            authority=AuthorityScope(
                owner="benchmark-policy",
                actor="benchmark-runner",
                scopes=(
                    f"task:{profile.task_id}",
                    "capability:local.success",
                ),
                decisions=(AuthorityAction.TRANSITION,),
                subject_owner="benchmark-policy",
                operations=("execute",),
                issued_at="1970-01-01T00:00:00Z",
                expires_at="2099-12-31T23:59:59Z",
            ),
            persist=False,
        )
        provider = DeterministicSuccessProvider()
        invocation = runtime.invocations[0]
        event = create_event(
            event_id="EVT-BENCHMARK-P2",
            event_sequence=1,
            timestamp="2026-08-28T12:00:00Z",
            task_id=profile.task_id,
            run_id=profile.run_id,
            event_type=TelemetryEventType.TASK_RECEIVED,
        )
        telemetry = TelemetryLog()

        operations: dict[str, dict[str, int]] = {
            "classification": _measure(
                lambda: classify_task(
                    profile.objective,
                    profile.requested_outcome,
                    task_id=profile.task_id,
                    run_id=profile.run_id,
                    created_at="2026-08-28T12:00:00Z",
                ),
                iterations,
            ),
            "registry_admission": _measure(lambda: ProviderRegistry.local_defaults(), iterations),
            "route_selection": _measure(
                lambda: minimum_route(
                    profile, CapabilityRegistry(), decision_id="ROUTE-P2-MEASURE"
                ),
                iterations,
            ),
            "graph_validation_10": _measure(
                lambda: validate_execution_graph(graph_10, max_nodes=128), iterations
            ),
            "graph_validation_100": _measure(
                lambda: validate_execution_graph(graph_100, max_nodes=128), iterations
            ),
            "provider_fixture_execution": _measure(
                lambda: provider.execute(invocation), iterations
            ),
            "serialization": _measure(
                lambda: from_json(to_json(profile), type(profile)), iterations
            ),
            "evidence_write": _measure(
                lambda: boundary.atomic_write_json(
                    ".harness/evidence/benchmark-p2.json",
                    {
                        "run_id": profile.run_id,
                        "evidence": [to_dict(item) for item in runtime.evidence],
                    },
                ),
                iterations,
            ),
            "telemetry_append": _measure(lambda: telemetry.append(event), iterations),
        }
    return {
        "schema_version": PHASE2_BENCHMARK_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(aliased=True),
        "manifest": manifest.capability_id,
        "iterations": iterations,
        "operations": operations,
        "required_operations": list(PHASE2_REQUIRED_OPERATIONS),
        "scope": "project-local deterministic fixtures only",
        "limitations": (
            "Local microbenchmark baseline only; it does not measure production latency, "
            "quality, causal impact, external providers, host load, concurrency, or SLOs."
        ),
    }


def write_phase2_benchmark_report(
    manifest_path: Path,
    destination: Path,
    *,
    project_root: Path,
    iterations: int = 10,
) -> dict[str, object]:
    """Write the Phase 2 benchmark atomically inside the declared project root."""

    report = run_phase2_benchmarks(manifest_path, iterations=iterations)
    root, relative = _project_relative_destination(project_root, destination)
    ProjectBoundary(root).atomic_write_json(relative, report)
    return report


def _project_relative_destination(project_root: Path, destination: Path) -> tuple[Path, str]:
    """Resolve a destination lexically while leaving symlink checks to the boundary."""

    try:
        root = project_root.resolve(strict=True)
        candidate = destination if destination.is_absolute() else root / destination
        if any(part == ".." for part in candidate.parts):
            raise ValueError("parent traversal is not allowed")
        lexical = Path(os.path.abspath(candidate))
        relative = lexical.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("benchmark destination must remain inside project_root") from exc
    if not relative.parts:
        raise ValueError("benchmark destination must be a file")
    return root, relative.as_posix()
