# ruff: noqa: E402
"""Run a neutral, evidence-reading verification-loop-vnext host turn."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from harness_kernel.phase4_host import _resolve_host_binding
from harness_kernel.phase4_models import ExecutionMode, Phase4Budget, public_data
from harness_kernel.phase6_host import discover_vnext_package, prepare_vnext_preflight
from harness_kernel.phase7_backend import package_fingerprint, snapshot_workspace
from harness_kernel.phase7_host import WorkspaceWriteMode, build_backend_filesystem_policy
from harness_kernel.phase81_host import Phase81VerifierAppServerAdapter

EVIDENCE_ROOT = PROJECT_ROOT / "evidence" / "phase-8.1"
ARTIFACT_ROOT = EVIDENCE_ROOT / "composition-run-013" / "frontend-artifact"
FRONTEND_RECEIPT = EVIDENCE_ROOT / "frontend-real-005" / "invocation-receipt.json"
FRONTEND_EVENTS = EVIDENCE_ROOT / "frontend-real-005" / "host-events.json"
BUILD_RECEIPT = EVIDENCE_ROOT / "frontend-real-005" / "build-receipt.json"
BROWSER_RECEIPT = EVIDENCE_ROOT / "browser-evidence-018.json"
POLICY_PATH = PROJECT_ROOT / "config" / "phase8.1-execution-policy.json"
PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / "verification-loop-vnext"
FRONTEND_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / "frontend-engineering-vnext"
INPUT_ROOT = EVIDENCE_ROOT / "verifier-input-010"
OUTPUT_ROOT = EVIDENCE_ROOT / "verifier-real-010"
RECEIPT_PATH = OUTPUT_ROOT / "invocation-receipt.json"
EVENTS_PATH = OUTPUT_ROOT / "host-events.json"

TASK_ID = "PHASE8.1-001"
RUN_ID = "P81-VERIFY-010"
COMPOSITION_RUN = "P81-COMPOSE-013"
ARTIFACT_DIGEST = "sha256:e3306ed2bdf13317f7486af6e61b0e4182abbc25d3d9e0fdfdb3dd8c4519643a"
CRITERION_IDS = (
    "P81-V-INPUT-INTEGRITY",
    "P81-V-HOST-MUTATION",
    "P81-V-ARTIFACT-LINEAGE",
    "P81-V-RUNTIME-CATALOG",
    "P81-V-BROWSER-FRESHNESS",
)
CATALOG_IDS = tuple(
    [f"P8-EVAL-{value:03d}" for value in range(11, 28)]
    + [f"P8-EVAL-{value:03d}" for value in range(29, 38)]
    + [f"P8-EVAL-{value:03d}" for value in range(39, 44)]
    + ["P8-EVAL-050", "P8-EVAL-053"]
)
ARTIFACT_FILES = ("index.html", "styles.css", "app.js", "fixture_server.py")


def digest_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def digest_file(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def digest_value(value: object) -> str:
    return digest_bytes(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected an object: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_report(message: str) -> dict[str, Any] | None:
    start = message.find("{")
    end = message.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        value = json.loads(message[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _copy_input(source: Path, relative: str, staged: list[dict[str, object]]) -> None:
    target = INPUT_ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    staged.append(
        {
            "path": relative,
            "origin": source.relative_to(PROJECT_ROOT).as_posix(),
            "sha256": digest_file(target),
            "bytes": target.stat().st_size,
        }
    )


def stage_verifier_input(
    browser: dict[str, Any],
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    if INPUT_ROOT.exists() or OUTPUT_ROOT.exists():
        raise RuntimeError("fresh verifier input/output path already exists")
    staged: list[dict[str, object]] = []
    for source, relative in (
        (FRONTEND_RECEIPT, "core/frontend-invocation.json"),
        (FRONTEND_EVENTS, "core/frontend-host-events.json"),
        (BUILD_RECEIPT, "core/build-receipt.json"),
        (BROWSER_RECEIPT, "core/browser-manifest.json"),
        (POLICY_PATH, "core/execution-policy.json"),
    ):
        _copy_input(source, relative, staged)
    for name in ARTIFACT_FILES:
        _copy_input(ARTIFACT_ROOT / name, f"artifact/{name}", staged)

    checks = browser.get("checks")
    if not isinstance(checks, list):
        raise RuntimeError("browser checks are missing")
    catalog_evidence: dict[str, str] = {}
    for check in checks:
        if not isinstance(check, dict) or check.get("id") not in CATALOG_IDS:
            continue
        evidence = check.get("evidence")
        if not isinstance(evidence, str):
            raise RuntimeError("catalog check evidence is missing")
        source = EVIDENCE_ROOT / evidence
        relative = f"runtime/{source.name}"
        catalog_evidence[str(check["id"])] = relative
        if not any(item["path"] == relative for item in staged):
            _copy_input(source, relative, staged)
    if tuple(sorted(catalog_evidence)) != tuple(sorted(CATALOG_IDS)):
        raise RuntimeError("browser manifest does not contain the exact runtime catalog")

    captures = browser.get("captures")
    if not isinstance(captures, list):
        raise RuntimeError("browser captures are missing")
    for capture in captures:
        if not isinstance(capture, dict) or not isinstance(capture.get("path"), str):
            raise RuntimeError("browser capture is malformed")
        source = EVIDENCE_ROOT / capture["path"]
        prefix = "screenshots" if capture.get("kind") == "screenshot" else "runtime"
        relative = f"{prefix}/{source.name}"
        if not any(item["path"] == relative for item in staged):
            _copy_input(source, relative, staged)

    index = {
        "schema_version": "P8.1-VERIFIER-INPUT-INDEX-1",
        "task_id": TASK_ID,
        "run_id": RUN_ID,
        "composition_run": COMPOSITION_RUN,
        "artifact_digest": ARTIFACT_DIGEST,
        "files": sorted(staged, key=lambda item: str(item["path"])),
        "catalog_evidence": catalog_evidence,
    }
    write_json(INPUT_ROOT / "input-index.json", index)
    required_inspections = (
        "input-index.json",
        "core/frontend-invocation.json",
        "core/frontend-host-events.json",
        "core/build-receipt.json",
        "core/browser-manifest.json",
        "core/execution-policy.json",
        *sorted(set(catalog_evidence.values())),
    )
    required_hashes = (
        "input-index.json",
        *sorted(str(item["path"]) for item in staged),
    )
    return index, required_inspections, required_hashes


def file_observations(events: object) -> tuple[dict[str, str], dict[str, str]]:
    reads: dict[str, str] = {}
    observed: dict[str, str] = {}
    if not isinstance(events, (list, tuple)):
        return reads, observed
    for event in events:
        detail = getattr(event, "detail", None)
        if not isinstance(detail, str) or not detail.startswith(
            ("tool=harness_read_file path=", "tool=harness_hash_file path=")
        ):
            continue
        path = detail.split(" path=", 1)[1].split(" bytes=", 1)[0]
        marker = " sha256="
        if marker in detail:
            observed[path] = detail.split(marker, 1)[1].split(" ", 1)[0]
            if detail.startswith("tool=harness_read_file path="):
                reads[path] = observed[path]
    return reads, observed


def report_errors(
    report: dict[str, Any] | None,
    handoff: dict[str, Any],
    required_inspections: tuple[str, ...],
    required_hashes: tuple[str, ...],
    expected_digests: dict[str, str],
    host_reads: dict[str, str],
    host_files: dict[str, str],
) -> list[str]:
    if report is None:
        return ["HOST_REPORT_NOT_JSON"]
    errors: list[str] = []
    for key, expected in {
        "marker": "P81_VERIFIER_REPORT",
        "input_digest": handoff["input_digest"],
        "artifact_digest": ARTIFACT_DIGEST,
        "criterion_set_digest": handoff["criterion_set_digest"],
        "frontend_fingerprint": handoff["expected"]["frontend_fingerprint"],
        "verifier_fingerprint": handoff["expected"]["verifier_fingerprint"],
        "browser_evidence_digest": handoff["expected"]["browser_manifest_digest"],
    }.items():
        if report.get(key) != expected:
            errors.append(f"HOST_REPORT_{key.upper()}_MISMATCH")

    criteria = report.get("criteria")
    criterion_statuses: dict[str, str] = {}
    if not isinstance(criteria, list):
        errors.append("HOST_REPORT_CRITERIA_MISSING")
    else:
        for item in criteria:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                errors.append("HOST_REPORT_CRITERION_INVALID")
                continue
            status = item.get("status")
            if status not in {"PASS", "FAIL", "BLOCKED"}:
                errors.append("HOST_REPORT_CRITERION_STATUS_INVALID")
                continue
            criterion_statuses[item["id"]] = status
            if not item.get("procedure") or not item.get("evidence") or not item.get("finding"):
                errors.append("HOST_REPORT_CRITERION_LINEAGE_INCOMPLETE")
        if set(criterion_statuses) != set(CRITERION_IDS):
            errors.append("HOST_REPORT_CRITERION_SET_MISMATCH")

    inspected = report.get("inspected_file_digests")
    if not isinstance(inspected, dict):
        errors.append("HOST_REPORT_INSPECTIONS_MISSING")
    else:
        for path in required_hashes:
            if inspected.get(path) != expected_digests.get(path):
                errors.append(f"HOST_REPORT_INSPECTION_DIGEST_MISMATCH:{path}")
            if host_files.get(path) != expected_digests.get(path):
                errors.append(f"HOST_FILE_EVENT_MISSING:{path}")
        for path in required_inspections:
            if host_reads.get(path) != expected_digests.get(path):
                errors.append(f"HOST_CONTENT_READ_EVENT_MISSING:{path}")

    all_pass = bool(criterion_statuses) and all(
        status == "PASS" for status in criterion_statuses.values()
    )
    any_fail = any(status == "FAIL" for status in criterion_statuses.values())
    expected_status = "PASS_WITH_LIMITATIONS" if all_pass else "FAIL" if any_fail else "PARTIAL"
    expected_stop = "ALL_REQUIRED_CRITERIA_RESOLVED" if all_pass else "UNRESOLVED_CRITERIA"
    if report.get("report_status") != expected_status:
        errors.append("HOST_REPORT_AGGREGATE_STATUS_INVALID")
    if report.get("stop_decision") != expected_stop:
        errors.append("HOST_REPORT_STOP_DECISION_INVALID")
    limitations = report.get("limitations")
    if not isinstance(limitations, list) or "HOST_LOAD_UNOBSERVABLE" not in limitations:
        errors.append("HOST_REPORT_LIMITATION_MISSING")
    return list(dict.fromkeys(errors))


def main() -> int:
    frontend = read_json(FRONTEND_RECEIPT)
    build = read_json(BUILD_RECEIPT)
    browser = read_json(BROWSER_RECEIPT)
    frontend_fingerprint = package_fingerprint(FRONTEND_ROOT)
    verifier_fingerprint = package_fingerprint(PACKAGE_ROOT)
    if frontend_fingerprint != frontend["package_fingerprint"]:
        raise RuntimeError("frontend package fingerprint drifted")
    if browser.get("status") != "PASS" or browser.get("summary", {}).get("failed") != 0:
        raise RuntimeError("browser evidence is not fully passing")
    if not (
        frontend["source"]["digest"]
        == build["source_digest"]
        == build["artifact_digest"]
        == browser["artifact_digest"]
        == ARTIFACT_DIGEST
    ):
        raise RuntimeError("source, build, artifact and browser identities are not equal")

    index, required_inspections, required_hashes = stage_verifier_input(browser)
    expected_digests = {str(item["path"]): str(item["sha256"]) for item in index["files"]}
    expected_digests["input-index.json"] = digest_file(INPUT_ROOT / "input-index.json")
    criteria = [
        {
            "id": CRITERION_IDS[0],
            "question": (
                "Do staged file bytes match the immutable input index and exact identities?"
            ),
            "procedure": (
                "List workspace; read index and every required path; compare host SHA-256."
            ),
        },
        {
            "id": CRITERION_IDS[1],
            "question": "Do raw frontend events expose writes for exactly the changed files?",
            "procedure": (
                "Compare invocation delta/event paths with raw host tool events and counters."
            ),
        },
        {
            "id": CRITERION_IDS[2],
            "question": "Are source, build and artifact identities tied to P81-COMPOSE-013?",
            "procedure": (
                "Compare frontend, build and browser receipts for equal digests and run IDs."
            ),
        },
        {
            "id": CRITERION_IDS[3],
            "question": (
                "Are exactly 33 unique catalog IDs backed by matching passed runtime evidence?"
            ),
            "procedure": (
                "Read manifest and catalog evidence; reject unrelated/missing/failed mappings."
            ),
        },
        {
            "id": CRITERION_IDS[4],
            "question": "Is browser evidence fresh, complete and bound to the exact artifact?",
            "procedure": (
                "Compare timestamps, identities, failures, captures and console observations."
            ),
        },
    ]
    handoff: dict[str, Any] = {
        "schema_version": "P8.1-VERIFICATION-INPUT-2",
        "task_id": TASK_ID,
        "run_id": RUN_ID,
        "composition_run": COMPOSITION_RUN,
        "role": "VERIFIER_ONLY",
        "expected": {
            "artifact_digest": ARTIFACT_DIGEST,
            "frontend_fingerprint": frontend_fingerprint,
            "verifier_fingerprint": verifier_fingerprint,
            "frontend_invocation_id": frontend["invocation_id"],
            "authorization_id": frontend["authorization_id"],
            "browser_manifest_digest": digest_file(BROWSER_RECEIPT),
            "input_index_digest": expected_digests["input-index.json"],
            "catalog_ids": CATALOG_IDS,
            "catalog_count": 33,
        },
        "criteria": criteria,
        "criterion_set_digest": digest_value(criteria),
        "required_inspections": required_inspections,
        "required_hashes": required_hashes,
        "decision_rules": {
            "all_criteria_pass": "PASS_WITH_LIMITATIONS",
            "any_criterion_fail": "FAIL",
            "otherwise": "PARTIAL",
            "pass_stop": "ALL_REQUIRED_CRITERIA_RESOLVED",
            "nonpass_stop": "UNRESOLVED_CRITERIA",
        },
        "known_limitations": [
            "HOST_LOAD_UNOBSERVABLE",
            "Chromium-only; no cross-browser or assistive-technology certification.",
        ],
    }
    handoff["input_digest"] = digest_value(handoff)
    prompt = json.dumps(
        {
            "instruction": (
                "Independently verify neutral questions from immutable workspace files. MUST "
                "call harness_list_files and harness_read_file for every required_inspections "
                "path. For every required_hashes path not in required_inspections, use exactly "
                "one harness_hash_file call; do not content-read those extra files. Every digest "
                "must come from a read/hash response. PASS is not "
                "prescribed. Return one JSON object with these exact top-level keys: marker "
                "(P81_VERIFIER_REPORT), input_digest, artifact_digest, criterion_set_digest, "
                "frontend_fingerprint, verifier_fingerprint, browser_evidence_digest, "
                "report_status, stop_decision, limitations, inspected_file_digests, and criteria. "
                "Each of five criteria needs id/status/procedure/evidence/finding. FAIL "
                "contradictions; BLOCKED insufficient evidence. Do not approve promotion or judge "
                "visual taste."
            ),
            "verification_input": handoff,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(prompt.encode()) > 64_000:
        raise RuntimeError("bounded verifier handoff exceeds context budget")

    snapshot = discover_vnext_package(PROJECT_ROOT)
    if snapshot.package_digest != verifier_fingerprint or snapshot.blockers:
        raise RuntimeError(f"verifier discovery drifted: {snapshot.blockers}")
    budget = Phase4Budget(
        timeout_seconds=240,
        max_context_bytes=64_000,
        max_host_events=4_096,
        max_tool_calls=0,
        max_output_bytes=64_000,
    )
    preflight = prepare_vnext_preflight(
        PROJECT_ROOT,
        snapshot=snapshot,
        task_id=TASK_ID,
        run_id=RUN_ID,
        task=prompt,
        acceptance_criteria=(
            "inspect every required immutable file through bounded read tools",
            "evaluate five neutral factual criteria without a prescribed PASS",
            "derive aggregate status mechanically from criterion statuses",
            "retain HOST_LOAD_UNOBSERVABLE and make no promotion decision",
        ),
        workspace=INPUT_ROOT,
        policy_path=POLICY_PATH,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=budget,
    )
    if not preflight.allowed or preflight.prepared is None or preflight.prepared.request is None:
        raise RuntimeError(f"verifier preflight blocked: {preflight.blockers}")
    request = preflight.prepared.request
    authorization = request.authorization
    raw_package = authorization.filesystem_policy.get("package_path")
    if not isinstance(raw_package, str):
        raise RuntimeError("verifier package path is not authorized")
    filesystem_policy = build_backend_filesystem_policy(
        INPUT_ROOT,
        mode=WorkspaceWriteMode.READ_ONLY,
        allowed_roots=(INPUT_ROOT,),
        package_path=raw_package,
    )
    binding = _resolve_host_binding()
    workspace_before = snapshot_workspace(INPUT_ROOT)
    started_at_ns = time.time_ns()
    adapter = Phase81VerifierAppServerAdapter(
        filesystem_policy=filesystem_policy,
        project_root=PROJECT_ROOT,
        trusted_authorization=authorization,
    )
    result = adapter.request_invocation(request, budget=budget)
    completed_at_ns = time.time_ns()
    workspace_after = snapshot_workspace(INPUT_ROOT)
    final_message = result.final_message or ""
    report = parse_report(final_message)
    host_reads, host_files = file_observations(result.events)
    errors = report_errors(
        report,
        handoff,
        required_inspections,
        required_hashes,
        expected_digests,
        host_reads,
        host_files,
    )
    if result.status.value != "SUCCESS":
        errors.append(f"HOST_STATUS_{result.status.value}")
    if not result.invocation_observed or not result.execution_observed:
        errors.append("HOST_EXECUTION_NOT_OBSERVED")
    if result.approval_request_count:
        errors.append("APPROVAL_REQUEST_OBSERVED")
    if result.mcp_event_count:
        errors.append("MCP_EVENT_OBSERVED")
    if workspace_before != workspace_after:
        errors.append("VERIFIER_WORKSPACE_MUTATION")
    delta = adapter.last_workspace_delta
    if delta is None or not delta.ok:
        errors.append("VERIFIER_DELTA_NOT_CLEAN")
    errors = list(dict.fromkeys(errors))
    report_status = report.get("report_status") if isinstance(report, dict) else None
    status = report_status if not errors and isinstance(report_status, str) else "FAIL"
    write_json(
        EVENTS_PATH,
        {
            "events": public_data(result.events),
            "read_observations": host_reads,
            "file_observations": host_files,
        },
    )
    receipt: dict[str, Any] = {
        "schema_version": "P8.1-REAL-VERIFIER-RECEIPT-2",
        "task_id": TASK_ID,
        "run_id": RUN_ID,
        "composition_run": COMPOSITION_RUN,
        "invocation_id": request.invocation_id,
        "status": status,
        "errors": errors,
        "input": handoff,
        "input_bytes": len(prompt.encode()),
        "input_index": index,
        "input_index_digest": expected_digests["input-index.json"],
        "package": {
            "capability_id": snapshot.capability_id,
            "package_fingerprint": verifier_fingerprint,
            "manifest_digest": snapshot.manifest_digest,
            "load_level": snapshot.load_level.value,
            "instruction_loaded": snapshot.instruction_loaded,
            "host_load_observation": snapshot.host_load_observation,
            "typed_skill_input": {
                "type": "skill",
                "name": "verification-loop-vnext",
                "path": "$PROJECT/.harness/capabilities/verification-loop-vnext/SKILL.md",
            },
        },
        "authorization": public_data(authorization),
        "preflight": {
            "allowed": preflight.allowed,
            "digest": preflight.digest,
            "warnings": list(preflight.warnings),
            "blockers": list(preflight.blockers),
        },
        "host": {
            "status": result.status.value,
            "invocation_observed": result.invocation_observed,
            "execution_observed": result.execution_observed,
            "error_code": result.error_code,
            "session_id": result.session_id,
            "thread_id": result.thread_id,
            "turn_id": result.turn_id,
            "protocol_message_count": result.protocol_message_count,
            "mcp_event_count": result.mcp_event_count,
            "approval_request_count": result.approval_request_count,
            "executable_digest": binding[2],
            "interpreter_digest": binding[5],
            "final_message": final_message,
            "response_digest": digest_bytes(final_message.encode()),
            "read_event_count": len(host_reads),
            "file_observation_count": len(host_files),
            "read_observations": host_reads,
            "file_observations": host_files,
        },
        "report": report,
        "report_valid": not errors,
        "workspace": {
            "root": "verifier-input-010",
            "mode": "READ_ONLY",
            "unchanged": workspace_before == workspace_after,
            "delta_ok": delta is not None and delta.ok,
        },
        "timeline": {"started_at_ns": started_at_ns, "completed_at_ns": completed_at_ns},
        "limitations": [
            "HOST_LOAD_UNOBSERVABLE",
            "Verifier is factual evidence authority, not promotion/release/visual authority.",
        ],
    }
    write_json(RECEIPT_PATH, receipt)
    print(
        json.dumps(
            {
                "status": status,
                "errors": errors,
                "invocation_id": request.invocation_id,
                "thread_id": result.thread_id,
                "turn_id": result.turn_id,
                "read_event_count": len(host_reads),
                "file_observation_count": len(host_files),
                "response_digest": receipt["host"]["response_digest"],
            },
            sort_keys=True,
        )
    )
    return 0 if status == "PASS_WITH_LIMITATIONS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
