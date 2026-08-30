"""Run the separately authorized Phase 7 builder in a disposable workspace.

The script is deliberately a project-local execution surface.  It copies the
fictional pilot into a temporary directory, binds exact host/package
fingerprints, exposes only the Phase 7 bounded host tools, and persists a
small receipt plus the resulting source artifact under the rerun evidence
directory.  It never writes the source pilot or installed/global state.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from harness_kernel.phase4_host import _resolve_host_binding
from harness_kernel.phase4_models import ExecutionMode, Phase4Budget, public_data
from harness_kernel.phase6_host import discover_vnext_package, prepare_vnext_preflight
from harness_kernel.phase7_backend import package_fingerprint
from harness_kernel.phase7_host import (
    BackendBuilderAppServerAdapter,
    WorkspaceWriteMode,
    build_backend_filesystem_policy,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / "backend-engineering-vnext"
PILOT_ROOT = PROJECT_ROOT / "pilots" / "backend-appointment-api"
RERUN_ROOT = PROJECT_ROOT / "evidence" / "phase-7" / "reruns" / "PHASE7-RERUN-0007"
IGNORED_NAMES = frozenset(
    {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".phase4-ledger-anchor"}
)

TASK_ID = "PHASE7-RERUN-0007"
RUN_ID = "P7-REAL-BUILDER-RERUN-0007"
TASK = (
    "Harden the bounded fictional veterinary appointment API against transient SQLite lock "
    "bursts under concurrent writers in this disposable workspace. "
    "Inspect the existing app, migrations, and tests through the host list/read tools first. "
    "Implement the smallest material concurrency/retry improvement that preserves the documented "
    "HTTP contract and data-integrity guarantees, add or update focused tests, and run the fixed "
    "host test observer before returning the handoff. Use only host-provided dynamic tools."
)
CRITERIA = (
    "only app, migrations, or tests under the declared roots change",
    "the API and persistence invariants remain explicit and parameterized",
    "a focused regression test covers the material hardening change",
    "the fixed host test observer passes",
    "return a bounded implementation handoff with tests and limitations",
)


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORED_NAMES or name.startswith(".")}


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _source_files(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_NAMES or part.startswith(".") for part in relative.parts):
            continue
        result[relative.as_posix()] = {"bytes": path.stat().st_size, "sha256": _sha256(path)}
    return result


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _preflight(workspace: Path):
    snapshot = discover_vnext_package(
        PROJECT_ROOT,
        capability_id="backend-engineering-vnext",
    )
    result = prepare_vnext_preflight(
        PROJECT_ROOT,
        snapshot=snapshot,
        task_id=TASK_ID,
        run_id=RUN_ID,
        task=TASK,
        acceptance_criteria=CRITERIA,
        workspace=workspace,
        policy_path=PROJECT_ROOT / "config" / "phase7-execution-policy.json",
        mode=ExecutionMode.CONTROLLED_REAL,
        budget=Phase4Budget(
            timeout_seconds=180,
            max_context_bytes=64_000,
            max_host_events=1024,
            max_tool_calls=0,
            max_output_bytes=384 * 1024,
        ),
    )
    if not result.allowed or result.prepared is None or result.prepared.request is None:
        raise RuntimeError(f"canonical builder preflight blocked: {result.blockers}")
    return result, result.prepared.request


def _preflight_receipt(preflight: object) -> dict[str, object]:
    data = public_data(preflight)
    if not isinstance(data, dict):
        raise RuntimeError("canonical preflight could not be serialized")
    snapshot = data.get("snapshot")
    prepared = data.get("prepared")
    if not isinstance(snapshot, dict) or not isinstance(prepared, dict):
        raise RuntimeError("canonical preflight receipt is incomplete")
    phase4 = prepared.get("preflight")
    request = prepared.get("request")
    if not isinstance(phase4, dict) or not isinstance(request, dict):
        raise RuntimeError("canonical Phase 4 receipt is incomplete")
    authorization = phase4.get("authorization")
    context = phase4.get("context")
    if not isinstance(authorization, dict) or not isinstance(context, dict):
        raise RuntimeError("canonical authorization receipt is incomplete")
    record = snapshot.get("record")
    if not isinstance(record, dict):
        raise RuntimeError("canonical package record is incomplete")
    return {
        "allowed": data.get("allowed"),
        "mode": data.get("mode"),
        "blockers": data.get("blockers"),
        "warnings": data.get("warnings"),
        "digest": data.get("digest"),
        "host_invoked": data.get("host_invoked"),
        "snapshot": {
            "project_root": snapshot.get("project_root"),
            "capability_id": snapshot.get("capability_id"),
            "package_digest": snapshot.get("package_digest"),
            "manifest_digest": snapshot.get("manifest_digest"),
            "instruction_loaded": snapshot.get("instruction_loaded"),
            "blockers": snapshot.get("blockers"),
            "digest": snapshot.get("digest"),
            "record": {
                key: record.get(key)
                for key in (
                    "capability_id",
                    "version",
                    "content_hash",
                    "root_id",
                    "path",
                    "kind",
                    "status",
                    "load_eligibility",
                )
            },
        },
        "phase4": {
            "allowed": phase4.get("allowed"),
            "blockers": phase4.get("blockers"),
            "warnings": phase4.get("warnings"),
            "digest": phase4.get("digest"),
            "authorization": {
                key: authorization.get(key)
                for key in (
                    "authorization_id",
                    "task_id",
                    "run_id",
                    "capability_id",
                    "capability_version",
                    "package_fingerprint",
                    "requested_execution_mode",
                    "filesystem_policy",
                    "host_executable_digest",
                    "host_interpreter_digest",
                )
            },
            "context": {
                key: context.get(key)
                for key in (
                    "task_id",
                    "capability_id",
                    "package_fingerprint",
                    "skill_path",
                    "selected_references",
                    "omitted_references",
                    "estimated_bytes",
                    "digest",
                )
            },
            "request": {
                key: request.get(key)
                for key in ("invocation_id", "skill_name", "skill_path", "workspace")
            },
        },
    }


def main() -> int:
    if RERUN_ROOT.exists():
        raise RuntimeError("rerun evidence directory already exists; refusing overwrite")
    package_digest = package_fingerprint(PACKAGE_ROOT)
    binding = _resolve_host_binding()
    interpreter_digest = binding[5]
    if interpreter_digest is None:
        raise RuntimeError("pinned Codex/Node host binding is unavailable")
    _command, _executable, host_digest, _pinned, _interpreter, _unused = binding
    RERUN_ROOT.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix=".p7-backend-builder-rerun-", dir=PROJECT_ROOT) as raw:
        workspace = Path(raw) / "pilot"
        shutil.copytree(PILOT_ROOT, workspace, ignore=_copy_ignore, symlinks=False)
        before = _source_files(workspace)
        preflight, request = _preflight(workspace)
        if request.authorization.package_fingerprint != package_digest:
            raise RuntimeError("canonical preflight package fingerprint drifted")
        if request.authorization.host_executable_digest != host_digest:
            raise RuntimeError("canonical preflight host executable binding drifted")
        if request.authorization.host_interpreter_digest != interpreter_digest:
            raise RuntimeError("canonical preflight host interpreter binding drifted")
        filesystem_policy = build_backend_filesystem_policy(
            workspace,
            mode=WorkspaceWriteMode(str(request.authorization.filesystem_policy["mode"])),
            allowed_roots=tuple(
                str(path) for path in request.authorization.filesystem_policy["allowed_roots"]
            ),
            package_path=str(request.authorization.filesystem_policy["package_path"]),
        )
        adapter = BackendBuilderAppServerAdapter(
            filesystem_policy=filesystem_policy,
            project_root=PROJECT_ROOT,
            instruction_kernel=PACKAGE_ROOT.joinpath("SKILL.md").read_text(encoding="utf-8"),
            trusted_authorization=request.authorization,
            test_root=workspace / "tests",
        )
        result = adapter.request_invocation(
            request,
            budget=Phase4Budget(timeout_seconds=180, max_host_events=1024, max_tool_calls=0),
        )
        after = _source_files(workspace)
        changed = sorted(
            path for path in set(before) | set(after) if before.get(path) != after.get(path)
        )
        artifact_root = RERUN_ROOT / "artifact-v1"
        artifact_root.mkdir()
        for root_name in ("app", "migrations", "tests"):
            source_root = workspace / root_name
            if source_root.exists():
                shutil.copytree(
                    source_root,
                    artifact_root / root_name,
                    ignore=_copy_ignore,
                    symlinks=False,
                )
        delta = adapter.last_workspace_delta
        receipt = {
            "schema_version": "P7-RERUN-BUILDER-RECEIPT-1",
            "task_id": TASK_ID,
            "run_id": RUN_ID,
            "capability": "backend-engineering-vnext",
            "package_fingerprint": package_digest,
            "canonical_preflight": _preflight_receipt(preflight),
            "host": {
                "executable_digest": host_digest,
                "interpreter_digest": interpreter_digest,
                "command_bound": True,
                "authentication_mode": adapter.host_authentication_mode,
                "capability_credential_policy": "DENY",
                "capability_credential_tools_exposed": False,
            },
            "workspace": "disposable/pilot",
            "transport_status": result.status.value,
            "invocation_observed": result.invocation_observed,
            "execution_observed": result.execution_observed,
            "semantic_status": result.status.value,
            "error_code": result.error_code,
            "final_message": result.final_message,
            "changed_paths": changed,
            "workspace_delta": None if delta is None else public_data(delta),
            "events": public_data(result.events),
            "protocol": {
                "message_count": result.protocol_message_count,
                "mcp_events": result.mcp_event_count,
                "approval_requests": result.approval_request_count,
                "observations": public_data(result.protocol_messages),
            },
            "artifact": {
                "present": bool(changed),
                "root": "artifact-v1",
                "files": _source_files(artifact_root),
            },
            "policy": dict(request.authorization.filesystem_policy),
            "promotion": (
                "CANDIDATE_PENDING_VERIFIER"
                if result.status.value == "SUCCESS" and changed
                else "NOT_CREATED"
            ),
        }
        _write_json(RERUN_ROOT / "builder-receipt.json", receipt)
    return 0 if result.status.value == "SUCCESS" and changed else 2


if __name__ == "__main__":
    raise SystemExit(main())
