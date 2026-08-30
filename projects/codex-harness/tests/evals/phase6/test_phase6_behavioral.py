from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]


def test_phase6_catalog_is_behaviorally_executed(tmp_path: Path) -> None:
    output = tmp_path / "phase6-eval-execution.json"
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "run_phase6_evals.py"),
            "--project-root",
            str(PROJECT_ROOT),
            "--output",
            str(output),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["execution_scope"] == "FULL_CATALOG"
    assert report["behavioral_execution"] == "FULL_CATALOG"
    assert report["negative_case_execution"] == "FULL_CATALOG"
    assert report["scenario_count"] == 40
    assert report["passed_scenarios"] == 40
    assert report["critical_false_pass_count"] == 0
    assert report["critical_oracle_mismatch_count"] == 0
    assert all(item["passed"] for item in report["records"])
