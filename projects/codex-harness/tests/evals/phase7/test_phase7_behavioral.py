from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_phase7_evals  # noqa: E402


def test_phase7_catalog_executes_every_scenario_and_known_bad_guard(tmp_path: Path) -> None:
    output = tmp_path / "phase7-eval-execution.json"
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "run_phase7_evals.py"),
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
    assert report["behavioral_execution"] == "DETERMINISTIC_CONTRACT_OBSERVERS"
    assert report["known_bad_execution"] == "SCHEMA_GUARD_ONLY"
    assert report["scenario_count"] == 48
    assert report["passed_scenarios"] == 48
    assert report["critical_false_pass_count"] == 0
    assert report["critical_oracle_mismatch_count"] == 0
    assert report["causal_claim"] is False
    assert all(item["oracle_passed"] for item in report["records"])
    assert all(item["known_bad"]["validator_rejected"] for item in report["records"])
    assert all(item["known_bad"]["fixture_applied"] for item in report["records"])
    assert all(item["known_bad"]["guard_triggered"] for item in report["records"])
    assert all(item["observation"]["scenario_input_consumed"] for item in report["records"])
    assert all(item["observation"]["scenario_oracle_consumed"] for item in report["records"])
    assert all(
        item["observation"]["input_digest"].startswith("sha256:") for item in report["records"]
    )
    assert all(item["observation"]["contract_metadata_consumed"] for item in report["records"])
    assert report["procedure_catalog_bound"] is True


def test_observer_uses_structured_task_identity_instead_of_scenario_id() -> None:
    catalog = json.loads(
        (
            PROJECT_ROOT
            / ".harness"
            / "capabilities"
            / "backend-engineering-vnext"
            / "evals"
            / "scenarios.json"
        ).read_text(encoding="utf-8")
    )
    scenario = deepcopy(next(item for item in catalog["scenarios"] if item["id"] == "P7-SC-007"))
    scenario["input_identity"] = "task:add-cache|scope:one-slow-read|artifact:service"
    scenario["input"] = {
        **scenario["input"],
        "task": "Caching request lacks evidence for adding a cache.",
        "scope": "overengineering",
        "artifact": scenario["input_identity"],
        "prompt": (
            "Evaluate the bounded backend task: Caching request lacks evidence for adding a cache."
        ),
    }

    signal = run_phase7_evals._scenario_input_signal(scenario)

    assert signal["task_key"] == "add-cache"
    assert signal["scope"] == "one-slow-read"
    assert signal["artifact"] == "service"
    assert signal["prompt_digest"].startswith("sha256:")
