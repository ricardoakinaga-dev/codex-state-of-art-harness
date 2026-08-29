"""Reproducible local benchmarks for the bounded Phase 3 host boundary."""

from __future__ import annotations

import platform
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from .phase3_discovery import CapabilityDiscovery
from .phase3_host import CodexHostAdapter
from .phase3_integration import Phase3RouterBridge
from .phase3_loader import SafeCapabilityLoader
from .phase3_models import DisclosureLevel, Phase3Limits
from .phase3_parser import parse_skill_bytes
from .phase3_resolution import ResolutionEngine

PHASE3_BENCHMARK_SCHEMA_VERSION = "P3-BENCH-1"
PHASE3_BENCHMARK_OPERATIONS = (
    "host_snapshot",
    "root_discovery",
    "package_discovery",
    "parse",
    "manifest_synthesis",
    "duplicate_analysis",
    "compatibility",
    "trust",
    "registry_bridge",
    "load_plan",
)


def _measure(operation: Callable[[], object], iterations: int) -> dict[str, int]:
    operation()
    samples: list[int] = []
    started = time.perf_counter_ns()
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


def _write_fixture(root: Path, capability_count: int) -> bytes:
    payload = (
        "---\n"
        "name: {name}\n"
        "description: bounded Phase 3 benchmark fixture\n"
        "version: 1.0.0\n"
        "do_not_activate_when: never\n"
        "---\n"
        "# Declarative fixture\n"
        "This content is benchmark input, never executable.\n"
    )
    first_payload = b""
    for index in range(capability_count):
        name = f"phase3-cap-{index:03d}"
        content = payload.format(name=name).encode("utf-8")
        (root / name).mkdir()
        (root / name / "SKILL.md").write_bytes(content)
        if index == 0:
            first_payload = content
    return first_payload


def run_phase3_benchmarks(*, iterations: int = 3, capability_count: int = 100) -> dict[str, object]:
    """Measure bounded Phase 3 operations over a temporary local fixture set."""

    for name, value in (("iterations", iterations), ("capability_count", capability_count)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    limits = Phase3Limits(
        max_capabilities=max(512, capability_count),
        max_total_files=max(4096, capability_count),
    )
    with TemporaryDirectory(prefix="harness-p3-benchmark-") as temporary:
        temporary_root = Path(temporary)
        project_root = temporary_root / "project"
        skill_root = project_root / ".agents" / "skills"
        home_dir = temporary_root / "home"
        project_root.mkdir(parents=True)
        skill_root.mkdir(parents=True)
        home_dir.mkdir()
        first_payload = _write_fixture(skill_root, capability_count)
        adapter = CodexHostAdapter(
            project_root=project_root,
            home_dir=home_dir,
            codex_home=home_dir / ".codex",
            limits=limits,
        )
        roots = adapter.discover_capability_roots()
        inventory = adapter.discover_capabilities(roots)
        discovery = CapabilityDiscovery(limits)
        engine = ResolutionEngine(limits)
        bridge = Phase3RouterBridge(limits)
        loader = SafeCapabilityLoader(limits)
        resolved = engine.resolve(inventory, "phase3-cap-000")
        selected = resolved.selected

        operations: dict[str, dict[str, int]] = {
            "host_snapshot": _measure(adapter.inspect_host, iterations),
            "root_discovery": _measure(adapter.discover_capability_roots, iterations),
            "package_discovery": _measure(lambda: adapter.discover_capabilities(roots), iterations),
            "parse": _measure(lambda: parse_skill_bytes(first_payload), iterations),
            "manifest_synthesis": _measure(lambda: discovery.scan(roots), iterations),
            "duplicate_analysis": _measure(lambda: engine.duplicate_report(inventory), iterations),
            "compatibility": _measure(
                lambda: tuple(item.compatibility for item in inventory.capabilities), iterations
            ),
            "trust": _measure(
                lambda: tuple(item.trust for item in inventory.capabilities), iterations
            ),
            "registry_bridge": _measure(
                lambda: bridge.registry(inventory.capabilities[:1]), iterations
            ),
            "load_plan": _measure(
                lambda: loader.plan(
                    ("phase3-cap-000",),
                    selected,
                    DisclosureLevel.ROUTING_METADATA,
                    blockers=resolved.blockers,
                    host_load_observable=False,
                ),
                iterations,
            ),
        }
        return {
            "schema_version": PHASE3_BENCHMARK_SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(aliased=True),
            "scope": "project-local bounded declarative fixtures only",
            "scenario": {
                "capability_count": capability_count,
                "root_count": len(roots),
                "fixture_kind": "temporary_synthetic_skill_packages",
            },
            "host": {
                "capability_count": len(inventory.capabilities),
                "root_count": len(inventory.roots),
                "inventory_errors": len(inventory.errors),
            },
            "iterations": iterations,
            "operations": operations,
            "limitations": (
                "Local process baseline only; this does not measure production latency, "
                "concurrency, provider latency, host loading, quality, causal impact or SLOs."
            ),
        }
