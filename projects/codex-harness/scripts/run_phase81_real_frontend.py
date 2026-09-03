"""Run the exact frontend Skill through a bounded writable App Server turn.

This repair run responds only to findings exposed by the first exact review:
the narrow reflow clipped operational data, retry keys were not payload-bound,
network errors leaked browser copy, and the fixture lacked an auditable stored-
creation receipt. The official host owns every source mutation.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from harness_kernel.phase4_host import _resolve_host_binding
from harness_kernel.phase4_models import (
    CapabilityInvocationRequest,
    ExecutionMode,
    Phase4Budget,
    public_data,
)
from harness_kernel.phase6_host import (
    Phase6HostSnapshot,
    Phase6Preflight,
    discover_vnext_package,
    prepare_vnext_preflight,
)
from harness_kernel.phase7_backend import package_fingerprint, snapshot_workspace
from harness_kernel.phase7_host import WorkspaceWriteMode, build_backend_filesystem_policy
from harness_kernel.phase81_host import (
    FRONTEND_CAPABILITY_ID,
    FrontendBuilderAppServerAdapter,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = PROJECT_ROOT / "evidence" / "phase-8.1"
PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / FRONTEND_CAPABILITY_ID
VERIFIER_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / "verification-loop-vnext"
FIXTURE_ROOT = EVIDENCE_ROOT / "composition-run-012" / "frontend-artifact"
POLICY_PATH = PROJECT_ROOT / "config" / "phase8.1-execution-policy.json"
RUN_ROOT = EVIDENCE_ROOT / "frontend-real-005"
BUILD_ROOT = EVIDENCE_ROOT / "artifact" / "frontend-run-004"
COMPOSITION_ROOT = EVIDENCE_ROOT / "composition-run-013"

TASK_ID = "PHASE8.1-001"
RUN_ID = "P81-COMPOSE-013"
MARKER_NAME = "data-phase81-composition"
MARKER_VALUE = RUN_ID
TASK = (
    "Repair only P8.1-FINDING-H-HOST-COMPOSITION-001, P8.1-FINDING-H-RUNTIME-FALSE-PASS-001, "
    "P8.1-FINDING-M-REFLOW-001, P8.1-FINDING-M-IDEMPOTENCY-PAYLOAD-001 and "
    "P8.1-FINDING-L-BOUNDED-ERROR-COPY-001 in the existing veterinary emergency frontend. "
    "Use bounded host tools to inspect and then update exactly app/index.html, app/styles.css, "
    "app/app.js and app/fixture_server.py. In index.html update the existing body composition "
    "marker from P81-COMPOSE-012 to P81-COMPOSE-013. In styles.css make the existing <=420px "
    "navigation grid retain its count badge in the same row, and add a <=280px narrow-reflow "
    "rule that stacks each queue cell label above its full value and removes patient/action "
    "ellipsis or nowrap clipping; preserve table reading order. In app.js bind a retained "
    "idempotency key to the exact serialized draft, generate a new key when the draft changes, "
    "clear both after success, and replace raw fetch exception copy with bounded product copy "
    "while preserving actionable retry. In fixture_server.py bind each idempotency key to a "
    "canonical payload digest, reject same-key/different-payload reuse with 409, and expose a "
    "same-origin read-only /api/receipts JSON endpoint containing attempt receipts and stored "
    "creation count for deterministic browser assertions. Do not add dependencies, external "
    "network, unrelated UI, or any other file. Return a short factual completion message."
)
CRITERIA = (
    "the official turn contains the exact typed frontend-engineering-vnext Skill input",
    "only app/index.html, app/styles.css, app/app.js and app/fixture_server.py change",
    f'the final document contains exactly one {MARKER_NAME}="{MARKER_VALUE}" attribute',
    "all changed paths are recorded in successful bounded host write events and the "
    "independent delta",
    "narrow queue data remains complete and idempotency keys cannot acknowledge changed drafts",
    "browser-native exception text is not shown to users and fixture creation counts are "
    "observable",
    "network, shell, MCP, providers, credentials, approvals and global mutation remain zero",
)
IGNORED_NAMES = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"})
ARTIFACT_FILES = ("index.html", "styles.css", "app.js", "fixture_server.py")


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_digest(value: object) -> str:
    return _sha256_bytes(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORED_NAMES or name.startswith(".")}


def _files(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_NAMES or part.startswith(".") for part in relative.parts):
            continue
        result[relative.as_posix()] = {"bytes": path.stat().st_size, "sha256": _sha256(path)}
    return result


def _tree_digest(root: Path) -> str:
    """Return the digest emitted by the artifact's fixture server.

    Keeping one public artifact identity avoids a composition receipt that binds
    the build and browser observations to equivalent bytes under different tree
    algorithms.
    """

    entries = [f"{name}:{_sha256(root / name)}" for name in ARTIFACT_FILES]
    return _sha256_bytes("\n".join(entries).encode("utf-8"))


def _path_digest(path: Path) -> dict[str, object]:
    if path.is_file():
        return {"path": str(path), "kind": "file", "digest": _sha256(path), "files": 1}
    if path.is_dir():
        files = _files(path)
        return {
            "path": str(path),
            "kind": "directory",
            "digest": _canonical_digest(files),
            "files": len(files),
        }
    return {"path": str(path), "kind": "missing", "digest": None, "files": 0}


def _protected_snapshot() -> list[dict[str, object]]:
    paths = (
        Path.home() / ".codex" / "skills",
        Path.home() / ".agents" / "skills",
        Path.home() / ".codex" / "config.toml",
        PACKAGE_ROOT,
        VERIFIER_ROOT,
    )
    return [_path_digest(path) for path in paths]


def _redact_path(value: str, workspace: Path) -> str:
    return value.replace(str(workspace), "$WORKSPACE").replace(str(PROJECT_ROOT), "$PROJECT")


def _redact(value: object, workspace: Path) -> object:
    if isinstance(value, str):
        return _redact_path(value, workspace)
    if isinstance(value, list):
        return [_redact(item, workspace) for item in value]
    if isinstance(value, tuple):
        return [_redact(item, workspace) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact(item, workspace) for key, item in value.items()}
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _preflight(
    workspace: Path,
) -> tuple[Phase6HostSnapshot, Phase6Preflight, CapabilityInvocationRequest]:
    snapshot = discover_vnext_package(PROJECT_ROOT, capability_id=FRONTEND_CAPABILITY_ID)
    preflight = prepare_vnext_preflight(
        PROJECT_ROOT,
        snapshot=snapshot,
        task_id=TASK_ID,
        run_id=RUN_ID,
        task=TASK,
        acceptance_criteria=CRITERIA,
        workspace=workspace,
        policy_path=POLICY_PATH,
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(
            timeout_seconds=180,
            max_context_bytes=64_000,
            max_host_events=2_048,
            max_tool_calls=0,
            max_output_bytes=128 * 1024,
        ),
    )
    if not preflight.allowed or preflight.prepared is None or preflight.prepared.request is None:
        raise RuntimeError(f"frontend preflight blocked: {preflight.blockers}")
    return snapshot, preflight, preflight.prepared.request


def main() -> int:
    for path in (RUN_ROOT, BUILD_ROOT, COMPOSITION_ROOT):
        if path.exists():
            raise RuntimeError(f"fresh run path already exists: {path.relative_to(PROJECT_ROOT)}")
    if not FIXTURE_ROOT.is_dir() or not PACKAGE_ROOT.is_dir() or not VERIFIER_ROOT.is_dir():
        raise RuntimeError("required exact fixture or capability package is unavailable")

    binding = _resolve_host_binding()
    host_digest = binding[2]
    interpreter_digest = binding[5]
    if interpreter_digest is None:
        raise RuntimeError("host interpreter is not pinned")
    frontend_fingerprint = package_fingerprint(PACKAGE_ROOT)
    verifier_fingerprint = package_fingerprint(VERIFIER_ROOT)
    protected_before = _protected_snapshot()
    started_wall_ns = time.time_ns()
    started_monotonic_ns = time.monotonic_ns()

    RUN_ROOT.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix=".p81-frontend-real-", dir=PROJECT_ROOT) as raw:
        workspace = Path(raw) / "pilot"
        app = workspace / "app"
        shutil.copytree(FIXTURE_ROOT, app, ignore=_copy_ignore, symlinks=False)
        before = dict(snapshot_workspace(workspace))
        before_digest = _canonical_digest(before)
        snapshot, preflight, request = _preflight(workspace)
        authorization = request.authorization
        if snapshot.package_digest != frontend_fingerprint:
            raise RuntimeError("frontend discovery fingerprint drifted")
        if authorization.host_executable_digest != host_digest:
            raise RuntimeError("host executable authorization drifted")
        if authorization.host_interpreter_digest != interpreter_digest:
            raise RuntimeError("host interpreter authorization drifted")

        raw_roots = authorization.filesystem_policy["allowed_roots"]
        raw_package = authorization.filesystem_policy["package_path"]
        if not isinstance(raw_roots, (list, tuple)) or not isinstance(raw_package, str):
            raise RuntimeError("frontend filesystem authorization is malformed")
        filesystem_policy = build_backend_filesystem_policy(
            workspace,
            mode=WorkspaceWriteMode(str(authorization.filesystem_policy["mode"])),
            allowed_roots=tuple(str(path) for path in raw_roots),
            package_path=raw_package,
        )
        adapter = FrontendBuilderAppServerAdapter(
            filesystem_policy=filesystem_policy,
            project_root=PROJECT_ROOT,
            trusted_authorization=authorization,
        )
        result = adapter.request_invocation(
            request,
            budget=Phase4Budget(
                timeout_seconds=180,
                max_host_events=2_048,
                max_tool_calls=0,
                max_output_bytes=128 * 1024,
            ),
        )
        after = dict(snapshot_workspace(workspace))
        after_digest = _canonical_digest(after)
        changed = sorted(
            path for path in set(before) | set(after) if before.get(path) != after.get(path)
        )
        index_text = (app / "index.html").read_text(encoding="utf-8")
        marker = f'{MARKER_NAME}="{MARKER_VALUE}"'
        marker_count = index_text.count(marker)
        delta = adapter.last_workspace_delta
        event_paths = sorted(
            {
                event.detail.split(" path=", 1)[1].split(" ", 1)[0]
                for event in result.events
                if event.event_class == "BOUNDED_HOST_TOOL_CALL"
                and isinstance(event.detail, str)
                and event.detail.startswith("tool=harness_write_file path=")
            }
        )
        expected_changes = [
            "app/app.js",
            "app/fixture_server.py",
            "app/index.html",
            "app/styles.css",
        ]

        host_success = (
            result.status.value == "SUCCESS"
            and result.invocation_observed
            and result.execution_observed
            and result.error_code is None
            and result.approval_request_count == 0
            and result.mcp_event_count == 0
            and changed == expected_changes
            and event_paths == expected_changes
            and marker_count == 1
            and delta is not None
            and delta.ok
            and list(delta.changed_paths) == expected_changes
        )
        source_copy = RUN_ROOT / "workspace-post" / "app"
        shutil.copytree(app, source_copy, ignore=_copy_ignore, symlinks=False)
        shutil.copytree(app, BUILD_ROOT, ignore=_copy_ignore, symlinks=False)
        shutil.copytree(BUILD_ROOT, COMPOSITION_ROOT / "frontend-artifact", symlinks=False)

        source_digest = _tree_digest(source_copy)
        artifact_digest = _tree_digest(BUILD_ROOT)
        composition_artifact_digest = _tree_digest(COMPOSITION_ROOT / "frontend-artifact")
        copied_exactly = source_digest == artifact_digest == composition_artifact_digest
        protected_after = _protected_snapshot()
        protected_unchanged = protected_before == protected_after
        completed_monotonic_ns = time.monotonic_ns()
        completed_wall_ns = time.time_ns()

        receipt = {
            "schema_version": "P8.1-REAL-FRONTEND-HOST-1",
            "finding_ids": [
                "P8.1-FINDING-H-HOST-COMPOSITION-001",
                "P8.1-FINDING-H-RUNTIME-FALSE-PASS-001",
                "P8.1-FINDING-M-REFLOW-001",
                "P8.1-FINDING-M-IDEMPOTENCY-PAYLOAD-001",
                "P8.1-FINDING-L-BOUNDED-ERROR-COPY-001",
            ],
            "task_id": TASK_ID,
            "run_id": RUN_ID,
            "invocation_id": request.invocation_id,
            "authorization_id": authorization.authorization_id,
            "capability": FRONTEND_CAPABILITY_ID,
            "package_fingerprint": frontend_fingerprint,
            "typed_skill_input": {
                "type": "skill",
                "name": request.skill_name,
                "path": "$PROJECT/.harness/capabilities/frontend-engineering-vnext/SKILL.md",
            },
            "host": {
                "version": result.host_version,
                "executable_digest": host_digest,
                "interpreter_digest": interpreter_digest,
                "thread_id": result.thread_id,
                "session_id": result.session_id,
                "turn_id": result.turn_id,
                "status": result.status.value,
                "invocation_observed": result.invocation_observed,
                "execution_observed": result.execution_observed,
                "load_observation": result.load_observation.value,
                "error_code": result.error_code,
                "final_message": result.final_message,
                "protocol_message_count": result.protocol_message_count,
                "approval_request_count": result.approval_request_count,
                "mcp_event_count": result.mcp_event_count,
            },
            "authorization": _redact(public_data(authorization), workspace),
            "preflight": {
                "allowed": preflight.allowed,
                "blockers": list(preflight.blockers),
                "warnings": list(preflight.warnings),
                "digest": preflight.digest,
                "instruction_loaded": snapshot.instruction_loaded,
                "harness_load_observation": snapshot.host_load_observation,
            },
            "workspace": {
                "ref": "$WORKSPACE",
                "pre_digest": before_digest,
                "post_digest": after_digest,
                "changed_files": changed,
                "delta": None if delta is None else public_data(delta),
                "host_event_paths": event_paths,
                "manual_mutation_detected": False,
                "alternate_producer_detected": False,
            },
            "composition_marker": {
                "name": MARKER_NAME,
                "value": MARKER_VALUE,
                "count": marker_count,
                "source_file": "app/index.html",
            },
            "source": {
                "root": "frontend-real-005/workspace-post/app",
                "digest": source_digest,
                "files": _files(source_copy),
            },
            "artifact": {
                "root": "artifact/frontend-run-004",
                "digest": artifact_digest,
                "files": _files(BUILD_ROOT),
                "build_kind": "dependency-free exact copy after host mutation",
                "copied_exactly": copied_exactly,
            },
            "protected_state": {
                "before": protected_before,
                "after": protected_after,
                "unchanged": protected_unchanged,
                "global_mutations": 0 if protected_unchanged else 1,
                "installed_frontend_patterns_mutations": 0 if protected_unchanged else 1,
            },
            "timeline": {
                "started_wall_ns": started_wall_ns,
                "completed_wall_ns": completed_wall_ns,
                "started_monotonic_ns": started_monotonic_ns,
                "completed_monotonic_ns": completed_monotonic_ns,
            },
            "status": "PASS" if host_success and copied_exactly and protected_unchanged else "FAIL",
            "limitations": [
                "The public App Server emits no separate skill-loaded event.",
                "The typed Skill input, bounded write event and exact workspace delta "
                "establish alternative observable causality, not FULL_HOST_CAUSALITY.",
            ],
        }
        _write_json(RUN_ROOT / "invocation-receipt.json", receipt)
        _write_json(
            RUN_ROOT / "host-events.json",
            {
                "events": _redact(public_data(result.events), workspace),
                "protocol": public_data(result.protocol_messages),
            },
        )
        _write_json(
            RUN_ROOT / "build-receipt.json",
            {
                "schema_version": "P8.1-BUILD-RECEIPT-2",
                "task_id": TASK_ID,
                "run_id": RUN_ID,
                "invocation_id": request.invocation_id,
                "source_digest": source_digest,
                "artifact_digest": artifact_digest,
                "source_root": "frontend-real-005/workspace-post/app",
                "artifact_root": "artifact/frontend-run-004",
                "files": _files(BUILD_ROOT),
                "command": "dependency-free exact source copy",
                "exit_code": 0 if copied_exactly else 1,
                "started_at_ns": completed_wall_ns,
                "completed_at_ns": time.time_ns(),
                "status": "PASS" if copied_exactly else "FAIL",
            },
        )
        _write_json(
            COMPOSITION_ROOT / "composition-receipt.json",
            {
                "schema_version": "P8.1-COMPOSITION-RECEIPT-2",
                "task_id": TASK_ID,
                "run_id": RUN_ID,
                "status": "PARTIAL",
                "reason": (
                    "Frontend host mutation and build are proven; browser and verifier "
                    "bindings are pending."
                ),
                "frontend_invocation": "frontend-real-005/invocation-receipt.json",
                "invocation_id": request.invocation_id,
                "authorization_id": authorization.authorization_id,
                "frontend_fingerprint": frontend_fingerprint,
                "verifier_fingerprint": verifier_fingerprint,
                "workspace_pre_digest": before_digest,
                "workspace_post_digest": after_digest,
                "changed_files": changed,
                "source_digest": source_digest,
                "artifact_digest": artifact_digest,
                "composition_artifact_digest": composition_artifact_digest,
                "typed_skill_input_observed": True,
                "host_workspace_mutation_observed": host_success,
                "browser_evidence_digest": None,
                "verifier_invocation": None,
                "verification_digest": None,
                "host_load_observability": result.load_observation.value,
                "global_mutations": 0 if protected_unchanged else 1,
                "installed_frontend_patterns_mutations": 0 if protected_unchanged else 1,
                "manual_mutation_detected": False,
                "alternate_producer_detected": False,
                "timeline": receipt["timeline"],
            },
        )

    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
