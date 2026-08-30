"""Run the single bounded Phase 7 repair against the current candidate artifact."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from harness_kernel.phase4_host import _resolve_host_binding  # noqa: E402
from harness_kernel.phase4_models import ExecutionMode, Phase4Budget, public_data  # noqa: E402
from harness_kernel.phase6_host import (  # noqa: E402
    discover_vnext_package,
    prepare_vnext_preflight,
)
from harness_kernel.phase7_backend import package_fingerprint  # noqa: E402
from harness_kernel.phase7_host import (  # noqa: E402
    BackendBuilderAppServerAdapter,
    WorkspaceWriteMode,
    build_backend_filesystem_policy,
)

PACKAGE_ROOT = PROJECT_ROOT / ".harness" / "capabilities" / "backend-engineering-vnext"
BASE_ARTIFACT_ROOT = (
    PROJECT_ROOT / "evidence" / "phase-7" / "reruns" / "PHASE7-RERUN-0007" / "artifact-v1"
)
REPAIR_ROOT = PROJECT_ROOT / "evidence" / "phase-7" / "reruns" / "PHASE7-REPAIR-0007"
IGNORED_NAMES = frozenset(
    {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".phase4-ledger-anchor"}
)

TASK_ID = "PHASE7-REPAIR-0007"
RUN_ID = "P7-REAL-BUILDER-REPAIR-0007"
TASK = (
    "Repair the current bounded backend artifact in this disposable workspace. "
    "Inspect app, migrations and tests through the bounded host list/read tools first. "
    "Preserve the reviewed idempotency-replay hardening and its regression test. "
    "Fix only the known static-quality defect: format the changed Python test code to the "
    "project's 100-column Ruff boundary. Do not redesign the API, persistence, migrations, "
    "acceptance criteria or unrelated files. Run the fixed host test observer and return a "
    "bounded handoff. Use only host-provided dynamic tools."
)
CRITERIA = (
    "only app, migrations, or tests under the declared roots change",
    "the idempotency replay hardening and focused regression remain present",
    "the fixed host test observer passes",
    "the repair is limited to the known static-quality defect",
)


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name in IGNORED_NAMES or name.startswith(".")}


def _source_files(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_NAMES or part.startswith(".") for part in relative.parts):
            continue
        result[relative.as_posix()] = {
            "bytes": path.stat().st_size,
            "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        }
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
            max_host_events=512,
            max_tool_calls=0,
            max_repair_iterations=1,
            max_output_bytes=384 * 1024,
        ),
    )
    if not result.allowed or result.prepared is None or result.prepared.request is None:
        raise RuntimeError(f"canonical repair preflight blocked: {result.blockers}")
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
    if REPAIR_ROOT.exists():
        raise RuntimeError("repair evidence directory already exists; refusing overwrite")
    if not BASE_ARTIFACT_ROOT.is_dir():
        raise RuntimeError("base artifact is unavailable")
    package_digest = package_fingerprint(PACKAGE_ROOT)
    binding = _resolve_host_binding()
    interpreter_digest = binding[5]
    if interpreter_digest is None:
        raise RuntimeError("pinned Codex/Node host binding is unavailable")
    _command, _executable, host_digest, _pinned, _interpreter, _unused = binding
    REPAIR_ROOT.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix=".p7-backend-repair-", dir=PROJECT_ROOT) as raw:
        workspace = Path(raw) / "artifact"
        shutil.copytree(BASE_ARTIFACT_ROOT, workspace, ignore=_copy_ignore, symlinks=False)
        before = _source_files(workspace)
        preflight, request = _preflight(workspace)
        if request.authorization.package_fingerprint != package_digest:
            raise RuntimeError("canonical repair preflight package fingerprint drifted")
        if request.authorization.host_executable_digest != host_digest:
            raise RuntimeError("canonical repair preflight host executable binding drifted")
        if request.authorization.host_interpreter_digest != interpreter_digest:
            raise RuntimeError("canonical repair preflight host interpreter binding drifted")
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
            max_builder_invocations=1,
            max_repairs=1,
        )
        result = adapter.request_invocation(
            request,
            budget=Phase4Budget(timeout_seconds=180, max_host_events=512, max_tool_calls=0),
        )
        after = _source_files(workspace)
        changed = sorted(
            path for path in set(before) | set(after) if before.get(path) != after.get(path)
        )
        artifact_root = REPAIR_ROOT / "artifact-v2"
        artifact_root.mkdir()
        shutil.copytree(
            workspace, artifact_root, ignore=_copy_ignore, symlinks=False, dirs_exist_ok=True
        )
        delta = adapter.last_workspace_delta
        receipt = {
            "schema_version": "P7-REPAIR-BUILDER-RECEIPT-1",
            "task_id": TASK_ID,
            "run_id": RUN_ID,
            "base_artifact": "../PHASE7-RERUN-0007/artifact-v1",
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
            "transport_status": result.status.value,
            "invocation_observed": result.invocation_observed,
            "execution_observed": result.execution_observed,
            "semantic_status": result.status.value,
            "error_code": result.error_code,
            "final_message": result.final_message,
            "events": public_data(result.events),
            "changed_paths": changed,
            "workspace_delta": None if delta is None else public_data(delta),
            "protocol": {
                "message_count": result.protocol_message_count,
                "mcp_events": result.mcp_event_count,
                "approval_requests": result.approval_request_count,
                "observations": public_data(result.protocol_messages),
            },
            "artifact": {
                "present": bool(changed),
                "root": "artifact-v2",
                "files": _source_files(artifact_root),
            },
            "promotion": "CANDIDATE_PENDING_VERIFIER" if changed else "NOT_CREATED",
        }
        _write_json(REPAIR_ROOT / "repair-receipt.json", receipt)
    return 0 if result.status.value == "SUCCESS" and changed else 2


if __name__ == "__main__":
    raise SystemExit(main())
