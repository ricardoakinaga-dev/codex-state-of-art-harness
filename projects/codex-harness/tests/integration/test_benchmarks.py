from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness_kernel.benchmarks import run_microbenchmarks, write_benchmark_report

FIXTURE = Path(__file__).parents[1] / "fixtures" / "golden" / "capability-manifest.json"


def test_phase1_benchmarks_cover_required_kernel_paths() -> None:
    report = run_microbenchmarks(FIXTURE, iterations=2)

    assert report["schema_version"] == "P1-BENCH-1"
    assert report["iterations"] == 2
    assert set(report["operations"]) == {
        "manifest_validation",
        "registry_loading",
        "route_validation",
        "state_transition",
        "telemetry_append",
    }
    for operation in report["operations"].values():
        assert operation["iterations"] == 2
        assert operation["duration_ns_total"] > 0
        assert operation["duration_ns_per_op"] > 0


def test_benchmark_report_is_json_and_rejects_invalid_iteration_count(tmp_path: Path) -> None:
    destination = tmp_path / "benchmark.json"

    report = write_benchmark_report(FIXTURE, destination, project_root=tmp_path, iterations=1)

    assert json.loads(destination.read_text(encoding="utf-8")) == report
    with pytest.raises(ValueError, match="iterations"):
        run_microbenchmarks(FIXTURE, iterations=0)


def test_benchmark_input_size_is_bounded(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"{" + b"a" * (2 * 1024 * 1024) + b"}")

    with pytest.raises(ValueError, match="size"):
        run_microbenchmarks(oversized, iterations=1)


def test_benchmark_report_destination_cannot_escape_project_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "benchmark-outside.json"

    with pytest.raises(ValueError, match="project_root"):
        write_benchmark_report(FIXTURE, outside, project_root=tmp_path, iterations=1)
