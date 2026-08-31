"""RED-first contract tests for the Phase 8 frontend specialist package."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / "frontend-engineering-vnext"


def _read_json(relative: str) -> dict[str, object]:
    return json.loads((PACKAGE_ROOT / relative).read_text(encoding="utf-8"))


def test_frontend_package_manifest_is_native_specialist_with_explicit_boundaries() -> None:
    manifest = _read_json("manifest.json")

    assert manifest["capability_id"] == "frontend-engineering-vnext"
    assert manifest["version"] == "0.1.0"
    assert manifest["type"] == "SPECIALIST"
    assert manifest["primary_type"] == "SPECIALIST"
    assert manifest["role"] == "SPECIALIST"
    assert "FRONTEND_ENGINEERING" in manifest["scope"]["domains"]
    assert manifest["registry_bridge"] is False
    assert "DESIGN_DIRECTOR" in manifest["composition"]["conflicts"]
    assert "VERIFIER" in manifest["composition"]["conflicts"]
    assert manifest["execution_policy"]["network"] == "deny"
    assert manifest["execution_policy"]["workspace_write"] == "host_bounded"


def test_frontend_package_references_and_contract_files_exist() -> None:
    package = _read_json("package-metadata.json")
    paths = [
        "SKILL.md",
        "manifest.json",
        "package-metadata.json",
        "profiles.json",
        "composition-contract.json",
        "scripts/deterministic-procedures.json",
        "evals/scenarios.json",
        "benchmarks/benchmark-fixtures.json",
        *package["files"]["references"],
    ]

    assert all((PACKAGE_ROOT / path).is_file() for path in paths)
    assert 8_000 <= (PACKAGE_ROOT / "SKILL.md").stat().st_size <= 20_000


def test_frontend_eval_set_is_meaningful_and_bounded() -> None:
    payload = _read_json("evals/scenarios.json")
    scenarios = payload["scenarios"]
    ids = [scenario["id"] for scenario in scenarios]
    categories = {scenario["category"] for scenario in scenarios}
    outcomes = {scenario["expected_route"] for scenario in scenarios}

    assert 50 <= len(scenarios) <= 75
    assert len(ids) == len(set(ids))
    assert {
        "routing",
        "state",
        "responsive",
        "accessibility",
        "performance",
        "security",
    } <= categories
    assert {"SELECTED", "OMITTED", "BLOCKED", "FALLBACK"} <= outcomes
    assert sum(scenario["false_pass_guard"] for scenario in scenarios) >= 8
    assert sum(scenario["negative"] for scenario in scenarios) >= 12
    assert all(scenario["acceptance"] for scenario in scenarios)


def test_frontend_procedures_are_declarative_and_fail_closed() -> None:
    payload = _read_json("scripts/deterministic-procedures.json")

    assert payload["metadata_only"] is True
    assert payload["read_only"] is True
    assert payload["network"] == "deny"
    assert payload["shell"] == "deny"
    assert payload["workspace_write"] == "host_bounded"
    assert 6 <= len(payload["procedures"]) <= 16
    assert all(item["max_attempts"] == 1 for item in payload["procedures"])


def test_frontend_skill_declares_handoff_without_unsupported_claims() -> None:
    skill = (PACKAGE_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "frontend-engineering-vnext" in skill
    assert "design-director" in skill
    assert "verification-loop-vnext" in skill
    assert "security-review" in skill
    assert "loading" in skill and "empty" in skill and "error" in skill and "retry" in skill
    assert "PRODUCTION_READY" not in skill
    assert "AAA_VERIFIED" not in skill
    assert "STABLE" not in skill


def test_pilot_contract_is_present_and_uses_existing_web_stack() -> None:
    pilot = PROJECT_ROOT / "evidence" / "phase-8" / "pilots" / "frontend-engineering" / "app"

    assert (pilot / "index.html").is_file()
    assert (pilot / "styles.css").is_file()
    assert (pilot / "app.js").is_file()
    assert (pilot / "fixture_server.py").is_file()
    source = "\n".join(
        (pilot / name).read_text(encoding="utf-8")
        for name in ("index.html", "styles.css", "app.js")
    )
    assert "Veterinary Emergency Intake" in source
    assert "/api/queue" in source
    assert "aria-live" in source
    assert "prefers-reduced-motion" in source


def test_pilot_visual_repair_contract_preserves_actions_and_error_recovery() -> None:
    pilot = PROJECT_ROOT / "evidence" / "phase-8" / "pilots" / "frontend-engineering" / "app"
    html = (pilot / "index.html").read_text(encoding="utf-8")
    css = (pilot / "styles.css").read_text(encoding="utf-8")
    javascript = (pilot / "app.js").read_text(encoding="utf-8")

    assert 'id="summary-retry"' in html
    assert "white-space: nowrap" in css
    assert ".queue-table th:nth-child(5)" in css and "width: 72px" in css
    assert ".state-card--error" in css
    assert ".summary-retry" in css
    assert ".form-field input:focus" in css
    assert "state-card--error" in javascript
    assert "summaryRetry" in javascript
