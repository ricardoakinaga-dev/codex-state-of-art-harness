"""RED-first behavior contracts for the isolated frontend pilot."""

from __future__ import annotations

import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).parents[3]
PILOT_ROOT = PROJECT_ROOT / "evidence" / "phase-8" / "pilots" / "frontend-engineering" / "app"


def _server_module() -> ModuleType:
    path = PILOT_ROOT / "fixture_server.py"
    spec = importlib.util.spec_from_file_location("phase8_fixture_server", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixture_data_is_synthetic_and_stable() -> None:
    server = _server_module()

    queue = server.queue_payload("default")

    assert queue["status"] == "success"
    assert len(queue["items"]) == 4
    assert all(item["patient"] for item in queue["items"])
    assert all("owner" not in item and "phone" not in item for item in queue["items"])


def test_fixture_covers_empty_error_and_retry_recovery() -> None:
    server = _server_module()

    assert server.queue_payload("empty")["items"] == []
    assert server.queue_payload("error")["status"] == "error"
    assert server.queue_payload("recovered")["status"] == "success"


def test_fixture_rejects_invalid_intake_and_accepts_valid_intake() -> None:
    server = _server_module()

    invalid = server.validate_intake({"patient": "", "species": "cat", "urgency": "urgent"})
    valid = server.validate_intake({"patient": "Miso", "species": "cat", "urgency": "urgent"})

    assert invalid["ok"] is False
    assert "patient" in invalid["errors"]
    assert valid == {"ok": True, "errors": {}}


def test_fixture_idempotency_reservation_is_atomic() -> None:
    server = _server_module()
    server.SUBMISSIONS.clear()
    payload = {"patient": "Nori", "species": "cat", "urgency": "urgent", "notes": ""}

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(lambda _: server.reserve_submission(payload, "stable-retry-key"), range(8))
        )

    assert sum(created for _, created in results) == 1
    assert {item["intake_id"] for item, _ in results} == {results[0][0]["intake_id"]}


def test_static_source_has_no_external_network_or_unsafe_inline_handlers() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in PILOT_ROOT.glob("*.js"))

    assert "http://" not in source and "https://" not in source
    assert "onclick=" not in (PILOT_ROOT / "index.html").read_text(encoding="utf-8")
    assert "eval(" not in source


def test_pilot_binds_retry_idempotency_and_server_errors_to_controls() -> None:
    html = (PILOT_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (PILOT_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (PILOT_ROOT / "styles.css").read_text(encoding="utf-8")

    assert 'id="patient"' in html and 'id="patient" name="patient" type="text"' in html
    assert (
        'id="patient" name="patient" type="text" autocomplete="off" maxlength="60" '
        'placeholder="e.g. Miso" aria-describedby="patient-hint patient-error" '
        'required aria-required="true"'
    ) in html
    assert (
        'id="species" name="species" aria-describedby="species-error" required aria-required="true"'
    ) in html
    assert (
        'id="urgency" name="urgency" aria-describedby="urgency-error" required aria-required="true"'
    ) in html
    assert 'id="notes-error" role="alert"' in html
    assert 'aria-describedby="notes-hint notes-error"' in html
    assert "let intakeIdempotencyKey" in javascript
    assert '"Idempotency-Key": intakeIdempotencyKey' in javascript
    assert "intakeIdempotencyKey = null" in javascript
    assert "showFormErrors(payload.errors)" in javascript
    assert "elements.notes" in javascript.split("function bind", 1)[1]
    assert "Lock" in (PILOT_ROOT / "fixture_server.py").read_text(encoding="utf-8")
    assert "--muted: #5d6965" in styles
    assert "--amber: #865b16" in styles
    assert "background: var(--accent-deep)" in styles


def test_benchmark_declares_required_viewports_and_states() -> None:
    benchmark = json.loads(
        (
            PROJECT_ROOT
            / ".harness/capabilities/frontend-engineering-vnext/benchmarks/benchmark-fixtures.json"
        ).read_text(encoding="utf-8")
    )
    viewports = {(item["width"], item["height"]) for item in benchmark["viewports"]}
    states = set(benchmark["states"])

    assert viewports == {(1440, 900), (1024, 768), (768, 1024), (390, 844)}
    assert {
        "default",
        "loading",
        "success",
        "empty",
        "error",
        "retry",
        "validation",
        "double_submit",
    } <= states
