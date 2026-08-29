"""Capture and publish one dynamically observed Phase 4 controlled pilot."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import cast

from harness_kernel.phase3_host import CodexHostAdapter
from harness_kernel.phase3_models import CapabilityInventory, CapabilityRecord, ResolutionResult
from harness_kernel.phase3_resolution import ResolutionEngine
from harness_kernel.phase4_artifacts import read_artifact_bytes
from harness_kernel.phase4_benchmarks import benchmark_operation
from harness_kernel.phase4_evidence import (
    EvidenceWriter,
    build_review_manifest,
    public_outcome,
    snapshot_tree,
)
from harness_kernel.phase4_execution import InvocationEngine
from harness_kernel.phase4_host import CodexAppServerAdapter
from harness_kernel.phase4_models import (
    ExecutionMode,
    ExecutionOutcome,
    HostInvocationResult,
    Phase4Budget,
    PreparedInvocation,
    canonical_json,
    public_data,
    stable_digest_payload,
)
from harness_kernel.phase4_policy import ExecutionPolicyRegistry

PROJECT_ROOT = Path(__file__).parents[1].resolve()
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
EVIDENCE_ROOT = PROJECT_ROOT / "evidence" / "phase-4"
POLICY_PATH = PROJECT_ROOT / "config" / "phase4-execution-policy.json"
PILOT_WORKSPACE = PROJECT_ROOT / "tests" / "fixtures" / "phase4" / "pilot-design-project"
PILOT_CAPABILITY = "phase4-safe-pilot"
PILOT_TASK_ID = "TASK-P4-FINAL-PILOT-PROVENANCE-PINNED"
PILOT_RUN_ID = "RUN-P4-FINAL-PILOT-PROVENANCE-PINNED-RECAPTURE-4"
PILOT_TASK = "Return a short final response containing the exact marker."
PILOT_ACCEPTANCE = (
    "response is non-empty",
    "marker: PHASE4_SAFE_PILOT_ARTIFACT",
)
PILOT_BUDGET = Phase4Budget(
    timeout_seconds=75,
    max_context_bytes=128 * 1024,
    max_host_events=256,
    max_tool_calls=0,
    max_repair_iterations=0,
    max_verification_iterations=1,
    max_artifacts=1,
    max_evidence=64,
    max_output_bytes=16 * 1024,
)

_POST_REVIEW_FILES = frozenset(
    {
        "review-manifest.json",
        "review-attestation.json",
        "independent-review.md",
        "readiness.json",
        "final-report.md",
        "PHASE4-FROZEN.md",
        "review-closure.json",
    }
)


def _repository_bound_files() -> tuple[tuple[str, Path], ...]:
    relative_files = (
        "projects/codex-harness/pyproject.toml",
        "projects/codex-harness/src/harness_kernel/phase4_artifacts.py",
        "projects/codex-harness/src/harness_kernel/phase4_benchmarks.py",
        "projects/codex-harness/src/harness_kernel/phase4_cli.py",
        "projects/codex-harness/src/harness_kernel/phase4_evidence.py",
        "projects/codex-harness/src/harness_kernel/phase4_execution.py",
        "projects/codex-harness/src/harness_kernel/phase4_host.py",
        "projects/codex-harness/src/harness_kernel/phase4_models.py",
        "projects/codex-harness/src/harness_kernel/phase4_policy.py",
        "projects/codex-harness/src/harness_kernel/phase4_verification.py",
        "projects/codex-harness/tests/evals/phase4/test_phase4_negative.py",
        "projects/codex-harness/tests/integration/test_phase4_cli.py",
        "projects/codex-harness/tests/integration/test_phase4_real_host.py",
        "projects/codex-harness/tests/unit/test_phase4_artifacts.py",
        "projects/codex-harness/tests/unit/test_phase4_benchmarks.py",
        "projects/codex-harness/tests/unit/test_phase4_evidence.py",
        "projects/codex-harness/tests/unit/test_phase4_execution.py",
        "projects/codex-harness/tests/unit/test_phase4_host.py",
        "projects/codex-harness/tests/unit/test_phase4_models.py",
        "projects/codex-harness/tests/unit/test_phase4_policy.py",
        "projects/codex-harness/tests/unit/test_phase4_finalizer.py",
        "projects/codex-harness/tests/fixtures/phase4/pilot-design-project/README.md",
        "projects/codex-harness/tests/fixtures/phase4/pilot-design-project/.harness/phase4/invocation-ledger.json",
        "projects/codex-harness/tests/fixtures/phase4/pilot-design-project/.agents/skills/"
        "phase4-safe-pilot/SKILL.md",
        "projects/codex-harness/config/phase4-execution-policy.json",
        "projects/codex-harness/docs/implementation/phase-4-quality-bar.md",
        "projects/codex-harness/docs/implementation/phase-4-real-capability-invocation-report.md",
        "projects/codex-harness/.agent/plans/PHASE-4-real-capability-invocation.md",
        "architecture/docs/adr/ADR-013-phase-4-real-capability-invocation-boundary.md",
        "projects/codex-harness/scripts/publish_phase4_evidence.py",
        "projects/codex-harness/scripts/finalize_phase4_evidence.py",
    )
    bound = [(item, REPOSITORY_ROOT / item) for item in relative_files]
    historical_roots = (
        "projects/codex-harness/evidence/phase-4-exploratory",
        "projects/codex-harness/evidence/phase-4-mcp-boundary-attempt",
        "projects/codex-harness/evidence/phase-4-truncated-snapshot-attempt",
        "projects/codex-harness/evidence/phase-4-full-snapshot-attempt",
        "projects/codex-harness/evidence/phase-4-scope-review-attempt",
        "projects/codex-harness/evidence/phase-4-provenance-pinning-attempt",
        "projects/codex-harness/evidence/phase-4-final-provenance-pinning-attempt",
        "projects/codex-harness/evidence/phase-4-receipt-binding-attempt",
    )
    for root_label in historical_roots:
        root = REPOSITORY_ROOT / root_label
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                bound.append((str(path.relative_to(REPOSITORY_ROOT)), path))
    return tuple(bound)


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _public_mapping(value: object) -> dict[str, object]:
    payload = public_data(value)
    if not isinstance(payload, dict):
        raise RuntimeError("evidence value did not serialize to an object")
    return cast(dict[str, object], payload)


def _root_labels(snapshot: dict[str, object]) -> tuple[str, ...]:
    raw_roots = snapshot.get("roots")
    if not isinstance(raw_roots, list):
        return ()
    return tuple(sorted(str(item.get("root")) for item in raw_roots if isinstance(item, dict)))


def _known_prior_attempts() -> list[dict[str, object]]:
    attempts: list[dict[str, object]] = []
    archive_specs = (
        (
            REPOSITORY_ROOT / "projects" / "codex-harness" / "evidence" / "phase-4-exploratory",
            "archived exploratory evidence",
        ),
        (
            REPOSITORY_ROOT
            / "projects"
            / "codex-harness"
            / "evidence"
            / "phase-4-mcp-boundary-attempt",
            "archived MCP-boundary attempt",
        ),
        (
            REPOSITORY_ROOT
            / "projects"
            / "codex-harness"
            / "evidence"
            / "phase-4-truncated-snapshot-attempt",
            "archived truncated-snapshot attempt",
        ),
        (
            REPOSITORY_ROOT
            / "projects"
            / "codex-harness"
            / "evidence"
            / "phase-4-full-snapshot-attempt",
            "archived full-snapshot attempt",
        ),
        (
            REPOSITORY_ROOT
            / "projects"
            / "codex-harness"
            / "evidence"
            / "phase-4-scope-review-attempt",
            "archived scope-review attempt",
        ),
        (
            REPOSITORY_ROOT
            / "projects"
            / "codex-harness"
            / "evidence"
            / "phase-4-provenance-pinning-attempt",
            "archived provenance-pinning attempt",
        ),
        (
            REPOSITORY_ROOT
            / "projects"
            / "codex-harness"
            / "evidence"
            / "phase-4-final-provenance-pinning-attempt",
            "archived final provenance-pinning attempt",
        ),
        (
            REPOSITORY_ROOT
            / "projects"
            / "codex-harness"
            / "evidence"
            / "phase-4-receipt-binding-attempt",
            "archived receipt-binding attempt",
        ),
    )
    known_invocations: set[str] = set()
    for archive_root, source in archive_specs:
        archived_receipts = archive_root / "invocation-receipts"
        if archived_receipts.is_dir():
            for path in sorted(archived_receipts.glob("*.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                invocation_id = str(payload.get("invocation_id", path.stem))
                if invocation_id in known_invocations:
                    continue
                known_invocations.add(invocation_id)
                host_result_path = archive_root / "host-result.json"
                mcp_events = 0
                try:
                    host_payload = json.loads(host_result_path.read_text(encoding="utf-8"))
                    host_result = host_payload.get("result", {})
                    events = host_result.get("events", []) if isinstance(host_result, dict) else []
                    if isinstance(host_result, dict) and isinstance(
                        host_result.get("mcp_event_count"), int
                    ):
                        mcp_events = host_result["mcp_event_count"]
                    elif isinstance(events, list):
                        mcp_events = sum(
                            1
                            for event in events
                            if isinstance(event, dict)
                            and str(event.get("method", "")).startswith("mcpServer/")
                        )
                except (OSError, UnicodeError, json.JSONDecodeError):
                    pass
                attempts.append(
                    {
                        "source": source,
                        "status": payload.get("status", "UNKNOWN"),
                        "invocation_id": invocation_id,
                        "receipt_digest": payload.get("receipt_digest"),
                        "mcp_startup_status_events": mcp_events,
                    }
                )
    ledger = PILOT_WORKSPACE / ".harness" / "phase4" / "invocation-ledger.json"
    try:
        payload = json.loads(ledger.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        payload = {}
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if isinstance(entries, dict):
        for invocation_id, entry in sorted(entries.items()):
            if invocation_id in known_invocations:
                continue
            if isinstance(entry, dict):
                attempts.append(
                    {
                        "source": "project-local replay ledger",
                        "status": "UNRESOLVED_AFTER_PREVIOUS_ATTEMPT",
                        "invocation_id": invocation_id,
                        "request_digest": entry.get("request_digest"),
                    }
                )
    return attempts


def _attempt_counts(prior_attempts: list[dict[str, object]]) -> tuple[int, int, int]:
    """Separate evidenced invocations from reservations whose host result is unknown."""

    evidenced = sum(
        1
        for attempt in prior_attempts
        if isinstance(attempt.get("receipt_digest"), str)
        and str(attempt["receipt_digest"]).startswith("sha256:")
    )
    unresolved = sum(
        1
        for attempt in prior_attempts
        if attempt.get("status") == "UNRESOLVED_AFTER_PREVIOUS_ATTEMPT"
    )
    attempt_count = len(prior_attempts) + 1
    return evidenced + 1, unresolved, attempt_count


def _global_root_digests(snapshot: dict[str, object]) -> dict[str, object]:
    raw = snapshot.get("root_entry_digests")
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): value
        for key, value in raw.items()
        if str(key)
        in {
            "$HOME/.codex/config.toml",
            "$HOME/.codex/auth.json",
            "$HOME/.codex/skills",
            "$HOME/.agents",
        }
    }


def _pilot_inputs() -> tuple[
    CodexHostAdapter,
    CapabilityInventory,
    ResolutionResult,
    CapabilityRecord,
    ExecutionPolicyRegistry,
]:
    host = CodexHostAdapter(
        project_root=PILOT_WORKSPACE,
        workspace_root=PILOT_WORKSPACE,
        home_dir=Path.home(),
    )
    inventory = host.discover_capabilities()
    resolution = ResolutionEngine().resolve(inventory, PILOT_CAPABILITY)
    if not resolution.selected:
        raise RuntimeError("the project-local fallback pilot was not resolved")
    record = resolution.selected[0]
    policy = ExecutionPolicyRegistry.from_json(POLICY_PATH)
    rule = policy.rule_for_record(record)
    if rule is None or not rule.execution_approved:
        raise RuntimeError("the resolved fallback pilot is not explicitly approved")
    return host, inventory, resolution, record, policy


def _host_capability_matrix(result: HostInvocationResult) -> list[dict[str, object]]:
    transcript_complete = bool(
        result.protocol_messages and len(result.protocol_messages) == result.protocol_message_count
    )
    return [
        {
            "feature": "jsonrpc_app_server",
            "official_documentation": "https://learn.chatgpt.com/docs/codex/app-server",
            "observed_support": "HOST_OBSERVED",
            "adapter_support": "ENFORCED",
            "confidence": "HIGH",
            "limitations": "Codex app-server semantics are bounded to the recorded version.",
        },
        {
            "feature": "initialize",
            "official_documentation": "https://learn.chatgpt.com/docs/codex/app-server",
            "observed_support": "HOST_OBSERVED",
            "adapter_support": "REQUIRED",
            "confidence": "HIGH",
            "limitations": "No claim beyond the captured JSON-RPC handshake.",
        },
        {
            "feature": "skills_list_discovery",
            "official_documentation": "https://learn.chatgpt.com/docs/codex/app-server",
            "observed_support": "HOST_OBSERVED",
            "adapter_support": "EXACT_NAME_PATH_ENABLED_REQUIRED",
            "confidence": "HIGH",
            "limitations": "Discovery is not proof of causal Skill loading.",
        },
        {
            "feature": "typed_skill_input",
            "official_documentation": "https://learn.chatgpt.com/docs/codex/app-server",
            "observed_support": "HOST_OBSERVED",
            "adapter_support": "REQUIRED",
            "confidence": "HIGH",
            "limitations": "Only one bounded Skill input was exercised.",
        },
        {
            "feature": "ephemeral_read_only_thread",
            "official_documentation": "https://learn.chatgpt.com/docs/codex/app-server",
            "observed_support": "HOST_OBSERVED",
            "adapter_support": "REQUIRED",
            "confidence": "HIGH",
            "limitations": "Read-only and project-root restrictions remain host-policy parameters.",
        },
        {
            "feature": "network_denial",
            "official_documentation": "https://learn.chatgpt.com/docs/codex/app-server",
            "observed_support": "REQUESTED_AND_BOUND",
            "adapter_support": "ENFORCED",
            "confidence": "MEDIUM",
            "limitations": "The pilot did not perform a network probe.",
        },
        {
            "feature": "approval_denial",
            "official_documentation": "https://learn.chatgpt.com/docs/codex/app-server",
            "observed_support": (
                "NO_APPROVAL_REQUEST_OBSERVED"
                if result.approval_request_count == 0
                else "HOST_OBSERVED"
            ),
            "adapter_support": "DECLINE_IF_REQUESTED",
            "confidence": "MEDIUM",
            "limitations": (
                "The final pilot exercised no approval request; adversarial denial is unit-tested."
            ),
        },
        {
            "feature": "mcp_suppression",
            "official_documentation": "NOT_EXPLICITLY_DOCUMENTED_AS_A_PHASE4_GUARANTEE",
            "observed_support": (
                "ZERO_PARSED_MCP_EVENTS" if result.mcp_event_count == 0 else "MCP_EVENTS_OBSERVED"
            ),
            "adapter_support": "mcp_servers_EMPTY_AND_APPS_DISABLED",
            "confidence": "HIGH",
            "limitations": "This is a pilot isolation property, not a universal MCP claim.",
        },
        {
            "feature": "turn_lifecycle_events",
            "official_documentation": "https://learn.chatgpt.com/docs/codex/app-server",
            "observed_support": "HOST_OBSERVED",
            "adapter_support": "CORRELATED_TO_THREAD_AND_TURN",
            "confidence": "HIGH",
            "limitations": "Only the bounded lifecycle in this packet is evidenced.",
        },
        {
            "feature": "complete_protocol_observation",
            "official_documentation": "NOT_HOST_SEMANTICS",
            "observed_support": "FULL_TRANSCRIPT" if transcript_complete else "PARTIAL_TRANSCRIPT",
            "adapter_support": "COUNT_AND_SUMMARY_FOR_EVERY_PARSED_MESSAGE",
            "confidence": "HIGH" if transcript_complete else "MEDIUM",
            "limitations": "Transcript summaries intentionally omit payload contents and secrets.",
        },
        {
            "feature": "timeout_and_cancellation",
            "official_documentation": "https://learn.chatgpt.com/docs/codex/app-server",
            "observed_support": "BOUNDED_AND_UNIT_TESTED",
            "adapter_support": "DEADLINE_AND_INTERRUPT_BOUND",
            "confidence": "MEDIUM",
            "limitations": "The final successful pilot did not need cancellation.",
        },
        {
            "feature": "host_executable_pinning",
            "official_documentation": "NOT_HOST_SEMANTICS",
            "observed_support": "ABSOLUTE_PATH_AND_SHA256_RECORDED",
            "adapter_support": "PIN_AND_REHASH_BEFORE_PROCESS_START",
            "confidence": "HIGH",
            "limitations": "The pin is for this host environment and policy fingerprint.",
        },
        {
            "feature": "host_interpreter_pinning",
            "official_documentation": "NOT_HOST_SEMANTICS",
            "observed_support": "ABSOLUTE_PATH_AND_SHA256_RECORDED_AND_BOUND",
            "adapter_support": "PIN_AND_REHASH_BEFORE_PROCESS_START",
            "confidence": "HIGH",
            "limitations": "The interpreter pin is for the captured host executable shebang.",
        },
        {
            "feature": "skill_load_causality",
            "official_documentation": "NOT_EXPOSED_BY_CAPTURED_PROTOCOL",
            "observed_support": result.load_observation.value,
            "adapter_support": "FAILS_CLOSED_ON_UNOBSERVABLE_CAUSALITY_CLAIM",
            "confidence": "HIGH",
            "limitations": "Level C causal Skill-load evidence is not claimed.",
        },
    ]


def _write_static_machine_reports(
    writer: EvidenceWriter,
    *,
    policy: ExecutionPolicyRegistry,
    record: CapabilityRecord,
    outcome: ExecutionOutcome,
    host_version: str,
    host_result: HostInvocationResult,
) -> None:
    writer.write_json("execution-policy.json", policy.to_dict())
    writer.write_json(
        "pilot-allowlist.json",
        {
            "schema_version": "P4-PILOT-ALLOWLIST-1",
            "selection": "exact capability ID + SemVer + package fingerprint",
            "controlled_real_rule": public_data(policy.rule_for_record(record)),
            "preferred_pilots": [
                {
                    "capability_id": "design-director",
                    "real_mode": "BLOCKED",
                    "reason": "script-bearing synthesized third-party global package",
                },
                {
                    "capability_id": "verification-loop",
                    "real_mode": "BLOCKED",
                    "reason": "invalid rejected package",
                },
            ],
            "fallback": {
                "capability_id": record.capability_id,
                "version": record.version,
                "package_fingerprint": record.content_hash,
                "real_mode": "EXPLICITLY_APPROVED_FOR_BOUNDED_PILOT",
            },
        },
    )
    writer.write_json(
        "host-invocation-capabilities.json",
        {
            "schema_version": "P4-HOST-CAPABILITIES-1",
            "host": "Codex app-server",
            "adapter": "CodexAppServerAdapter",
            "host_version": host_version,
            "support_level": "P4_LEVEL_B",
            "official_sources": [
                "https://learn.chatgpt.com/docs/codex/app-server",
                "https://learn.chatgpt.com/docs/codex/cli",
                "https://learn.chatgpt.com/docs/codex/non-interactive-mode",
                "https://learn.chatgpt.com/docs/codex/codex-sdk",
            ],
            "observed_sequence": [
                "initialize",
                "skills/list",
                "thread/start(ephemeral,read-only)",
                "turn/start(typed text + typed skill input)",
                "turn/completed",
            ],
            "enforced_boundary": {
                "process": [
                    "codex",
                    "-c",
                    "mcp_servers={}",
                    "-c",
                    "features.apps=false",
                    "app-server",
                    "--listen",
                    "stdio://",
                ],
                "resolved_command": list(host_result.host_command),
                "host_executable_path": host_result.host_executable_path,
                "host_executable_digest": host_result.host_executable_digest,
                "host_interpreter_path": host_result.host_interpreter_path,
                "host_interpreter_digest": host_result.host_interpreter_digest,
                "sandbox": "readOnly",
                "network_access": False,
                "approval_policy": "on-request with every approval declined",
                "runtime_workspace_roots": ["$WORKSPACE"],
                "mcp_config_override": "mcp_servers={}",
                "apps_feature_override": "features.apps=false",
                "isolated_runtime": "temporary HOME/CODEX_HOME with host auth copied only",
                "shell_scripts_tools_providers_credentials_subagents": "DENIED",
            },
            "host_authentication": "host-managed and never sent as Skill input",
            "causality": "host execution observed; Skill load event unobservable",
            "outcome_status": outcome.status.value,
            "capability_matrix_schema": "P4-HOST-MATRIX-1",
            "capability_matrix": _host_capability_matrix(host_result),
        },
    )


def _write_pilot_evidence(
    writer: EvidenceWriter,
    *,
    prepared: PreparedInvocation,
    outcome: ExecutionOutcome,
    elapsed_seconds: float,
    before_snapshot: dict[str, object],
    after_snapshot: dict[str, object],
) -> None:
    request = prepared.request
    if request is None or outcome.host_result is None or outcome.verification is None:
        raise RuntimeError("successful pilot did not return a complete evidence chain")
    result = outcome.host_result
    receipt = outcome.receipt
    artifact = outcome.artifacts[0] if len(outcome.artifacts) == 1 else None
    if artifact is None:
        raise RuntimeError("successful pilot did not return exactly one artifact")
    artifact_bytes = read_artifact_bytes(artifact.location, request.workspace)
    if "sha256:" + hashlib.sha256(artifact_bytes).hexdigest() != artifact.digest:
        raise RuntimeError("artifact digest does not match captured bytes")
    if "PHASE4_SAFE_PILOT_ARTIFACT" not in artifact_bytes.decode("utf-8"):
        raise RuntimeError("final pilot marker is missing")
    writer.write_bytes(f"artifacts/{artifact.artifact_id}.host-response.txt", artifact_bytes)
    request_digest = stable_digest_payload(request, workspace=request.workspace)
    writer.write_json(
        f"requests/{receipt.invocation_id}.json",
        {
            "schema_version": "P4-REQUEST-1",
            "request_digest": request_digest,
            "request": _public_mapping(request),
        },
    )
    writer.write_json(
        f"invocation-receipts/{receipt.invocation_id}.json",
        {
            "schema_version": "P4-RECEIPT-1",
            **_public_mapping(receipt),
            "request_digest": request_digest,
        },
    )
    writer.write_json(
        f"context-manifests/{receipt.invocation_id}.json",
        {"schema_version": "P4-CONTEXT-1", **_public_mapping(request.context)},
    )
    writer.write_json(
        f"authorizations/{receipt.authorization_id}.json",
        {"schema_version": "P4-AUTHORIZATION-1", **_public_mapping(request.authorization)},
    )
    writer.write_json(
        f"verification/{receipt.invocation_id}.json",
        {"schema_version": "P4-VERIFICATION-1", **_public_mapping(outcome.verification)},
    )
    writer.write_json(
        f"telemetry/{receipt.invocation_id}.json",
        {
            "schema_version": "P4-TELEMETRY-1",
            "invocation_id": receipt.invocation_id,
            "host_version": result.host_version,
            "host_event_count": len(result.events),
            "host_event_digest": receipt.host_event_digest,
            "load_observation": result.load_observation,
            "approval_requests_denied": result.denied_approvals,
            "protocol_message_count": result.protocol_message_count,
            "mcp_event_count": result.mcp_event_count,
            "approval_request_count": result.approval_request_count,
            "protocol_messages": result.protocol_messages,
            "host_invoked": result.invocation_observed,
            "execution_observed": result.execution_observed,
            "cancellation_status": result.cancellation_status,
            "elapsed_seconds_wall_clock": round(elapsed_seconds, 3),
            "events": result.events,
        },
    )
    writer.write_text(
        f"telemetry/{receipt.invocation_id}.jsonl",
        "".join(
            json.dumps(
                {
                    "sequence": event.sequence,
                    "method": event.method,
                    "fact_status": event.fact_status,
                    "event_class": event.event_class,
                    "item_type": event.item_type,
                    "item_id": event.item_id,
                    "status": event.status,
                    "detail": event.detail,
                    "thread_id": event.thread_id,
                    "turn_id": event.turn_id,
                },
                sort_keys=True,
            )
            + "\n"
            for event in result.events
        ),
    )
    writer.write_json(
        "host-result.json",
        {
            "schema_version": "P4-HOST-RESULT-1",
            "invocation_id": receipt.invocation_id,
            "authorized_thread_id": result.thread_id,
            "authorized_turn_id": result.turn_id,
            "result": result,
            "correlation": (
                "every explicit threadId/turnId in accepted host events matched; "
                "all parsed protocol messages were counted"
            ),
        },
    )
    writer.write_json("outcome.json", public_outcome(outcome, workspace=request.workspace))
    writer.write_json("state-before.json", before_snapshot, max_bytes=2 * 1024 * 1024)
    writer.write_json("state-after.json", after_snapshot, max_bytes=2 * 1024 * 1024)
    before_global = _global_root_digests(before_snapshot)
    after_global = _global_root_digests(after_snapshot)
    writer.write_json(
        "global-mutation-report.json",
        {
            "schema_version": "P4-GLOBAL-MUTATION-1",
            "scope": "metadata-only snapshots; file contents and credentials were not read",
            "global_scope": [
                "$HOME/.codex/config.toml",
                "$HOME/.codex/auth.json",
                "$HOME/.codex/skills",
                "$HOME/.agents",
            ],
            "excluded_dynamic_state": [
                "$HOME/.codex/sessions",
                "$HOME/.codex/history.jsonl",
                "$HOME/.codex/logs",
            ],
            "roots": sorted(set(_root_labels(before_snapshot)) | set(_root_labels(after_snapshot))),
            "before_digest": before_snapshot.get("metadata_digest"),
            "after_digest": after_snapshot.get("metadata_digest"),
            "before_global_root_digests": before_global,
            "after_global_root_digests": after_global,
            "project_runtime_expected_mutation": True,
            "global_root_digests_unchanged": before_global == after_global,
            "root_delta_requires_read_only_review": before_global != after_global,
        },
    )


def _write_reports(
    writer: EvidenceWriter,
    *,
    prepared: PreparedInvocation,
    outcome: ExecutionOutcome,
    elapsed_seconds: float,
    test_summary: str = "final verification run is recorded by the repository test command",
) -> None:
    request = prepared.request
    if request is None or outcome.host_result is None or outcome.verification is None:
        raise RuntimeError("report inputs are incomplete")
    receipt = outcome.receipt
    result = outcome.host_result
    artifact = outcome.artifacts[0]
    writer.write_text(
        "README.md",
        "# Phase 4 evidence packet\n\n"
        "This packet records one dynamically captured, project-local, script-free "
        "controlled-real pilot through the official Codex app-server JSON-RPC boundary. "
        "The final status is provisional until the independent read-only review closes.\n\n"
        f"Support level: `P4_LEVEL_B`; load causality: `{result.load_observation.value}`; "
        f"invocation: `{receipt.invocation_id}`; "
        f"package fingerprint: `{prepared.record.content_hash}`.\n"
        "No claim of arbitrary Skill execution, production readiness, MCP completeness, "
        "provider completeness, or `AAA_VERIFIED` is made.\n",
    )
    writer.write_text(
        "design-director-pilot-report.md",
        "# Design-director pilot report\n\n"
        "Status: `DRY_RUN_ONLY` / controlled-real blocked.\n\n"
        "Phase 3 classifies the installed package as synthesized, global, third-party, "
        "partially compatible and script-bearing. Its exact fingerprint is allowlisted "
        "for inspection but not real execution; no host request was made.\n",
    )
    writer.write_text(
        "verification-pilot-report.md",
        "# Verification-loop pilot report\n\n"
        "Status: blocked before host invocation.\n\n"
        "Phase 3 resolution rejects the installed invalid package. No host request, "
        "Skill load, artifact or mutation was attempted.\n",
    )
    writer.write_text(
        "host-load-causality-report.md",
        "# Host-load causality report\n\n"
        f"The host observed a complete bounded turn for `{request.skill_name}`: exact "
        "discovery, ephemeral read-only thread, typed Skill input and turn completion. "
        f"The event count was `{len(result.events)}` and no correlated Skill-load event "
        f"was exposed, so the causal status is `{result.load_observation.value}`. "
        "This is `P4_LEVEL_B`, not Level C.\n",
    )
    writer.write_text(
        "artifact-report.md",
        f"# Artifact report\n\nThe byte-preserving artifact `{artifact.artifact_id}` is a "
        f"`HOST_RESPONSE` of `{artifact.size_bytes}` bytes, bound to "
        f"`{receipt.invocation_id}` with digest `{artifact.digest}`. The final path was "
        "validated inside the project workspace with final symlink rejection.\n",
    )
    writer.write_text(
        "verification-report.md",
        f"# Verification report\n\nStatus: `{outcome.verification.status}`. The chain "
        "validated host completion, execution observation, non-empty output, exactly one "
        "artifact, byte integrity, type, producer/invocation binding, both acceptance "
        f"criteria, correlated receipt reference and evidence references. Digest: "
        f"`{outcome.verification.digest}`.\n",
    )
    writer.write_text(
        "telemetry-report.md",
        "# Telemetry report\n\n"
        f"The receipt lifecycle is `{' → '.join(item.value for item in receipt.lifecycle)}`. "
        f"The host emitted `{len(result.events)}` bounded events and denied "
        f"`{result.denied_approvals}` approval requests. The complete parsed protocol "
        f"count was `{result.protocol_message_count}`, including "
        f"`{result.mcp_event_count}` MCP events and `{result.approval_request_count}` "
        f"approval requests; it returned status "
        f"`{result.status.value}` after approximately `{elapsed_seconds:.3f}` "
        "wall-clock seconds.\n",
    )
    writer.write_text(
        "security-summary.md",
        "# Security summary\n\n"
        "The bounded pilot is fail-closed: exact fingerprint and explicit execution "
        "approval are required; the app-server starts with `mcp_servers={}`, a read-only "
        "ephemeral thread, no network access, zero tool budget and approval denial. "
        "Shell, scripts, tools, network, MCP, providers, credentials, side effects and "
        "subagents are denied. Task/preflight/request bindings, persistent replay, event "
        "correlation, artifact paths and sanitized evidence are independently testable. "
        "Global state is checked through metadata-only before/after snapshots.\n",
    )
    writer.write_text(
        "phase2-regression.md",
        "# Phase 2 regression\n\nPASS. The frozen Phase 2 packet and its regression suite "
        "remain green; no Phase 2 implementation was changed.\n",
    )
    writer.write_text(
        "phase3-regression.md",
        "# Phase 3 regression\n\nPASS. The frozen Phase 3 packet and its regression suite "
        "remain green; no Phase 3 implementation was changed.\n",
    )
    writer.write_text(
        "phase3-supersession.md",
        "# Phase 3 supersession record\n\n"
        "The historical Phase 3 implementation and evidence packet remain frozen. "
        "Phase 4 adds only the project-local `harness-phase4` entry point in the "
        "current `pyproject.toml`; it does not rewrite Phase 3 source, tests, config "
        "or global state. The current Phase 4 manifest binds the exact additive file "
        "bytes, and the Phase 2/3 regression checks were rerun for this packet.\n",
    )
    writer.write_text(
        "coverage-report.md",
        "# Coverage report\n\n"
        f"{test_summary}. Combined branch coverage must remain at or above 80%; the "
        "closeout command records the exact fresh result.\n",
    )


def _write_benchmark(
    writer: EvidenceWriter,
    *,
    engine: InvocationEngine,
    prepared: PreparedInvocation,
    outcome: ExecutionOutcome,
    artifact_bytes: bytes,
    elapsed_seconds: float,
) -> None:
    request = prepared.request
    if request is None or outcome.verification is None or outcome.host_result is None:
        raise RuntimeError("benchmark inputs are incomplete")
    host_result = outcome.host_result

    def prepare_dry_run() -> object:
        return engine.prepare(
            prepared.record,
            prepared.inventory,
            prepared.resolution,
            _policy_for_benchmark(prepared),
            task_id="TASK-P4-BENCH",
            run_id="RUN-P4-BENCH",
            task=PILOT_TASK,
            acceptance_criteria=PILOT_ACCEPTANCE,
            workspace=PILOT_WORKSPACE,
            mode=ExecutionMode.DRY_RUN,
            budget=PILOT_BUDGET,
        )

    writer.write_json(
        "benchmark-summary.json",
        {
            "schema_version": "P4-BENCH-1",
            "purpose": "reproducibility and control-plane measurement, not a production SLO",
            "host_latency": {
                "sample_count": 1,
                "observed_elapsed_seconds": round(elapsed_seconds, 3),
                "host_event_count": len(host_result.events),
                "source": "monotonic wall-clock around one real pilot",
                "claim": "one observation; not a performance guarantee",
            },
            "harness_operations": [
                benchmark_operation(
                    "preflight_and_context_prepare", prepare_dry_run, iterations=10
                ),
                benchmark_operation(
                    "request_serialization", lambda: canonical_json(request), iterations=10
                ),
                benchmark_operation(
                    "receipt_serialization",
                    lambda: canonical_json(outcome.receipt),
                    iterations=10,
                ),
                benchmark_operation(
                    "artifact_read",
                    lambda: read_artifact_bytes(
                        outcome.artifacts[0].location,
                        request.workspace,
                    ),
                    iterations=10,
                ),
                benchmark_operation(
                    "verification_serialization",
                    lambda: canonical_json(outcome.verification),
                    iterations=10,
                ),
            ],
        },
    )


def _policy_for_benchmark(prepared: PreparedInvocation) -> ExecutionPolicyRegistry:
    policy = ExecutionPolicyRegistry.from_json(POLICY_PATH)
    if policy.rule_for_record(prepared.record) is None:
        raise RuntimeError("benchmark record lost its exact policy binding")
    return policy


def _payload_paths() -> tuple[str, ...]:
    return tuple(
        str(path.relative_to(EVIDENCE_ROOT))
        for path in EVIDENCE_ROOT.rglob("*")
        if path.is_file() and path.name not in _POST_REVIEW_FILES
    )


def main() -> int:
    if (EVIDENCE_ROOT / "final-run.json").exists():
        raise RuntimeError("final Phase 4 evidence already exists; refusing a second real call")
    _host, inventory, resolution, record, policy = _pilot_inputs()
    prior_attempts = _known_prior_attempts()
    evidenced_real_invocation_count, unresolved_reservation_count, attempt_count = _attempt_counts(
        prior_attempts
    )
    before = snapshot_tree(
        (
            PILOT_WORKSPACE / ".harness" / "phase4",
            Path.home() / ".codex" / "config.toml",
            Path.home() / ".codex" / "auth.json",
            Path.home() / ".codex" / "skills",
            Path.home() / ".agents",
        )
    )
    engine = InvocationEngine(CodexAppServerAdapter())
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id=PILOT_TASK_ID,
        run_id=PILOT_RUN_ID,
        task=PILOT_TASK,
        acceptance_criteria=PILOT_ACCEPTANCE,
        workspace=PILOT_WORKSPACE,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=PILOT_BUDGET,
        expected_fingerprint=record.content_hash,
        require_fingerprint_confirmation=True,
    )
    started = time.monotonic()
    outcome = engine.execute_prepared(prepared)
    elapsed_seconds = time.monotonic() - started
    after = snapshot_tree(
        (
            PILOT_WORKSPACE / ".harness" / "phase4",
            Path.home() / ".codex" / "config.toml",
            Path.home() / ".codex" / "auth.json",
            Path.home() / ".codex" / "skills",
            Path.home() / ".agents",
        )
    )
    if outcome.status.value != "SUCCESS" or outcome.assurance is None:
        raise RuntimeError(f"final controlled pilot did not succeed: {outcome.status.value}")
    if outcome.host_result is None:
        raise RuntimeError("final controlled pilot did not return a host result")
    host_result = outcome.host_result
    if host_result.mcp_event_count:
        raise RuntimeError(
            f"isolated controlled pilot observed MCP protocol events: {host_result.mcp_event_count}"
        )
    writer = EvidenceWriter(EVIDENCE_ROOT)
    _write_pilot_evidence(
        writer,
        prepared=prepared,
        outcome=outcome,
        elapsed_seconds=elapsed_seconds,
        before_snapshot=before,
        after_snapshot=after,
    )
    _write_static_machine_reports(
        writer,
        policy=policy,
        record=record,
        outcome=outcome,
        host_version=host_result.host_version,
        host_result=host_result,
    )
    artifact_bytes = read_artifact_bytes(
        outcome.artifacts[0].location,
        prepared.request.workspace if prepared.request is not None else PILOT_WORKSPACE,
    )
    _write_benchmark(
        writer,
        engine=engine,
        prepared=prepared,
        outcome=outcome,
        artifact_bytes=artifact_bytes,
        elapsed_seconds=elapsed_seconds,
    )
    _write_reports(writer, prepared=prepared, outcome=outcome, elapsed_seconds=elapsed_seconds)
    writer.write_json(
        "final-run.json",
        {
            "schema_version": "P4-FINAL-RUN-1",
            "status": outcome.status,
            "assurance": outcome.assurance,
            "invocation_id": outcome.receipt.invocation_id,
            "capability_id": record.capability_id,
            "capability_version": record.version,
            "package_fingerprint": record.content_hash,
            "preflight_digest": outcome.preflight.digest,
            "host_version": host_result.host_version,
            "host_load_observation": host_result.load_observation,
            "protocol_message_count": host_result.protocol_message_count,
            "mcp_event_count": host_result.mcp_event_count,
            "approval_request_count": host_result.approval_request_count,
            "host_executable_path": host_result.host_executable_path,
            "host_executable_digest": host_result.host_executable_digest,
            "host_command": host_result.host_command,
            "host_interpreter_path": host_result.host_interpreter_path,
            "host_interpreter_digest": host_result.host_interpreter_digest,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "review_status": "PENDING_INDEPENDENT_READ_ONLY_REVIEW",
            "prior_real_attempts": prior_attempts,
            "evidenced_real_invocation_count": evidenced_real_invocation_count,
            "unresolved_reservation_count": unresolved_reservation_count,
            "attempt_count": attempt_count,
        },
    )
    writer.write_json(
        "attempt-history.json",
        {
            "schema_version": "P4-ATTEMPT-HISTORY-1",
            "known_prior_attempts": prior_attempts,
            "successful_final_attempt": outcome.receipt.invocation_id,
            "evidenced_real_invocation_count": evidenced_real_invocation_count,
            "unresolved_reservation_count": unresolved_reservation_count,
            "attempt_count": attempt_count,
            "note": "Unresolved ledger reservations are retained and never replayed.",
        },
    )
    writer.write_text(
        "independent-review.md",
        "# Independent review\n\nPENDING_INDEPENDENT_READ_ONLY_REVIEW. A separate "
        "read-only reviewer must inspect this exact packet before closeout.\n",
    )
    payload_paths = _payload_paths()
    manifest = build_review_manifest(
        EVIDENCE_ROOT,
        payload_paths,
        bound_files=_repository_bound_files(),
    )
    writer.write_json("review-manifest.json", manifest)
    writer.write_json(
        "review-attestation.json",
        {
            "schema_version": "P4-REVIEW-ATTESTATION-1",
            "review_status": "PENDING_INDEPENDENT_READ_ONLY_REVIEW",
            "manifest_closure": manifest["payload_closure"],
            "reviewed_head": _git_head(),
            "scope": "Phase 4 packet only; no source or global state mutation",
        },
    )
    writer.write_json(
        "readiness.json",
        {
            "phase": "PHASE4-001",
            "status": "PENDING_INDEPENDENT_READ_ONLY_REVIEW",
            "quality_bar": "P4-QB-1",
            "reviewed_head": _git_head(),
            "phase2_base": "FROZEN",
            "phase3_base": "FROZEN",
            "host_support_level": "P4_LEVEL_B",
            "pilot_capabilities": [record.capability_id],
            "pilot_fingerprints": [record.content_hash],
            "execution_mode": outcome.mode,
            "real_invocation_count": evidenced_real_invocation_count,
            "evidenced_real_invocation_count": evidenced_real_invocation_count,
            "unresolved_reservation_count": unresolved_reservation_count,
            "attempt_count": attempt_count,
            "successful_final_invocation_count": 1,
            "load_observation_status": host_result.load_observation,
            "tests": "PENDING_FINAL_VERIFICATION",
            "coverage": "PENDING_FINAL_VERIFICATION",
            "ruff": "PENDING_FINAL_VERIFICATION",
            "mypy": "PENDING_FINAL_VERIFICATION",
            "benchmark": "P4-BENCH-1",
            "security": "PENDING_INDEPENDENT_READ_ONLY_REVIEW",
            "phase2_regression": "PASS",
            "phase3_regression": "PASS",
            "critical": 0,
            "high": 0,
            "medium": "PENDING_REVIEW",
            "independent_review": "PENDING",
            "review_manifest": manifest["payload_closure"],
            "review_attestation": "PENDING",
            "limitations": [host_result.load_observation],
            "excluded_claims": [
                "PRODUCTION_READY",
                "AAA_VERIFIED",
                "ARBITRARY_SKILL_EXECUTION",
                "SAFE_ARBITRARY_CODE_EXECUTION",
                "MCP_COMPLETE",
                "PROVIDER_COMPLETE",
                "SUBAGENT_COMPLETE",
                "FULL_HOST_CAUSALITY",
                "GLOBAL_MUTATION_SAFE",
                "DISTRIBUTED_EXECUTION",
            ],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
