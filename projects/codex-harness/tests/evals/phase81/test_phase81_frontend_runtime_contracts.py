"""RED-first contracts for the Phase 8.1 finding-driven runtime fixture."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).parents[3]
RUNTIME_ROOT = PROJECT_ROOT / "evidence" / "phase-8.1" / "fixture" / "frontend" / "app"


def _server_module() -> ModuleType:
    path = RUNTIME_ROOT / "fixture_server.py"
    spec = importlib.util.spec_from_file_location("phase81_fixture_server", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase81_fixture_is_a_frozen_copy_with_deterministic_stale_responses() -> None:
    server = _server_module()

    server.reset_stale_fixture()
    first = server.stale_queue_payload()
    second = server.stale_queue_payload()

    assert first["request_label"] == "A"
    assert first["delay_ms"] > second["delay_ms"]
    assert second["request_label"] == "B"
    assert first["items"][0]["patient"] != second["items"][0]["patient"]


def test_phase81_fixture_preserves_validation_and_idempotency_contracts() -> None:
    server = _server_module()
    server.SUBMISSIONS.clear()
    payload = {"patient": "Nori", "species": "cat", "urgency": "urgent", "notes": ""}

    assert server.validate_intake(payload) == {"ok": True, "errors": {}}
    first, first_created = server.reserve_submission(payload, "phase81-retry-key")
    second, second_created = server.reserve_submission(payload, "phase81-retry-key")

    assert first_created is True
    assert second_created is False
    assert first == second


def test_phase81_frontend_binds_filter_to_url_history_and_stale_guard() -> None:
    javascript = (RUNTIME_ROOT / "app.js").read_text(encoding="utf-8")

    assert "readUrgencyFromLocation" in javascript
    assert "history.pushState" in javascript
    assert 'addEventListener("popstate"' in javascript
    assert "requestId !== queueRequest" in javascript
    assert "queueEndpoint(recover, requestId)" in javascript
    assert 'params.set("request", String(requestId))' in javascript
    assert 'if (currentScenario() !== "stale-response") loadQueue();' in javascript
    assert "window.__phase81" in javascript


def test_phase81_frontend_allows_200_percent_reflow_without_body_min_width() -> None:
    stylesheet = (RUNTIME_ROOT / "styles.css").read_text(encoding="utf-8")

    assert "body { margin: 0; min-width: 0;" in stylesheet


def test_phase81_frontend_uses_singular_case_label_for_one_filtered_item() -> None:
    javascript = (RUNTIME_ROOT / "app.js").read_text(encoding="utf-8")

    assert 'count === 1 ? "case" : "cases"' in javascript


def test_phase81_frontend_gives_row_actions_context_and_touch_size() -> None:
    javascript = (RUNTIME_ROOT / "app.js").read_text(encoding="utf-8")
    stylesheet = (RUNTIME_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'action.setAttribute("aria-label", `Review ${item.patient}`)' in javascript
    assert ".row-action { min-width: 44px; min-height: 44px;" in stylesheet
    assert ".icon-button { display: grid; width: 44px; height: 44px;" in stylesheet


def test_phase81_frontend_preserves_recovery_focus_and_visual_contrast_tokens() -> None:
    javascript = (RUNTIME_ROOT / "app.js").read_text(encoding="utf-8")
    stylesheet = (RUNTIME_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'action.dataset.recoveryAction = "true"' in javascript
    assert "elements.refreshQueue.focus()" in javascript
    assert "--border: #8a968f" in stylesheet
    assert "--border-strong: #6f7c75" in stylesheet
    assert "color: #586760" in stylesheet
    assert "@media (max-width: 420px)" in stylesheet
    assert ".rail-nav { grid-template-columns: 1fr; }" in stylesheet


def test_phase81_fixture_server_emits_current_artifact_binding_header() -> None:
    server = (RUNTIME_ROOT / "fixture_server.py").read_text(encoding="utf-8")

    assert "X-Phase81-Artifact-Digest" in server
    assert "artifact_tree_digest" in server


def test_phase81_frontend_fixture_contract_declares_runtime_metadata() -> None:
    metadata = json.loads(
        (PROJECT_ROOT / "evidence" / "phase-8.1" / "runtime-fixture.json").read_text(
            encoding="utf-8"
        )
    )

    assert metadata["schema_version"] == "P8.1-RUNTIME-FIXTURE-1"
    assert metadata["source_kind"] == "PHASE8_PILOT_COPY_WITH_FINDING_REPAIRS"
    assert metadata["scenario"] == "stale-response"
    assert metadata["network"] == "LOOPBACK_ONLY"
    assert metadata["external_producer"] is False
