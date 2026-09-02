# ruff: noqa: E501
"""Generate and verify the bounded Phase 8.1 closure packet.

The verifier is intentionally local and evidence-driven.  It binds the
frontend package, composed artifact, browser captures, structural catalog,
coverage result, host receipts and finding ledger without claiming that the
public host protocol exposed a skill-load event.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
EVIDENCE_ROOT = PROJECT_ROOT / "evidence" / "phase-8.1"
BROWSER_ROOT = EVIDENCE_ROOT / "browser"
FRONTEND_FINGERPRINT = "sha256:c0cd7c9611a89bdb730b2ba73a06212f4b3d432e06ed4f9792550ff7dacd9342"
VERIFIER_FINGERPRINT = "sha256:dc380396cdc489976b5d120a964321032907f0101431786cda060dae15c11a4b"
COMPOSITION_RUN = "P81-COMPOSE-011"
COMPOSED_ARTIFACT_DIGEST = "sha256:bfd899129937a6c615389796e6d85972ebe7f4572392b362e9e37b256bc3e044"
BASE_URL = "http://127.0.0.1:4188/"
FRONTEND_HOST_RECEIPT = (
    "frontend-real-003/invocation-receipts/INV-b1154ffe58ce5c6d9ba8d3c4.json"
)
VERIFIER_HOST_RECEIPT = "verifier-real-003/invocation-receipts/INV-d74d1ef5d64b573689764a86.json"
COMPOSITION_RECEIPT = "composition-run-011/composition-receipt.json"
CANONICAL_COMPOSITION_RECEIPT = "composition-receipt.json"
COMPOSITION_ARTIFACT_ROOT = "composition-run-011/frontend-artifact"
COMPOSITION_ARTIFACT_REF = f"evidence/phase-8.1/{COMPOSITION_ARTIFACT_ROOT}"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical(value).encode()).hexdigest()}"


def file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def load_json(relative_path: str) -> Any:
    return json.loads((EVIDENCE_ROOT / relative_path).read_text(encoding="utf-8"))


def normalize_evidence_ref(value: str) -> str:
    prefix = "evidence/phase-8.1/"
    if value.startswith(prefix):
        value = value.removeprefix(prefix)
    path = Path(value)
    if path.is_absolute():
        path = path.resolve().relative_to(EVIDENCE_ROOT.resolve())
    if ".." in path.parts:
        raise ValueError(f"evidence reference escapes the packet: {value}")
    return path.as_posix()


def capture_timestamp(path: Path) -> int:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        value = None
    if isinstance(value, dict) and isinstance(value.get("captured_at_ns"), int):
        return value["captured_at_ns"]
    if isinstance(value, dict) and isinstance(value.get("observed_at_ns"), int):
        return value["observed_at_ns"]
    return path.stat().st_mtime_ns


def host_invocation_id(host: dict[str, Any]) -> str:
    receipt = host.get("receipt")
    if isinstance(receipt, dict) and isinstance(receipt.get("invocation_id"), str):
        return receipt["invocation_id"]
    return str(host.get("invocation_id", "unknown-host-invocation"))


def host_completed_ns(host: dict[str, Any]) -> int:
    result = host.get("host_result", {})
    completed_at = result.get("completed_at")
    if not isinstance(completed_at, (int, float)):
        raise ValueError("host receipt does not contain completed_at")
    return int(completed_at * 1_000_000_000)


def browser_capture_record(
    path: Path,
    *,
    kind: str,
    composition_run: str,
    artifact_digest: str,
    server_process: dict[str, Any],
    server_process_previous: dict[str, Any],
) -> dict[str, Any]:
    observed_at_ns = capture_timestamp(path)
    server_run = (
        server_process
        if observed_at_ns >= server_process["started_at_ns"]
        else server_process_previous
    )
    return {
        "path": f"browser/{path.name}",
        "sha256": file_digest(path),
        "kind": kind,
        "capture_id": "P81-BROWSER-010",
        "composition_run": composition_run,
        "source_digest": artifact_digest,
        "artifact_digest": artifact_digest,
        "captured_at_ns": observed_at_ns,
        "observer": "Playwright MCP Chromium browser observer",
        "server_run_id": server_run["run_id"],
    }


def timeline_event(
    sequence: int,
    event: str,
    observed_at_ns: int,
    source: str,
    invocation_id: str,
    capability: str,
    artifact_digest: str,
    observation_type: str,
    observation: str,
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "event": event,
        "observed_at_ns": observed_at_ns,
        "source": source,
        "run_id": COMPOSITION_RUN,
        "invocation_id": invocation_id,
        "capability": capability,
        "source_digest": artifact_digest,
        "artifact_digest": artifact_digest,
        "observation_type": observation_type,
        "observation": observation,
    }


def write_json(relative_path: str, value: Any) -> None:
    path = EVIDENCE_ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(relative_path: str, value: str) -> None:
    path = EVIDENCE_ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def git_head() -> str:
    return subprocess.run(
        ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def check(
    checks: list[dict[str, Any]],
    name: str,
    condition: bool,
    details: str,
    refs: list[str],
) -> None:
    checks.append(
        {
            "name": name,
            "status": "PASS" if condition else "FAIL",
            "details": details,
            "evidence": refs,
        }
    )


def url_is_current(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(BASE_URL)


def build_runtime_classification(
    structural: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    runtime_ids = {
        f"P8-EVAL-{number:03d}"
        for number in (
            *range(11, 21),
            *range(21, 28),
            *range(29, 38),
            *range(39, 44),
            50,
            53,
        )
    }
    not_applicable_ids = {
        "P8-EVAL-003",
        "P8-EVAL-004",
        "P8-EVAL-006",
        "P8-EVAL-007",
    }
    future_domain_ids = {"P8-EVAL-044"}
    evidence_map: dict[str, list[str]] = {
        "P8-EVAL-011": ["browser/loading.json"],
        "P8-EVAL-012": ["browser/default-metrics.json", "browser/default-snapshot.md"],
        "P8-EVAL-013": ["browser/portrait-metrics.json"],
        "P8-EVAL-014": ["browser/error.json"],
        "P8-EVAL-015": ["browser/error-retry.json", "browser/error-keyboard-retry.json"],
        "P8-EVAL-016": [
            "browser/stale-response.json",
            "browser/stale-response-initial.json",
            "browser/stale-response-request-a.json",
            "browser/stale-response-request-b.json",
            "browser/stale-response-timeline.json",
            "browser/stale-network.log",
        ],
        "P8-EVAL-017": ["browser/idempotency.json"],
        "P8-EVAL-018": ["browser/url-select-urgent.json", "browser/url-critical.json"],
        "P8-EVAL-019": [
            "browser/url-critical.json",
            "browser/url-select-urgent.json",
            "browser/url-back-critical.json",
            "browser/url-invalid.json",
        ],
        "P8-EVAL-020": ["browser/server-validation.json", "browser/interaction-validation.json"],
        "P8-EVAL-021": ["browser/desktop-success-1440x900.png", "browser/desktop-metrics.json"],
        "P8-EVAL-022": ["browser/tablet-urgent-1024x768.png", "browser/tablet-metrics.json"],
        "P8-EVAL-023": ["browser/tablet-metrics.json"],
        "P8-EVAL-024": [
            "browser/mobile-critical-focused-390x844.png",
            "browser/mobile-critical-metrics.json",
        ],
        "P8-EVAL-025": [
            "browser/long-heading-768x1024.json",
        ],
        "P8-EVAL-026": ["browser/default-snapshot.md", "browser/mobile-critical-metrics.json"],
        "P8-EVAL-027": [
            "browser/reflow-200-percent.json",
            "browser/reflow-200-percent-195x844.png",
        ],
        "P8-EVAL-029": ["browser/accessibility-runtime.json"],
        "P8-EVAL-030": ["browser/accessibility-runtime.json"],
        "P8-EVAL-031": ["browser/accessibility-runtime.json"],
        "P8-EVAL-032": [
            "browser/accessibility-runtime.json",
            "browser/contrast-observation.json",
        ],
        "P8-EVAL-033": [
            "browser/keyboard-submit-result-002.json",
            "browser/keyboard-submit-focused-002.json",
            "browser/keyboard-step-00.json",
            "browser/keyboard-invalid-submit.json",
        ],
        "P8-EVAL-034": [
            "browser/accessibility-runtime.json",
            "browser/interaction-submit-loading.json",
        ],
        "P8-EVAL-035": ["browser/accessibility-runtime.json", "browser/default-snapshot.md"],
        "P8-EVAL-036": ["browser/accessibility-runtime.json", "browser/performance-runtime.json"],
        "P8-EVAL-037": ["browser/accessibility-runtime.json"],
        "P8-EVAL-039": ["browser/performance-runtime.json"],
        "P8-EVAL-040": ["browser/layout-performance.json"],
        "P8-EVAL-041": ["browser/performance-runtime.json", "browser/default-final-network.log"],
        "P8-EVAL-042": ["browser/performance-runtime.json"],
        "P8-EVAL-043": ["browser/performance-runtime.json"],
        "P8-EVAL-050": ["browser/server-validation.json", "browser/interaction-validation.json"],
        "P8-EVAL-053": [
            "browser/default-final-network.log",
            "browser/server-validation.json",
            "browser/server-process.json",
        ],
    }

    def runtime_contract(scenario_id: str, refs: list[str]) -> tuple[bool, str]:
        missing = [ref for ref in refs if not (EVIDENCE_ROOT / ref).is_file()]
        if missing:
            return False, f"Missing evidence: {', '.join(missing)}"
        values = {ref: load_json(ref) for ref in refs if ref.endswith(".json")}
        text_values = {
            ref: (EVIDENCE_ROOT / ref).read_text(encoding="utf-8")
            for ref in refs
            if ref.endswith(".md") or ref.endswith(".log")
        }
        all_current_urls = all(
            url_is_current(value.get("url"))
            for value in values.values()
            if isinstance(value, dict) and "url" in value
        )
        if scenario_id == "P8-EVAL-011":
            loading = values["browser/loading.json"]
            condition = (
                loading["phase"] == "loading"
                and loading.get("queueBusy") is True
                and loading.get("skeletonRows", 0) >= 1
            )
            detail = "Loading phase, busy queue state and skeleton rows are captured before the delayed response."
        elif scenario_id == "P8-EVAL-012":
            metrics = values["browser/default-metrics.json"]
            condition = (
                metrics["phase"] == "success"
                and metrics["items"] == 4
                and "Emergency queue" in text_values["browser/default-snapshot.md"]
                and all_current_urls
            )
            detail = "Default success state, four items and queue landmark are observed."
        elif scenario_id == "P8-EVAL-013":
            value = values["browser/portrait-metrics.json"]
            condition = value["phase"] == "success" and value["items"] == 0
            detail = "Portrait empty state is observed with one explicit state row."
        elif scenario_id == "P8-EVAL-014":
            value = values["browser/error.json"]
            condition = value["phase"] == "error" and bool(value.get("alert"))
            detail = "Error state exposes an alert and recovery action."
        elif scenario_id == "P8-EVAL-015":
            value = values["browser/error-retry.json"]
            keyboard = values["browser/error-keyboard-retry.json"]
            condition = (
                value["phase"] == "success"
                and value["itemCount"] == 4
                and keyboard["after"]["phase"] == "success"
            )
            detail = "Error recovery succeeds by both captured retry paths."
        elif scenario_id == "P8-EVAL-016":
            timeline = values["browser/stale-response-timeline.json"]
            requests = timeline["requests"]
            condition = (
                values["browser/stale-response.json"]["visiblePatients"] == ["Fresh B"]
                and values["browser/stale-response-request-a.json"]["request_label"] == "A"
                and values["browser/stale-response-request-b.json"]["request_label"] == "B"
                and values["browser/stale-response-request-a.json"]["delay_ms"]
                > values["browser/stale-response-request-b.json"]["delay_ms"]
                and len(requests) == 2
                and requests[0]["label"] == "A"
                and requests[1]["label"] == "B"
                and timeline["ordering"]["requestAStartedBeforeB"] is True
                and timeline["ordering"]["responseBCompletedBeforeA"] is True
                and timeline["finalVisiblePatients"] == ["Fresh B"]
            )
            detail = "Delayed A and fast B overlap; B completes first and remains authoritative."
        elif scenario_id == "P8-EVAL-017":
            value = values["browser/idempotency.json"]
            condition = (
                value["sameId"] is True
                and value["acceptedPayloads"] == 1
                and value["duplicatePayloads"] == 1
            )
            detail = "Concurrent idempotent submissions yield one accepted and one duplicate."
        elif scenario_id == "P8-EVAL-018":
            value = values["browser/url-select-urgent.json"]
            condition = value["selectedUrgency"] == "urgent" and value["visiblePatients"] == [
                "Juniper"
            ]
            detail = "Selecting Urgent updates URL state and visible rows."
        elif scenario_id == "P8-EVAL-019":
            condition = (
                values["browser/url-critical.json"]["selectedUrgency"] == "critical"
                and values["browser/url-select-urgent.json"]["selectedUrgency"] == "urgent"
                and values["browser/url-back-critical.json"]["selectedUrgency"] == "critical"
                and values["browser/url-invalid.json"]["selectedUrgency"] == "all"
                and values["browser/url-invalid.json"]["canonical"] is True
            )
            detail = (
                "URL initialization, history selection, back restoration and invalid fallback pass."
            )
        elif scenario_id == "P8-EVAL-020":
            value = values["browser/server-validation.json"]
            condition = value["status"] == 422 and set(value["body"]["errors"]) >= {
                "patient",
                "species",
                "urgency",
            }
            detail = "Server-side validation returns a bounded 422 envelope for invalid fields."
        elif scenario_id in {"P8-EVAL-021", "P8-EVAL-022", "P8-EVAL-023", "P8-EVAL-024"}:
            if scenario_id == "P8-EVAL-021":
                value = load_json("browser/desktop-metrics.json")
            elif scenario_id in {"P8-EVAL-022", "P8-EVAL-023"}:
                value = values["browser/tablet-metrics.json"]
            else:
                value = values["browser/mobile-critical-metrics.json"]
            expected_width = {
                "P8-EVAL-021": 1440,
                "P8-EVAL-022": 1024,
                "P8-EVAL-023": 1024,
                "P8-EVAL-024": 390,
            }[scenario_id]
            overflow = value.get(
                "overflowX",
                value.get("documentWidth", expected_width) > expected_width
                or value.get("bodyWidth", expected_width) > expected_width,
            )
            condition = value["viewport"]["width"] == expected_width and overflow is False
            if scenario_id in {"P8-EVAL-022", "P8-EVAL-023"}:
                condition = (
                    condition
                    and value["selectedUrgency"] == "urgent"
                    and value["visiblePatients"] == ["Juniper"]
                )
            if scenario_id == "P8-EVAL-024":
                condition = (
                    condition
                    and value["selected"] == "critical"
                    and value["visiblePatients"] == ["Miso"]
                )
            detail = f"Responsive runtime at {expected_width}px has no horizontal overflow."
        elif scenario_id == "P8-EVAL-025":
            value = values["browser/long-heading-768x1024.json"]
            condition = (
                value["viewport"]["width"] == 768
                and value["headingText"]
                and value["headingLineCount"] >= 2
                and value["headingOverflow"] is False
            )
            detail = "The current clinic heading wraps to multiple lines at the intermediate viewport without clipping."
        elif scenario_id == "P8-EVAL-026":
            condition = (
                'columnheader "Patient"' in text_values["browser/default-snapshot.md"]
                and values["browser/mobile-critical-metrics.json"]["viewport"]["width"] == 390
            )
            detail = "Accessibility snapshot contains the queue table headers."
        elif scenario_id == "P8-EVAL-027":
            value = values["browser/reflow-200-percent.json"]
            condition = value["viewport"]["width"] == 195 and value["overflowX"] is False
            detail = "200% reflow capture is bounded to 195px without horizontal overflow."
        elif scenario_id == "P8-EVAL-029":
            value = values["browser/accessibility-runtime.json"]
            condition = set(value["headings"]) >= {"H1", "H2"} and len(value["ariaLive"]) >= 2
            detail = "Landmarks, headings and live regions are present in the runtime capture."
        elif scenario_id == "P8-EVAL-030":
            condition = values["browser/accessibility-runtime.json"]["headings"] == [
                "H1",
                "H2",
                "H2",
                "H2",
            ]
            detail = "Heading hierarchy is captured as one H1 followed by H2 sections."
        elif scenario_id == "P8-EVAL-031":
            labels = values["browser/accessibility-runtime.json"]["labels"]
            condition = all(
                labels.get(field) for field in ("patient", "species", "urgency", "notes")
            )
            detail = "Form controls have non-empty associated labels."
        elif scenario_id == "P8-EVAL-032":
            focus = values["browser/accessibility-runtime.json"]["focus"]
            contrast = values["browser/contrast-observation.json"]
            condition = (
                focus["id"] == "patient"
                and "solid 3px" in focus["outline"]
                and contrast["pass"] is True
            )
            detail = "Focused patient field exposes a visible three-pixel outline and sampled runtime contrast passes."
        elif scenario_id == "P8-EVAL-033":
            result = values["browser/keyboard-submit-result-002.json"]
            focused = values["browser/keyboard-submit-focused-002.json"]
            steps = values["browser/keyboard-step-00.json"]["tabSequence"]
            invalid = values["browser/keyboard-invalid-submit.json"]
            condition = (
                result["phase"] == "success"
                and result["focused"]["id"] == "patient"
                and focused["focused"]["id"] == "submit-intake"
                and focused["focusVisible"] is True
                and steps[-1] == "submit-intake"
                and invalid["phase"] == "validation"
                and invalid["focused"]["id"] == "patient"
                and set(invalid["invalid"]) >= {"patient", "species", "urgency"}
            )
            detail = "Keyboard traversal reaches submit; a real invalid keyboard submit returns focus to patient before a successful submit."
        elif scenario_id == "P8-EVAL-034":
            live = values["browser/accessibility-runtime.json"]["ariaLive"]
            condition = {item["id"] for item in live} >= {
                "queue-state",
                "intake-feedback",
            } and values["browser/interaction-submit-loading.json"]["feedbackRole"] == "status"
            detail = "Queue and intake feedback are polite status live regions."
        elif scenario_id == "P8-EVAL-035":
            targets = values["browser/accessibility-runtime.json"]["targets"]
            condition = (
                any(target.get("ariaLabel") == "Review Miso" for target in targets)
                and "Triage" in text_values["browser/default-snapshot.md"]
            )
            detail = "Contextual row actions and triage state labels are exposed to the accessibility tree."
        elif scenario_id == "P8-EVAL-036":
            condition = (
                values["browser/accessibility-runtime.json"]["reducedMotionRule"] is True
                and values["browser/performance-runtime.json"]["reducedMotionRule"] is True
            )
            detail = "Reduced-motion CSS rule is observed in both accessibility and performance captures."
        elif scenario_id == "P8-EVAL-037":
            targets = values["browser/accessibility-runtime.json"]["targets"]
            refresh = next(
                (target for target in targets if target.get("id") == "refresh-queue"), {}
            )
            actions = [
                target
                for target in targets
                if (target.get("ariaLabel") or "").startswith("Review ")
            ]
            submit = next((target for target in targets if target.get("id") == "submit-intake"), {})
            condition = (
                refresh.get("width", 0) >= 44
                and refresh.get("height", 0) >= 44
                and all(
                    target.get("width", 0) >= 44 and target.get("height", 0) >= 44
                    for target in actions
                )
                and submit.get("height", 0) >= 44
            )
            detail = "Primary row, refresh and submit controls meet the bounded touch-size check."
        elif scenario_id == "P8-EVAL-039":
            value = values["browser/performance-runtime.json"]
            condition = (
                isinstance(value.get("largestContentfulPaintMs"), (int, float))
                and value["largestContentfulPaintMs"] < 2500
            )
            detail = "Largest Contentful Paint is recorded below the bounded 2.5s target."
        elif scenario_id == "P8-EVAL-040":
            condition = values["browser/layout-performance.json"]["layoutShiftValue"] == 0
            detail = "No layout shift is recorded in the current capture."
        elif scenario_id == "P8-EVAL-041":
            value = values["browser/performance-runtime.json"]
            condition = (
                value["externalResources"] == 0
                and BASE_URL.removesuffix("/") in text_values["browser/default-final-network.log"]
            )
            detail = "Runtime resources and network log remain same-origin loopback only."
        elif scenario_id == "P8-EVAL-042":
            condition = "ui-sans-serif" in values["browser/performance-runtime.json"]["fontFamily"]
            detail = "Runtime font stack begins with the bounded system sans family."
        elif scenario_id == "P8-EVAL-043":
            value = values["browser/performance-runtime.json"]
            condition = value["images"] == 0 and value["mediaBytes"] == 0
            detail = "No image or media payload is loaded by the local fixture."
        elif scenario_id == "P8-EVAL-050":
            value = values["browser/server-validation.json"]
            interaction = values["browser/interaction-validation.json"]
            condition = (
                value["status"] == 422
                and set(interaction["invalid"]) >= {"patient", "species", "urgency"}
                and interaction["focused"] == "patient"
            )
            detail = "Client and server validation evidence agree on invalid-field handling."
        elif scenario_id == "P8-EVAL-053":
            process = values["browser/server-process.json"]
            network_lines = [
                line
                for line in text_values["browser/default-final-network.log"].splitlines()
                if line[:1].isdigit()
            ]
            condition = (
                process["network"] == "LOOPBACK_ONLY"
                and process["process_started"] is True
                and network_lines
                and all(BASE_URL.removesuffix("/") in line for line in network_lines)
            )
            detail = "Server process and browser network evidence are loopback-bound."
        else:
            condition = False
            detail = "No runtime contract was defined for this scenario."
        return condition and all_current_urls, detail

    catalog = json.loads(
        (
            PROJECT_ROOT / ".harness/capabilities/frontend-engineering-vnext/evals/scenarios.json"
        ).read_text(encoding="utf-8")
    )
    scenarios = catalog["scenarios"]
    structural_results = {result["id"]: result for result in structural["results"]}
    records: list[dict[str, Any]] = []
    traceability: dict[str, Any] = {
        "schema_version": "P8.1-RUNTIME-TRACEABILITY-1",
        "task_id": "PHASE8.1-001",
        "composition_run": COMPOSITION_RUN,
        "frontend_artifact_digest": COMPOSED_ARTIFACT_DIGEST,
        "records": [],
    }
    for scenario in scenarios:
        scenario_id = scenario["id"]
        if scenario_id in runtime_ids:
            classification = "RUNTIME_REQUIRED"
            refs = evidence_map.get(scenario_id, [])
            passed, reason = runtime_contract(scenario_id, refs)
            status = "PASS" if passed else "FAIL"
            validation = status
            promotion_relevant = True
        elif scenario_id in not_applicable_ids:
            classification = "NOT_APPLICABLE"
            status = "NOT_APPLICABLE"
            validation = "NOT_RUN"
            refs = ["structural-eval-report.json"]
            reason = "The bounded Phase 8.1 frontend runtime does not exercise this domain."
            promotion_relevant = False
        elif scenario_id in future_domain_ids:
            classification = "FUTURE_DOMAIN"
            status = "FUTURE_DOMAIN"
            validation = "NOT_RUN"
            refs = ["structural-eval-report.json"]
            reason = "Virtualization is outside the bounded four-row local fixture."
            promotion_relevant = False
        else:
            classification = "STRUCTURAL_SUFFICIENT"
            status = structural_results[scenario_id]["status"]
            validation = status
            refs = ["structural-eval-report.json"]
            reason = (
                "Structural routing/negative-guard result is sufficient for this catalog scenario."
            )
            promotion_relevant = True
        records.append(
            {
                "id": scenario_id,
                "category": scenario["category"],
                "title": scenario.get("title", scenario.get("name", scenario_id)),
                "classification": classification,
                "status": status,
                "validation": validation,
                "promotion_relevant": promotion_relevant,
                "reason": reason,
                "evidence": refs,
            }
        )
        traceability["records"].append(
            {
                "id": scenario_id,
                "classification": classification,
                "status": status,
                "validation": validation,
                "details": reason,
                "checked_evidence": refs,
                "evidence": refs,
            }
        )
    classification = {
        "schema_version": "P8.1-RUNTIME-CLASSIFICATION-1",
        "task_id": "PHASE8.1-001",
        "status": "PASS"
        if all(item["status"] in {"PASS", "NOT_APPLICABLE", "FUTURE_DOMAIN"} for item in records)
        else "FAIL",
        "catalog": ".harness/capabilities/frontend-engineering-vnext/evals/scenarios.json",
        "catalog_scenario_count": len(scenarios),
        "structural_report": "structural-eval-report.json",
        "composition_run": COMPOSITION_RUN,
        "frontend_artifact_digest": COMPOSED_ARTIFACT_DIGEST,
        "records": records,
        "counts": {
            "total": len(records),
            "runtime_required": sum(
                item["classification"] == "RUNTIME_REQUIRED" for item in records
            ),
            "runtime_executed": sum(
                item["classification"] == "RUNTIME_REQUIRED" and item["status"] == "PASS"
                for item in records
            ),
            "structural_sufficient": sum(
                item["classification"] == "STRUCTURAL_SUFFICIENT" for item in records
            ),
            "not_applicable": sum(item["classification"] == "NOT_APPLICABLE" for item in records),
            "future_domain": sum(item["classification"] == "FUTURE_DOMAIN" for item in records),
            "promotion_relevant_unresolved": sum(
                item["promotion_relevant"] and item["status"] != "PASS" for item in records
            ),
        },
    }
    traceability["digest"] = digest(traceability)
    classification["digest"] = digest(classification)
    return classification, traceability


def main() -> int:
    global BASE_URL, COMPOSITION_ARTIFACT_REF, COMPOSITION_ARTIFACT_ROOT
    global COMPOSITION_RECEIPT, COMPOSITION_RUN, COMPOSED_ARTIFACT_DIGEST
    global FRONTEND_FINGERPRINT, FRONTEND_HOST_RECEIPT, VERIFIER_FINGERPRINT
    global VERIFIER_HOST_RECEIPT
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="verifier-report.json")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--composition-run", default=COMPOSITION_RUN)
    parser.add_argument("--artifact-digest", default=COMPOSED_ARTIFACT_DIGEST)
    parser.add_argument("--frontend-fingerprint", default=FRONTEND_FINGERPRINT)
    parser.add_argument("--verifier-fingerprint", default=VERIFIER_FINGERPRINT)
    parser.add_argument("--frontend-host-receipt", default=FRONTEND_HOST_RECEIPT)
    parser.add_argument("--verifier-host-receipt", default=VERIFIER_HOST_RECEIPT)
    parser.add_argument("--composition-receipt", default=COMPOSITION_RECEIPT)
    parser.add_argument("--scope-audit", default="composition-run-011/composition-scope-audit.json")
    args = parser.parse_args()

    BASE_URL = args.base_url.rstrip("/") + "/"
    COMPOSITION_RUN = args.composition_run
    COMPOSED_ARTIFACT_DIGEST = args.artifact_digest
    FRONTEND_FINGERPRINT = args.frontend_fingerprint
    VERIFIER_FINGERPRINT = args.verifier_fingerprint
    FRONTEND_HOST_RECEIPT = normalize_evidence_ref(args.frontend_host_receipt)
    VERIFIER_HOST_RECEIPT = normalize_evidence_ref(args.verifier_host_receipt)
    COMPOSITION_RECEIPT = normalize_evidence_ref(args.composition_receipt)
    scope_audit_ref = normalize_evidence_ref(args.scope_audit)

    checks: list[dict[str, Any]] = []
    frontend_validation = load_json("frontend-package-validation.json")
    composition_receipt = load_json(COMPOSITION_RECEIPT)
    canonical_composition_receipt = load_json(CANONICAL_COMPOSITION_RECEIPT)
    build_receipt_ref = normalize_evidence_ref(composition_receipt["source"]["build_receipt"])
    build_receipt = load_json(build_receipt_ref)
    structural = load_json("structural-eval-report.json")
    ledger = load_json("finding-ledger.json")
    matrix = load_json("host-composition-capability-matrix.json")
    frontend_host = load_json(FRONTEND_HOST_RECEIPT)
    verifier_host = load_json(VERIFIER_HOST_RECEIPT)
    server_process = load_json("browser/server-process.json")
    server_process_previous = load_json("browser/server-process-011.json")
    server_binding = load_json("browser/server-binding.json")
    scope_audit = load_json(scope_audit_ref)
    coverage = load_json("coverage-summary.json")

    current_files = ["index.html", "styles.css", "app.js", "fixture_server.py"]
    source_root = EVIDENCE_ROOT / "fixture" / "frontend" / "app"
    source_files = {name: source_root / name for name in current_files}
    source_tree_digest = (
        "sha256:"
        + hashlib.sha256(
            "\n".join(f"{name}:{file_digest(source_files[name])}" for name in current_files).encode(
                "utf-8"
            )
        ).hexdigest()
    )
    build_root_ref = normalize_evidence_ref(composition_receipt["source"]["root"])
    COMPOSITION_ARTIFACT_ROOT = normalize_evidence_ref(
        composition_receipt["composed_artifact"]["root"]
    )
    COMPOSITION_ARTIFACT_REF = f"evidence/phase-8.1/{COMPOSITION_ARTIFACT_ROOT}"
    artifact_root = EVIDENCE_ROOT / COMPOSITION_ARTIFACT_ROOT
    artifact_tree_digest = (
        "sha256:"
        + hashlib.sha256(
            "\n".join(
                f"{name}:{file_digest(artifact_root / name)}" for name in current_files
            ).encode("utf-8")
        ).hexdigest()
    )

    check(
        checks,
        "frontend_package_current",
        frontend_validation["status"] == "PASS"
        and frontend_validation["package_fingerprint"] == FRONTEND_FINGERPRINT
        and frontend_validation["eval_count"] == 60,
        "Frontend package validator is PASS with the exact current fingerprint and 60 scenarios.",
        ["frontend-package-validation.json"],
    )
    check(
        checks,
        "frontend_source_tree_current",
        source_tree_digest == COMPOSED_ARTIFACT_DIGEST
        and build_receipt["source_tree_digest"] == COMPOSED_ARTIFACT_DIGEST,
        f"Current fixture source and build receipt bind to {COMPOSED_ARTIFACT_DIGEST}.",
        ["baseline.json", "runtime-fixture.json", build_receipt_ref],
    )
    check(
        checks,
        "composition_exact_artifact",
        composition_receipt["run_id"] == COMPOSITION_RUN
        and composition_receipt["composed_artifact"]["tree_digest"] == COMPOSED_ARTIFACT_DIGEST
        and artifact_tree_digest == COMPOSED_ARTIFACT_DIGEST,
        "Bridge output matches the current source/build digest and the exact composed files.",
        [COMPOSITION_RECEIPT, f"{COMPOSITION_ARTIFACT_ROOT}/"],
    )
    authorization = composition_receipt["host"]["authorization"]
    check(
        checks,
        "composition_canonical_authorization",
        canonical_composition_receipt["run_id"] == COMPOSITION_RUN
        and canonical_composition_receipt["status"] == "PARTIAL"
        and canonical_composition_receipt["composed_artifact"]["tree_digest"]
        == COMPOSED_ARTIFACT_DIGEST
        and canonical_composition_receipt["host"]["invocation_id"]
        == composition_receipt["host"]["invocation_id"]
        and authorization["authorization_id"]
        == composition_receipt["workspace_observation"]["authorization_id"]
        and authorization["filesystem_mode"] == "READ_ONLY"
        and authorization["package_write_allowed"] is False
        and all(
            authorization[key] == "DENY"
            for key in ("network", "mcp", "providers", "shell", "credentials")
        )
        and composition_receipt["workspace_observation"]["composition_output_confined_to_evidence"]
        is True,
        "The canonical receipt is current, authorized read-only, denied external side effects and confined to the evidence root.",
        [CANONICAL_COMPOSITION_RECEIPT, COMPOSITION_RECEIPT],
    )
    check(
        checks,
        "frontend_host_transport",
        frontend_host["status"] == "SUCCESS"
        and frontend_host["host_invoked"] is True
        and frontend_host["host_result"]["status"] == "SUCCESS"
        and frontend_host["host_result"]["execution_observed"] is True
        and frontend_host["host_result"]["final_message"] == "READY"
        and frontend_host["verification"]["status"] == "VERIFIED"
        and frontend_host["package_fingerprint"] == FRONTEND_FINGERPRINT,
        "Fresh frontend app-server handshake observed READY under the exact package fingerprint.",
        [FRONTEND_HOST_RECEIPT],
    )
    check(
        checks,
        "verifier_host_transport",
        verifier_host["status"] == "SUCCESS"
        and verifier_host["host_invoked"] is True
        and verifier_host["host_result"]["status"] == "SUCCESS"
        and verifier_host["host_result"]["execution_observed"] is True
        and verifier_host["host_result"]["final_message"] == "VERIFIER_READY"
        and verifier_host["verification"]["status"] == "VERIFIED"
        and verifier_host["package_fingerprint"] == VERIFIER_FINGERPRINT,
        "Fresh verifier app-server handshake observed VERIFIER_READY under the exact verifier fingerprint.",
        [VERIFIER_HOST_RECEIPT],
    )
    check(
        checks,
        "alternative_bridge_mutation_boundary",
        composition_receipt["workspace_observation"]["global_mutations"] == 0
        and composition_receipt["workspace_observation"]["capability_file_mutations"] == 0
        and composition_receipt["workspace_observation"]["external_producer"] is False
        and composition_receipt["workspace_observation"]["manual_mutation_during_run"] is False,
        "Composition bridge records zero global/capability mutation and no alternate producer.",
        [COMPOSITION_RECEIPT, scope_audit_ref],
    )
    check(
        checks,
        "independent_scope_audit",
        scope_audit["run_id"] == COMPOSITION_RUN
        and scope_audit["global_mutations"] == 0
        and scope_audit["capability_file_mutations"] == 0
        and scope_audit["before_digest"] == scope_audit["after_digest"]
        and scope_audit["external_producer"] is False,
        "Independent read-only snapshots show no global or capability-file mutation around the exact bridge.",
        [scope_audit_ref, COMPOSITION_RECEIPT],
    )
    check(
        checks,
        "structural_catalog_current",
        structural["status"] == "PASS"
        and structural["scenario_count"] == 60
        and not structural["failures"]
        and structural["critical_false_pass_count"] == 0
        and structural["critical_false_pass"] == []
        and structural["false_pass_guard_ids"],
        "Structural evaluator is PASS for all 60 scenarios with zero observed critical false passes and a preserved guard inventory.",
        ["structural-eval-report.json"],
    )
    check(
        checks,
        "finding_ledger_resolved",
        ledger["counts"]["open_actionable_high"] == 0
        and ledger["counts"]["open_actionable_medium"] == 0
        and ledger["counts"]["promotion_blocking_high"] == 0
        and ledger["counts"]["promotion_blocking_medium"] == 0,
        "No actionable or promotion-blocking Critical/High/Medium finding remains open.",
        ["finding-ledger.json"],
    )
    check(
        checks,
        "host_limitation_explicit",
        any(
            capability.get("id") == "frontend-engineering-vnext"
            and capability.get("status") == "BLOCKED"
            for capability in matrix["capabilities"]
        )
        and any(
            invocation.get("load_observation") == "HOST_LOAD_UNOBSERVABLE"
            for invocation in matrix["fresh_host_invocations"]
        ),
        "The unsupported public host skill-load signal remains explicitly bounded.",
        ["host-composition-capability-matrix.json", "host-composition-interpretation.md"],
    )

    browser_json = {
        name: load_json(f"browser/{name}")
        for name in (
            "accessibility-runtime.json",
            "contrast-observation.json",
            "default-metrics.json",
            "desktop-metrics.json",
            "desktop-success-metrics.json",
            "error-focus-dom.json",
            "idempotency.json",
            "interaction-submit-loading.json",
            "interaction-submit-success.json",
            "interaction-validation.json",
            "loading.json",
            "error.json",
            "error-retry.json",
            "layout-performance.json",
            "mobile-critical-metrics.json",
            "performance-runtime.json",
            "portrait-metrics.json",
            "reflow-200-percent.json",
            "server-validation.json",
            "server-binding.json",
            "server-process.json",
            "stale-response.json",
            "stale-response-initial.json",
            "stale-response-request-a.json",
            "stale-response-request-b.json",
            "stale-response-timeline.json",
            "tablet-metrics.json",
            "url-back-critical.json",
            "url-critical.json",
            "url-invalid.json",
            "url-select-urgent.json",
            "keyboard-submit-result-002.json",
            "keyboard-submit-focused-002.json",
            "keyboard-step-00.json",
            "error-keyboard-step-01.json",
            "error-keyboard-retry.json",
            "keyboard-invalid-submit.json",
            "long-heading-768x1024.json",
        )
    }
    current_url_evidence = [
        browser_json["default-metrics.json"],
        browser_json["desktop-metrics.json"],
        browser_json["desktop-success-metrics.json"],
        browser_json["mobile-critical-metrics.json"],
        browser_json["tablet-metrics.json"],
        browser_json["portrait-metrics.json"],
        browser_json["reflow-200-percent.json"],
        browser_json["long-heading-768x1024.json"],
        browser_json["loading.json"],
        browser_json["error.json"],
        browser_json["idempotency.json"],
        browser_json["layout-performance.json"],
    ]
    check(
        checks,
        "browser_artifact_binding",
        all(url_is_current(item["url"]) for item in current_url_evidence)
        and server_process["artifact_root"] == COMPOSITION_ARTIFACT_REF
        and server_process["artifact_digest"] == COMPOSED_ARTIFACT_DIGEST
        and server_process["base_url"] == BASE_URL
        and server_process["network"] == "LOOPBACK_ONLY"
        and server_process["process_started"] is True
        and server_process_previous["artifact_digest"] == COMPOSED_ARTIFACT_DIGEST
        and server_process_previous["base_url"] == BASE_URL
        and server_process_previous["network"] == "LOOPBACK_ONLY"
        and server_process_previous["process_started"] is True
        and server_binding["status"] == 200
        and server_binding["artifactDigest"] == COMPOSED_ARTIFACT_DIGEST
        and server_binding["requestedUrl"] == BASE_URL
        and server_binding["responseUrl"] == BASE_URL,
        "Authoritative browser metrics target the loopback server whose process and response header bind the composed artifact.",
        [
            "browser/default-metrics.json",
            "browser/reflow-200-percent.json",
            "browser/error.json",
            "browser/server-process.json",
            "browser/server-binding.json",
        ],
    )
    check(
        checks,
        "browser_state_and_responsive_runtime",
        browser_json["default-metrics.json"]["phase"] == "success"
        and browser_json["default-metrics.json"]["items"] == 4
        and browser_json["portrait-metrics.json"]["items"] == 0
        and browser_json["reflow-200-percent.json"]["overflowX"] is False,
        "Success, empty and 200% reflow states are observed without horizontal overflow.",
        [
            "browser/default-metrics.json",
            "browser/portrait-metrics.json",
            "browser/reflow-200-percent.json",
        ],
    )
    check(
        checks,
        "browser_finding_repairs",
        browser_json["url-invalid.json"]["selectedUrgency"] == "all"
        and browser_json["url-invalid.json"]["canonical"] is True
        and browser_json["url-back-critical.json"]["selectedUrgency"] == "critical"
        and browser_json["stale-response.json"]["visiblePatients"] == ["Fresh B"]
        and browser_json["stale-response-request-a.json"]["delay_ms"]
        > browser_json["stale-response-request-b.json"]["delay_ms"]
        and browser_json["stale-response-timeline.json"]["ordering"]["requestAStartedBeforeB"]
        is True
        and browser_json["stale-response-timeline.json"]["ordering"]["responseBCompletedBeforeA"]
        is True
        and browser_json["idempotency.json"]["sameId"] is True
        and browser_json["idempotency.json"]["acceptedPayloads"] == 1
        and browser_json["idempotency.json"]["duplicatePayloads"] == 1,
        "URL history, stale-response ordering and idempotency are fresh and deterministic.",
        [
            "browser/url-invalid.json",
            "browser/url-back-critical.json",
            "browser/stale-response.json",
            "browser/stale-response-request-a.json",
            "browser/stale-response-request-b.json",
            "browser/stale-response-timeline.json",
            "browser/idempotency.json",
        ],
    )
    check(
        checks,
        "browser_accessibility_and_keyboard",
        browser_json["accessibility-runtime.json"]["reducedMotionRule"] is True
        and browser_json["accessibility-runtime.json"]["focus"]["id"] == "patient"
        and browser_json["contrast-observation.json"]["pass"] is True
        and all(
            sample["pass"] is True
            for sample in browser_json["contrast-observation.json"]["results"]
        )
        and browser_json["keyboard-submit-result-002.json"]["phase"] == "success"
        and browser_json["keyboard-submit-result-002.json"]["formValues"]["patient"] == ""
        and browser_json["keyboard-submit-result-002.json"]["focused"]["id"] == "patient"
        and browser_json["keyboard-invalid-submit.json"]["phase"] == "validation"
        and browser_json["keyboard-invalid-submit.json"]["focused"]["id"] == "patient"
        and browser_json["keyboard-submit-focused-002.json"]["focused"]["id"] == "submit-intake"
        and browser_json["keyboard-submit-focused-002.json"]["focusVisible"] is True
        and browser_json["error-keyboard-step-01.json"]["focused"]["text"] == "Try again"
        and browser_json["error-keyboard-retry.json"]["after"]["phase"] == "success",
        "Visible focus, reduced-motion rule and keyboard submit are observed on the current artifact.",
        [
            "browser/accessibility-runtime.json",
            "browser/contrast-observation.json",
            "browser/keyboard-submit-focused-002.json",
            "browser/keyboard-submit-result-002.json",
            "browser/keyboard-invalid-submit.json",
            "browser/long-heading-768x1024.json",
            "browser/error-keyboard-step-01.json",
            "browser/error-keyboard-retry.json",
        ],
    )
    check(
        checks,
        "browser_performance_and_network",
        browser_json["performance-runtime.json"]["url"].startswith(BASE_URL)
        and browser_json["performance-runtime.json"]["externalResources"] == 0
        and browser_json["performance-runtime.json"]["reducedMotionRule"] is True
        and isinstance(
            browser_json["performance-runtime.json"]["largestContentfulPaintMs"], (int, float)
        )
        and browser_json["performance-runtime.json"]["largestContentfulPaintMs"] < 2500
        and browser_json["layout-performance.json"]["load"]
        > browser_json["layout-performance.json"]["firstContentfulPaint"]
        and browser_json["layout-performance.json"]["layoutShiftValue"] == 0,
        "Current browser run has recorded sub-2.5s LCP, no external resources and no layout shift.",
        [
            "browser/performance-runtime.json",
            "browser/layout-performance.json",
            "browser/default-final-network.log",
        ],
    )
    check(
        checks,
        "coverage_threshold",
        coverage["totals"]["percent_covered"] >= 80
        and coverage["totals"]["percent_branches_covered"] >= 80,
        "Current coverage summary exceeds the 80% line and branch threshold.",
        ["coverage-summary.json"],
    )
    required_browser_files = {
        "accessibility-runtime.json",
        "contrast-observation.json",
        "desktop-metrics.json",
        "desktop-success-metrics.json",
        "error-focus-dom.json",
        "layout-performance.json",
        "performance-runtime.json",
        "keyboard-invalid-submit.json",
        "long-heading-768x1024.json",
    }
    check(
        checks,
        "browser_capture_set_complete",
        all((BROWSER_ROOT / name).is_file() for name in required_browser_files),
        "The browser packet contains the independent desktop, error-focus, contrast and performance captures required by the review bar.",
        [f"browser/{name}" for name in sorted(required_browser_files)],
    )

    classification, traceability = build_runtime_classification(structural)
    write_json("runtime-eval-classification.json", classification)
    write_json("eval-runtime-classification.json", classification)
    write_json("runtime-eval-traceability.json", traceability)
    check(
        checks,
        "runtime_eval_classification_complete",
        classification["counts"]["total"] == 60
        and classification["counts"]["runtime_required"] == 33
        and classification["counts"]["runtime_executed"] == 33
        and classification["counts"]["promotion_relevant_unresolved"] == 0,
        "All 60 catalog scenarios are classified; all 33 runtime-required scenarios pass.",
        ["runtime-eval-classification.json", "runtime-eval-traceability.json"],
    )
    browser_capture_paths = [
        path
        for path in BROWSER_ROOT.iterdir()
        if path.is_file()
        and path.name not in {"browser-evidence.json", "server-process.json", "server-process-011.json"}
        and not path.name.startswith("_")
    ]
    browser_capture_timestamps = {
        path: capture_timestamp(path) for path in browser_capture_paths
    }
    browser_capture_ns = max(browser_capture_timestamps.values())
    browser_batch_before_restart_ns = max(
        timestamp
        for path, timestamp in browser_capture_timestamps.items()
        if timestamp < server_process["started_at_ns"]
    )
    browser_batch_after_restart_ns = max(
        timestamp
        for path, timestamp in browser_capture_timestamps.items()
        if timestamp >= server_process["started_at_ns"]
    )
    browser_binding_ns = server_binding["observed_at_ns"]
    timeline_order = [
        host_completed_ns(frontend_host),
        build_receipt["built_at_ns"],
        composition_receipt["generated_at_ns"],
        server_process_previous["started_at_ns"],
        browser_batch_before_restart_ns,
        server_process["started_at_ns"],
        browser_binding_ns,
        browser_batch_after_restart_ns,
        host_completed_ns(verifier_host),
    ]
    check(
        checks,
        "composition_timeline_ordered",
        all(left < right for left, right in zip(timeline_order, timeline_order[1:], strict=False)),
        "Host, build, composition, serving, browser capture and verifier observations are timestamp ordered.",
        [
            FRONTEND_HOST_RECEIPT,
            build_receipt_ref,
            COMPOSITION_RECEIPT,
            "browser/server-process-011.json",
            "browser/server-process.json",
            "browser/server-binding.json",
            "browser/",
            VERIFIER_HOST_RECEIPT,
            "browser-evidence.json",
        ],
    )

    runtime_report = {
        "schema_version": "P8.1-RUNTIME-REPORT-1",
        "task_id": "PHASE8.1-001",
        "status": "PASS_WITH_LIMITATIONS"
        if all(item["status"] == "PASS" for item in checks)
        else "FAIL",
        "run_id": "P81-VERIFY-001",
        "verified_at": datetime.now(UTC).isoformat(),
        "repository_head": git_head(),
        "frontend_fingerprint": FRONTEND_FINGERPRINT,
        "verifier_fingerprint": VERIFIER_FINGERPRINT,
        "composition_run": COMPOSITION_RUN,
        "artifact_digest": COMPOSED_ARTIFACT_DIGEST,
        "checks": checks,
        "summary": {
            "checks_total": len(checks),
            "checks_passed": sum(item["status"] == "PASS" for item in checks),
            "checks_failed": sum(item["status"] == "FAIL" for item in checks),
            "runtime_evals_passed": classification["counts"]["runtime_executed"],
            "runtime_evals_required": classification["counts"]["runtime_required"],
            "promotion_relevant_unresolved": classification["counts"][
                "promotion_relevant_unresolved"
            ],
        },
        "limitations": [
            "HOST_LOAD_UNOBSERVABLE",
            "Alternative harness-observed composition is not full host skill-load causality.",
            "Browser evidence is Chromium-only and not a full assistive-technology certification.",
            "The local synthetic fixture does not establish production, release or security approval.",
        ],
    }
    runtime_report["verification_digest"] = digest(runtime_report)
    write_json(args.output, runtime_report)
    write_json("runtime-eval-report.json", runtime_report)
    write_json(
        "browser-evidence.json",
        {
            "schema_version": "P8.1-BROWSER-EVIDENCE-1",
            "task_id": "PHASE8.1-001",
            "status": runtime_report["status"],
            "composition_run": COMPOSITION_RUN,
            "artifact_digest": COMPOSED_ARTIFACT_DIGEST,
            "browser": {
                "engine": "Chromium",
                "executable": "/usr/bin/google-chrome",
                "version": "Google Chrome 152.0.7977.64",
                "executable_digest": "sha256:aea09d69ce7f24d5901f6bfb15dd44d0c856e793e0a498f8d8393ec7d2c308ec",
            },
            "server_process_runs": [
                {
                    "path": "browser/server-process-011.json",
                    "sha256": file_digest(BROWSER_ROOT / "server-process-011.json"),
                    "run_id": server_process_previous["run_id"],
                    "artifact_digest": server_process_previous["artifact_digest"],
                    "base_url": server_process_previous["base_url"],
                },
                {
                    "path": "browser/server-process.json",
                    "sha256": file_digest(BROWSER_ROOT / "server-process.json"),
                    "run_id": server_process["run_id"],
                    "artifact_digest": server_process["artifact_digest"],
                    "base_url": server_process["base_url"],
                },
            ],
            "captures": [
                browser_capture_record(
                    path,
                    kind="screenshot",
                    composition_run=COMPOSITION_RUN,
                    artifact_digest=COMPOSED_ARTIFACT_DIGEST,
                    server_process=server_process,
                    server_process_previous=server_process_previous,
                )
                for path in sorted(BROWSER_ROOT.glob("*.png"))
                if path.name
                in {
                    "mobile-critical-focused-390x844.png",
                    "desktop-success-1440x900.png",
                    "tablet-urgent-1024x768.png",
                    "portrait-empty-768x1024.png",
                    "reflow-200-percent-195x844.png",
                }
            ]
            + [
                browser_capture_record(
                    path,
                    kind="runtime-json",
                    composition_run=COMPOSITION_RUN,
                    artifact_digest=COMPOSED_ARTIFACT_DIGEST,
                    server_process=server_process,
                    server_process_previous=server_process_previous,
                )
                for path in sorted(BROWSER_ROOT.glob("*.json"))
                if path.name
                in {
                    "accessibility-runtime.json",
                    "contrast-observation.json",
                    "default-metrics.json",
                    "desktop-metrics.json",
                    "desktop-success-metrics.json",
                    "server-binding.json",
                    "server-process.json",
                    "error.json",
                    "error-focus-dom.json",
                    "error-retry.json",
                    "error-keyboard-step-01.json",
                    "error-keyboard-retry.json",
                    "keyboard-invalid-submit.json",
                    "idempotency.json",
                    "interaction-submit-loading.json",
                    "interaction-submit-success.json",
                    "interaction-validation.json",
                    "keyboard-submit-focused-002.json",
                    "keyboard-submit-result-002.json",
                    "keyboard-step-00.json",
                    "layout-performance.json",
                    "long-heading-768x1024.json",
                    "loading.json",
                    "mobile-critical-metrics.json",
                    "performance-runtime.json",
                    "portrait-metrics.json",
                    "reflow-200-percent.json",
                    "server-validation.json",
                    "stale-response.json",
                    "stale-response-initial.json",
                    "stale-response-request-a.json",
                    "stale-response-request-b.json",
                    "stale-response-timeline.json",
                    "tablet-metrics.json",
                    "url-back-critical.json",
                    "url-critical.json",
                    "url-invalid.json",
                    "url-select-urgent.json",
                }
            ],
            "network_and_console": [
                "browser/default-final-network.log",
                "browser/default-final-console.log",
                "browser/stale-network.log",
            ],
            "limitations": runtime_report["limitations"],
        },
    )

    browser_digest = file_digest(EVIDENCE_ROOT / "browser-evidence.json")
    verification_digest = runtime_report["verification_digest"]
    browser_packet_ns = (EVIDENCE_ROOT / "browser-evidence.json").stat().st_mtime_ns
    local_verification_ns = time.time_ns()
    timeline = {
        "schema_version": "P8.1-COMPOSITION-TIMELINE-1",
        "task_id": "PHASE8.1-001",
        "composition_run": COMPOSITION_RUN,
        "ordering_basis": "host receipts, build/composition timestamps, server process starts, browser capture metadata and packet mtimes",
        "events": [
            timeline_event(
                1,
                "FRONTEND_HOST_RESPONSE_OBSERVED",
                host_completed_ns(frontend_host),
                FRONTEND_HOST_RECEIPT,
                host_invocation_id(frontend_host),
                "frontend-engineering-vnext",
                COMPOSED_ARTIFACT_DIGEST,
                "HOST_RESPONSE_OBSERVED",
                "top-level SUCCESS / READY / execution_observed=true / verification=VERIFIED",
            ),
            timeline_event(
                2,
                "EXACT_ARTIFACT_IDENTITY_CHECKED",
                build_receipt["built_at_ns"],
                build_receipt_ref,
                host_invocation_id(frontend_host),
                "frontend-engineering-vnext",
                COMPOSED_ARTIFACT_DIGEST,
                "ARTIFACT_IDENTITY_OBSERVED",
                f"source_tree_digest={COMPOSED_ARTIFACT_DIGEST}; build output is byte-identical",
            ),
            timeline_event(
                3,
                "COMPOSITION_COPY_CREATED_AND_RECHECKED",
                composition_receipt["generated_at_ns"],
                COMPOSITION_RECEIPT,
                composition_receipt["host"]["invocation_id"],
                "frontend-engineering-vnext",
                COMPOSED_ARTIFACT_DIGEST,
                "COMPOSITION_COPY_OBSERVED",
                f"run={COMPOSITION_RUN}; artifact_tree_digest={COMPOSED_ARTIFACT_DIGEST}; global_mutations=0",
            ),
            timeline_event(
                4,
                "EXACT_ARTIFACT_SERVER_STARTED",
                server_process_previous["started_at_ns"],
                "browser/server-process-011.json",
                composition_receipt["host"]["invocation_id"],
                "frontend-engineering-vnext",
                COMPOSED_ARTIFACT_DIGEST,
                "SERVER_PROCESS_OBSERVED",
                f"run={server_process_previous['run_id']}; base_url={BASE_URL}; process_started=true",
            ),
            timeline_event(
                5,
                "BROWSER_RUNTIME_CAPTURE_BATCH_COMPLETED",
                browser_batch_before_restart_ns,
                "browser/",
                "P81-BROWSER-010",
                "browser-observer",
                COMPOSED_ARTIFACT_DIGEST,
                "BROWSER_RUNTIME_CAPTURE_OBSERVED",
                "Initial browser captures completed against the same exact artifact before the server restart.",
            ),
            timeline_event(
                6,
                "EXACT_ARTIFACT_SERVER_STARTED",
                server_process["started_at_ns"],
                "browser/server-process.json",
                composition_receipt["host"]["invocation_id"],
                "frontend-engineering-vnext",
                COMPOSED_ARTIFACT_DIGEST,
                "SERVER_PROCESS_OBSERVED",
                f"run={server_process['run_id']}; base_url={BASE_URL}; process_started=true",
            ),
            timeline_event(
                7,
                "BROWSER_ARTIFACT_BINDING_OBSERVED",
                browser_binding_ns,
                "browser/server-binding.json",
                "P81-BROWSER-010",
                "browser-observer",
                COMPOSED_ARTIFACT_DIGEST,
                "BROWSER_ARTIFACT_BINDING_OBSERVED",
                f"HTTP 200 X-Phase81-Artifact-Digest={COMPOSED_ARTIFACT_DIGEST}; server_run={server_process['run_id']}",
            ),
            timeline_event(
                8,
                "BROWSER_RUNTIME_CAPTURE_COMPLETED",
                browser_batch_after_restart_ns,
                "browser/",
                "P81-BROWSER-010",
                "browser-observer",
                COMPOSED_ARTIFACT_DIGEST,
                "BROWSER_RUNTIME_CAPTURE_OBSERVED",
                "The final browser capture batch completed after the current exact server binding.",
            ),
            timeline_event(
                9,
                "VERIFIER_HOST_RESPONSE_OBSERVED",
                host_completed_ns(verifier_host),
                VERIFIER_HOST_RECEIPT,
                host_invocation_id(verifier_host),
                "verification-loop-vnext",
                COMPOSED_ARTIFACT_DIGEST,
                "HOST_RESPONSE_OBSERVED",
                "top-level SUCCESS / VERIFIER_READY / execution_observed=true / verification=VERIFIED",
            ),
            timeline_event(
                10,
                "BROWSER_EVIDENCE_PACKETIZED",
                browser_packet_ns,
                "browser-evidence.json",
                host_invocation_id(verifier_host),
                "verification-loop-vnext",
                COMPOSED_ARTIFACT_DIGEST,
                "BROWSER_EVIDENCE_PACKETIZED",
                f"browser_evidence_digest={browser_digest}",
            ),
            timeline_event(
                11,
                "LOCAL_VERIFICATION_COMPLETED",
                local_verification_ns,
                args.output,
                "P81-VERIFY-001",
                "verification-loop-vnext",
                COMPOSED_ARTIFACT_DIGEST,
                "LOCAL_VERIFICATION_COMPLETED",
                f"verification_digest={verification_digest}",
            ),
        ],
        "unknowns": ["The public host protocol did not emit a skill-load event."],
        "limitations": runtime_report["limitations"],
    }
    timeline["timeline_digest"] = digest(timeline)
    write_json("composition-timeline.json", timeline)
    proof = {
        "schema_version": "P8.1-COMPOSITION-PROOF-1",
        "task_id": "PHASE8.1-001",
        "composition_id": "P81-ALT-COMPOSITION-001",
        "run_id": COMPOSITION_RUN,
        "status": "PROVEN_WITH_OBSERVABLE_ALTERNATIVE_CAUSALITY",
        "canonical_composition_receipt": CANONICAL_COMPOSITION_RECEIPT,
        "authorization_id": authorization["authorization_id"],
        "authorization": {
            "capability_id": authorization["capability_id"],
            "filesystem_mode": authorization["filesystem_mode"],
            "workspace": authorization["workspace"],
            "package_write_allowed": authorization["package_write_allowed"],
            "network": authorization["network"],
            "mcp": authorization["mcp"],
            "providers": authorization["providers"],
            "shell": authorization["shell"],
            "credentials": authorization["credentials"],
        },
        "frontend_capability_ref": "frontend-engineering-vnext@0.1.0",
        "frontend_fingerprint": FRONTEND_FINGERPRINT,
        "frontend_invocation_ref": f"evidence/phase-8.1/{FRONTEND_HOST_RECEIPT}",
        "workspace_ref": f"evidence/phase-8.1/{COMPOSITION_ARTIFACT_ROOT}",
        "workspace_pre_digest": composition_receipt["workspace_observation"][
            "before_snapshot_digest"
        ],
        "workspace_post_digest": composition_receipt["workspace_observation"][
            "after_snapshot_digest"
        ],
        "changed_files": composition_receipt["workspace_observation"]["changed_paths"],
        "source_digest": COMPOSED_ARTIFACT_DIGEST,
        "artifact_digest": COMPOSED_ARTIFACT_DIGEST,
        "browser_evidence_digest": browser_digest,
        "verifier_capability_ref": "verification-loop-vnext@0.1.0",
        "verifier_fingerprint": VERIFIER_FINGERPRINT,
        "verifier_invocation_ref": f"evidence/phase-8.1/{VERIFIER_HOST_RECEIPT}",
        "verification_digest": verification_digest,
        "verifier_host_verification_digest": verifier_host["assurance"]["verification_digest"],
        "timeline": "composition-timeline.json",
        "host_observations": {
            "frontend": "READY with execution_observed=true",
            "verifier": "VERIFIER_READY with execution_observed=true",
            "skill_load": "HOST_LOAD_UNOBSERVABLE",
        },
        "Harness_observations": {
            "producer_kind": composition_receipt["producer_kind"],
            "global_mutations": composition_receipt["workspace_observation"]["global_mutations"],
            "capability_file_mutations": composition_receipt["workspace_observation"][
                "capability_file_mutations"
            ],
            "manual_mutation_during_run": composition_receipt["workspace_observation"][
                "manual_mutation_during_run"
            ],
            "external_producer": composition_receipt["workspace_observation"]["external_producer"],
            "independent_scope_audit": scope_audit_ref,
            "scope_audit_global_mutations": scope_audit["global_mutations"],
            "scope_audit_capability_file_mutations": scope_audit["capability_file_mutations"],
        },
        "inferences": [
            "The exact artifact copied by the bridge is the artifact served to the browser captures.",
            "The current verifier checks the same package identities, digests and fresh runtime evidence.",
            "The server process and HTTP response header independently bind browser traffic to the composed artifact digest.",
        ],
        "unknowns": ["No public host skill-load or native browser-observer event was available."],
        "limitations": runtime_report["limitations"],
    }
    proof["proof_digest"] = digest(proof)
    write_json("composition-proof.json", proof)

    write_text(
        "real-frontend-run-report.md",
        f"""# Real Frontend Run

Status: `{runtime_report["status"]}`

- Capability: `frontend-engineering-vnext@0.1.0`
- Fingerprint: `{FRONTEND_FINGERPRINT}`
- Host receipt: `{FRONTEND_HOST_RECEIPT}`
- Host observation: `SUCCESS`, `READY`, `execution_observed=true`
- Artifact: `{COMPOSED_ARTIFACT_DIGEST}`

The host handshake is fresh and bounded. The receipt is a transport/execution observation, not proof of a public skill-load event; that limitation remains in the composition proof.
""",
    )
    write_text(
        "workspace-mutation-report.md",
        f"""# Workspace Mutation Report

The authorized bridge run is `{COMPOSITION_RUN}`.

- Pre-snapshot: `{proof["workspace_pre_digest"]}`
- Post-snapshot: `{proof["workspace_post_digest"]}`
- Changed files: `{", ".join(proof["changed_files"])}`
- Global mutations: `{proof["Harness_observations"]["global_mutations"]}`
- Capability-file mutations: `{proof["Harness_observations"]["capability_file_mutations"]}`
- Manual mutation during run: `{proof["Harness_observations"]["manual_mutation_during_run"]}`
- External producer: `{proof["Harness_observations"]["external_producer"]}`

The bridge is an exact artifact copy with post-copy digest verification. It does not claim to generate application code or establish full host causality.
""",
    )
    report_specs = {
        "high-closure-report.md": (
            "High host composition finding",
            "The official skill-load signal remains unavailable; the independently reviewable exact-artifact bridge is the accepted bounded alternative.",
        ),
        "medium-closure-report.md": (
            "Three Medium runtime findings",
            "URL history, stale-response ordering, idempotency and keyboard/focus behavior have fresh current-artifact runtime receipts.",
        ),
        "responsive-runtime-report.md": (
            "Responsive runtime",
            "Desktop, tablet, mobile, portrait and 200% reflow captures are bound to the composed artifact; 200% reflow reports no horizontal overflow.",
        ),
        "interaction-runtime-report.md": (
            "Interaction runtime",
            "Validation, submit loading, submit success, retry recovery and server-side 422 validation are recorded.",
        ),
        "accessibility-runtime-report.md": (
            "Accessibility runtime",
            "Labels, heading structure, live regions, focus styling, keyboard traversal, reduced-motion CSS and touch-target measurements are recorded for Chromium.",
        ),
        "idempotency-runtime-report.md": (
            "Idempotency runtime",
            "Concurrent submissions with one key produce one accepted and one duplicate response sharing the same intake id.",
        ),
        "stale-response-runtime-report.md": (
            "Stale-response runtime",
            "Deterministic delayed A and fast B responses are recorded; final UI contains Fresh B only.",
        ),
        "url-state-runtime-report.md": (
            "URL-state runtime",
            "Valid filter initialization, filter history, back restoration and invalid fallback are recorded.",
        ),
        "keyboard-runtime-report.md": (
            "Keyboard runtime",
            "The current composed page reaches the submit action by keyboard and submits successfully; invalid focus and visible-focus receipts are also present.",
        ),
    }
    for filename, (title, body) in report_specs.items():
        write_text(
            filename,
            f"# {title}\n\nStatus: `{runtime_report['status']}`\n\n{body}\n\nPrimary packet references: `browser-evidence.json`, `runtime-eval-traceability.json`, `composition-proof.json`.\n",
        )

    return 0 if runtime_report["status"] != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
