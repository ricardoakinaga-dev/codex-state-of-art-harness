"""Read-only CLI for Phase 3 host inspection and declarative load planning."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from .phase3_host import (
    CodexHostAdapter,
    HostAdapterError,
    public_inventory,
    public_root,
    public_snapshot,
)
from .phase3_loader import LoaderError, SafeCapabilityLoader
from .phase3_models import (
    DisclosureLevel,
    Phase3Limits,
    public_data,
)
from .phase3_paths import redact_path
from .phase3_resolution import ResolutionEngine, ResolutionError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness-phase3",
        description="Read-only Codex host capability inspection and load planning",
    )
    parser.add_argument("--project-root", default=os.getcwd())
    parser.add_argument("--workspace-root")
    parser.add_argument("--json", action="store_true", dest="json_output")
    commands = parser.add_subparsers(dest="command", required=True)
    host = commands.add_parser("host", help="inspect the local Codex capability host")
    host.add_argument("--json", action="store_true", dest="json_output", default=argparse.SUPPRESS)
    host_commands = host.add_subparsers(dest="host_command", required=True)
    for name in ("inspect", "roots", "list", "duplicates", "compatibility", "refresh"):
        sub = host_commands.add_parser(name)
        sub.add_argument(
            "--json", action="store_true", dest="json_output", default=argparse.SUPPRESS
        )
    inspect_capability = host_commands.add_parser("capability-inspect")
    inspect_capability.add_argument("capability_id")
    inspect_capability.add_argument(
        "--json", action="store_true", dest="json_output", default=argparse.SUPPRESS
    )
    resolve = commands.add_parser("resolve", help="resolve one capability ID without loading it")
    resolve.add_argument("capability_id")
    resolve.add_argument("--version")
    resolve.add_argument(
        "--json", action="store_true", dest="json_output", default=argparse.SUPPRESS
    )
    load_plan = commands.add_parser("load-plan", help="prepare a bounded declarative load plan")
    load_plan.add_argument("capability_id")
    load_plan.add_argument(
        "--level",
        choices=[item.value for item in DisclosureLevel],
        default=DisclosureLevel.ROUTING_METADATA.value,
    )
    load_plan.add_argument(
        "--json", action="store_true", dest="json_output", default=argparse.SUPPRESS
    )
    doctor = commands.add_parser("doctor", help="run read-only host boundary checks")
    doctor.add_argument(
        "--json", action="store_true", dest="json_output", default=argparse.SUPPRESS
    )
    return parser


def _adapter(arguments: argparse.Namespace) -> CodexHostAdapter:
    project_root = Path(arguments.project_root).absolute()
    workspace = Path(arguments.workspace_root).absolute() if arguments.workspace_root else None
    return CodexHostAdapter(
        project_root=project_root,
        workspace_root=workspace,
        limits=Phase3Limits(),
    )


def _record_public(adapter: CodexHostAdapter, record: Any) -> dict[str, object]:
    item = cast(dict[str, object], public_data(record))
    item["path"] = redact_path(
        record.path,
        workspace_root=adapter.project_root,
        home_dir=adapter.home_dir,
        root_id=record.root_id,
    )
    provenance = cast(dict[str, object], item["provenance"])
    provenance["source_repository"] = f"root://{record.root_id}"
    return item


def _duplicates_public(adapter: CodexHostAdapter, findings: object) -> list[dict[str, object]]:
    values = cast(list[dict[str, object]], public_data(findings))
    for item in values:
        paths = item.get("paths")
        if isinstance(paths, list):
            item["paths"] = [
                redact_path(
                    path,
                    workspace_root=adapter.project_root,
                    home_dir=adapter.home_dir,
                    root_id="CAPABILITY",
                )
                for path in paths
                if isinstance(path, str)
            ]
    return values


def _render(value: object, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, indent=2, sort_keys=True, default=str))
    else:
        if isinstance(value, dict):
            for key, item in value.items():
                print(f"{key}: {item}")
        else:
            print(value)


def _execute(arguments: argparse.Namespace) -> dict[str, object]:
    adapter = _adapter(arguments)
    engine = ResolutionEngine()
    command = arguments.command
    if command == "host":
        host_command = arguments.host_command
        if host_command == "inspect":
            snapshot = adapter.inspect_host()
            return public_snapshot(
                snapshot,
                workspace_root=adapter.project_root,
                home_dir=adapter.home_dir,
            )
        inventory = adapter.discover_capabilities()
        if host_command == "roots":
            return {
                "schema_version": "P3-ROOTS-1",
                "roots": [
                    public_root(
                        item, workspace_root=adapter.project_root, home_dir=adapter.home_dir
                    )
                    for item in inventory.roots
                ],
            }
        if host_command in {"list", "refresh"}:
            value = public_inventory(
                inventory,
                workspace_root=adapter.project_root,
                home_dir=adapter.home_dir,
            )
            value["refresh"] = host_command == "refresh"
            value["writes"] = []
            return value
        if host_command == "duplicates":
            return {
                "schema_version": "P3-DUPLICATES-1",
                "duplicates": _duplicates_public(adapter, engine.duplicate_report(inventory)),
            }
        if host_command == "compatibility":
            return {
                "schema_version": "P3-COMPATIBILITY-1",
                "capabilities": [
                    {
                        "capability_id": item.capability_id,
                        "version": item.version,
                        "status": item.compatibility.status.value,
                        "missing_features": item.compatibility.missing_features,
                        "portability_debt": item.compatibility.portability_debt,
                        "reasons": item.compatibility.reasons,
                    }
                    for item in inventory.capabilities
                ],
            }
        record = adapter.inspect_capability(arguments.capability_id)
        return _record_public(adapter, record)
    inventory = adapter.discover_capabilities()
    if command == "resolve":
        request = arguments.capability_id
        if arguments.version:
            request = f"{request}@{arguments.version}"
        result = engine.resolve(inventory, request)
        value = cast(dict[str, object], public_data(result))
        value["selected"] = [_record_public(adapter, item) for item in result.selected]
        value["duplicates"] = _duplicates_public(adapter, result.duplicates)
        return value
    if command == "load-plan":
        level = DisclosureLevel(arguments.level)
        result = engine.resolve(inventory, arguments.capability_id)
        plan = SafeCapabilityLoader().plan(
            (arguments.capability_id,),
            result.selected,
            level,
            blockers=result.blockers,
            host_load_observable=False,
        )
        resolution = cast(dict[str, object], public_data(result))
        resolution["selected"] = [_record_public(adapter, item) for item in result.selected]
        resolution["duplicates"] = _duplicates_public(adapter, result.duplicates)
        return {"resolution": resolution, "load_plan": public_data(plan)}
    if command == "doctor":
        snapshot = adapter.inspect_host()
        checks = {
            "read_only_roots": all(not item.mutable for item in snapshot.roots),
            "bounded_root_count": len(snapshot.roots) <= adapter.limits.max_roots,
            "host_load_not_claimed": not adapter.observe_load_state("doctor").loaded,
            "no_execution_surface": not any(
                callable(getattr(adapter, name, None))
                for name in ("execute", "install", "delete", "mutate", "run_provider")
            ),
        }
        status = "PASS_WITH_LIMITATIONS" if all(checks.values()) else "FAIL"
        return {
            "schema_version": "P3-DOCTOR-1",
            "status": status,
            "checks": checks,
            "host_loaded": False,
            "limitations": snapshot.limitations,
        }
    raise HostAdapterError("unsupported Phase 3 command")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        value = _execute(arguments)
    except (HostAdapterError, LoaderError, ResolutionError, OSError, ValueError) as exc:
        error = {"status": "BLOCKED", "error": str(exc)[:240]}
        _render(error, bool(arguments.json_output))
        return 2
    _render(value, bool(arguments.json_output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
