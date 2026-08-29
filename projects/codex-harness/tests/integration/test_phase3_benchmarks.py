from __future__ import annotations

from harness_kernel.phase3_benchmarks import run_phase3_benchmarks


def test_phase3_benchmark_runner_covers_a_bounded_100_capability_scenario() -> None:
    report = run_phase3_benchmarks(iterations=1, capability_count=100)

    assert report["schema_version"] == "P3-BENCH-1"
    assert report["scope"] == "project-local bounded declarative fixtures only"
    assert report["scenario"]["capability_count"] == 100
    assert set(report["operations"]) == {
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
    }
    for operation in report["operations"].values():
        assert operation["iterations"] == 1
        assert operation["duration_ns_total"] > 0
