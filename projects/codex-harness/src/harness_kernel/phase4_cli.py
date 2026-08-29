"""Explicit Phase 4 CLI for dry-run, preparation and controlled pilot calls."""

from __future__ import annotations

import argparse
import json
import stat
import uuid
from collections.abc import Sequence
from pathlib import Path

from .phase3_host import CodexHostAdapter
from .phase3_resolution import ResolutionEngine
from .phase4_evidence import EvidenceError, EvidenceWriter, public_outcome, redact_paths
from .phase4_execution import InvocationEngine
from .phase4_host import CodexAppServerAdapter
from .phase4_models import ExecutionMode, InvocationResultStatus, Phase4Budget
from .phase4_policy import ExecutionPolicyRegistry, Phase4PolicyError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness-phase4",
        description="Run an explicitly bounded Phase 4 Codex capability pilot.",
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", dest="json_output")
    subparsers = parser.add_subparsers(dest="command", required=True)
    invoke = subparsers.add_parser("invoke", help="prepare or invoke one exact capability")
    invoke.add_argument("capability")
    invoke.add_argument("--task", required=True)
    invoke.add_argument("--acceptance", action="append", default=[])
    modes = invoke.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--controlled-real", action="store_true")
    invoke.add_argument("--workspace", type=Path)
    invoke.add_argument("--policy", type=Path)
    invoke.add_argument("--confirm-fingerprint")
    invoke.add_argument("--timeout", type=int, default=60)
    invoke.add_argument("--evidence-dir", type=Path)
    invoke.add_argument("--explain", action="store_true")
    invoke.add_argument(
        "--json", action="store_true", dest="json_output", default=argparse.SUPPRESS
    )
    return parser


def _mode(arguments: argparse.Namespace) -> ExecutionMode:
    if arguments.dry_run:
        return ExecutionMode.DRY_RUN
    if arguments.prepare_only:
        return ExecutionMode.PREPARE_ONLY
    if arguments.controlled_real:
        return ExecutionMode.CONTROLLED_REAL
    return ExecutionMode.BLOCKED


def _project_path(project_root: Path, candidate: Path, label: str) -> Path:
    if not candidate.is_absolute():
        candidate = project_root / candidate
    try:
        resolved_project = project_root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if not resolved_candidate.is_relative_to(resolved_project):
        raise ValueError(f"{label} must remain inside project root")
    if _has_symlink_component(candidate):
        raise ValueError(f"{label} cannot contain symlinks")
    return resolved_candidate


def _has_symlink_component(path: Path) -> bool:
    if not path.is_absolute():
        return True
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            return True
        if stat.S_ISLNK(metadata.st_mode):
            return True
    return False


def _load_policy(project_root: Path, requested: Path | None) -> ExecutionPolicyRegistry:
    path = requested or project_root / "config" / "phase4-execution-policy.json"
    try:
        resolved = _project_path(project_root, path, "policy")
    except ValueError:
        raise
    if not resolved.exists():
        return ExecutionPolicyRegistry(())
    return ExecutionPolicyRegistry.from_json(resolved)


def _missing_payload(mode: ExecutionMode, capability: str, blocker: str) -> dict[str, object]:
    return {
        "schema_version": "P4-OUTCOME-1",
        "mode": mode.value,
        "status": InvocationResultStatus.BLOCKED.value,
        "capability": capability,
        "blockers": [blocker],
        "warnings": [],
        "host_invoked": False,
        "artifacts": [],
        "verification": None,
        "assurance": {"decision": "BLOCK", "reason": "capability was not resolved"},
    }


def _human_output(payload: dict[str, object]) -> str:
    mode = payload.get("mode", "UNKNOWN")
    status = payload.get("status", "UNKNOWN")
    host_invoked = payload.get("host_invoked", False)
    lines = [
        f"Mode: {mode}",
        f"Status: {status}",
        "REAL EXECUTION REQUESTED" if mode == "CONTROLLED_REAL" else "NO HOST EXECUTION",
        f"Host invoked: {'yes' if host_invoked else 'no'}",
    ]
    blockers = _sequence(payload.get("blockers"))
    if blockers:
        lines.append("Blockers: " + ", ".join(str(item) for item in blockers))
    limitations = _sequence(payload.get("limitations"))
    if limitations:
        lines.append("Limitations: " + ", ".join(str(item) for item in limitations))
    return "\n".join(lines)


def _sequence(value: object) -> tuple[object, ...]:
    return tuple(value) if isinstance(value, (list, tuple)) else ()


def _run_invoke(arguments: argparse.Namespace) -> dict[str, object]:
    project_root = arguments.project_root.resolve(strict=True)
    mode = _mode(arguments)
    workspace = arguments.workspace or project_root
    if not workspace.is_absolute():
        workspace = project_root / workspace
    if any(part in {".", ".."} for part in workspace.parts) or _has_symlink_component(workspace):
        return _missing_payload(mode, arguments.capability, "WORKSPACE_SYMLINK")
    try:
        workspace_resolved = workspace.resolve(strict=True)
    except (OSError, RuntimeError):
        return _missing_payload(mode, arguments.capability, "WORKSPACE_UNAVAILABLE")
    if not workspace_resolved.is_dir():
        return _missing_payload(mode, arguments.capability, "WORKSPACE_NOT_DIRECTORY")
    if not workspace_resolved.is_relative_to(project_root):
        return _missing_payload(mode, arguments.capability, "WORKSPACE_OUTSIDE_PROJECT")
    policy = _load_policy(project_root, arguments.policy)
    adapter = CodexHostAdapter(
        project_root=project_root, workspace_root=workspace_resolved, home_dir=Path.home()
    )
    inventory = adapter.discover_capabilities()
    resolution = ResolutionEngine().resolve(inventory, arguments.capability)
    if not resolution.selected:
        return _missing_payload(mode, arguments.capability, "CAPABILITY_NOT_RESOLVED")
    record = resolution.selected[0]
    raw_acceptance = arguments.acceptance
    acceptance = (
        tuple(raw_acceptance)
        if isinstance(raw_acceptance, (list, tuple))
        else ("response is non-empty",)
    ) or ("response is non-empty",)
    if arguments.timeout <= 0:
        return _missing_payload(mode, arguments.capability, "TIMEOUT_INVALID")
    budget = Phase4Budget(timeout_seconds=arguments.timeout)
    engine = InvocationEngine(CodexAppServerAdapter())
    prepared = engine.prepare(
        record,
        inventory,
        resolution,
        policy,
        task_id="TASK-P4-" + uuid.uuid4().hex[:12],
        run_id="RUN-P4-" + uuid.uuid4().hex[:12],
        task=arguments.task,
        acceptance_criteria=acceptance,
        workspace=workspace,
        mode=mode,
        budget=budget,
        expected_fingerprint=arguments.confirm_fingerprint,
        require_fingerprint_confirmation=mode is ExecutionMode.CONTROLLED_REAL,
    )
    outcome = engine.execute_prepared(prepared)
    payload = public_outcome(outcome, workspace=workspace)
    payload["capability"] = record.capability_id
    payload["package_fingerprint"] = record.content_hash
    if arguments.explain:
        payload["explain"] = {
            "resolution_status": resolution.status.value,
            "resolution_blockers": list(resolution.blockers),
            "preflight": {
                "allowed": outcome.preflight.allowed,
                "blockers": list(outcome.preflight.blockers),
                "warnings": list(outcome.preflight.warnings),
                "digest": outcome.preflight.digest,
            },
            "host_boundary": (
                "official Codex app-server; no shell, scripts, tools, network, MCP, "
                "providers, credentials, or subagents"
            ),
        }
    if arguments.evidence_dir is not None:
        evidence_dir = _project_path(project_root, arguments.evidence_dir, "evidence directory")
        writer = EvidenceWriter(str(evidence_dir))
        writer.write_json(f"invocation-receipts/{outcome.receipt.invocation_id}.json", payload)
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command != "invoke":
            raise ValueError("unsupported Phase 4 command")
        payload = _run_invoke(arguments)
    except (OSError, ValueError, Phase4PolicyError, EvidenceError) as exc:
        payload = {
            "schema_version": "P4-OUTCOME-1",
            "mode": "BLOCKED",
            "status": "BLOCKED",
            "blockers": [type(exc).__name__.upper()],
            "message": "Phase 4 request could not be represented safely",
            "host_invoked": False,
        }
    if arguments.json_output:
        print(json.dumps(redact_paths(payload), ensure_ascii=False, sort_keys=True))
    else:
        print(_human_output(payload))
    successful_statuses = {
        InvocationResultStatus.SUCCESS.value,
        InvocationResultStatus.PREPARED.value,
    }
    return 0 if payload.get("status") in successful_statuses else 2


if __name__ == "__main__":
    raise SystemExit(main())
