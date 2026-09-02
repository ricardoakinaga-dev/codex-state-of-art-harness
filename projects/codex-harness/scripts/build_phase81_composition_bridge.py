"""Bind a completed host response to an exact, read-only browser artifact copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parents[1]
EVIDENCE_ROOT = PROJECT_ROOT / "evidence/phase-8.1"
SOURCE_ROOT = EVIDENCE_ROOT / "artifact/frontend-run-001"
DEFAULT_OUTPUT_ROOT = EVIDENCE_ROOT / "composition-run-001/frontend-artifact"
DEFAULT_RECEIPT = EVIDENCE_ROOT / "composition-run-001/composition-receipt.json"
SOURCE_FILES = ("index.html", "styles.css", "app.js", "fixture_server.py")


def _digest_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _digest(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _tree_digest(root: Path) -> str:
    entries = [f"{name}:{_digest(root / name)}" for name in SOURCE_FILES]
    return _digest_bytes("\n".join(entries).encode("utf-8"))


def _snapshot(root: Path) -> dict[str, dict[str, Any]]:
    if not root.exists():
        return {}
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"composition root is not a regular directory: {root}")
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"composition root contains a symlink: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            result[relative] = {"bytes": path.stat().st_size, "sha256": _digest(path)}
    return result


def _snapshot_digest(files: dict[str, dict[str, Any]]) -> str:
    payload = json.dumps(
        [{"path": path, **files[path]} for path in sorted(files)],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _digest_bytes(payload)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _resolve_inside(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"{label} escapes the Phase 8.1 evidence root")
    return resolved


def compose(
    *,
    host_receipt_path: Path,
    source_root: Path,
    output_root: Path,
    receipt_path: Path,
    expected_fingerprint: str,
    run_id: str,
) -> dict[str, Any]:
    host_receipt_path = _resolve_inside(host_receipt_path, EVIDENCE_ROOT, "host receipt")
    source_root = _resolve_inside(source_root, EVIDENCE_ROOT, "source artifact")
    output_root = output_root.resolve()
    receipt_path = receipt_path.resolve()
    if not output_root.is_relative_to(EVIDENCE_ROOT.resolve()):
        raise ValueError("composition output must remain inside the Phase 8.1 evidence root")
    if not receipt_path.is_relative_to(EVIDENCE_ROOT.resolve()):
        raise ValueError("composition receipt must remain inside the Phase 8.1 evidence root")
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite composition output: {output_root}")
    if receipt_path.exists():
        raise FileExistsError(f"refusing to overwrite composition receipt: {receipt_path}")

    host = _read_object(host_receipt_path)
    host_result = host.get("host_result")
    receipt = host.get("receipt")
    preflight = host.get("preflight")
    authorization = preflight.get("authorization") if isinstance(preflight, dict) else None
    filesystem_policy = (
        authorization.get("filesystem_policy") if isinstance(authorization, dict) else None
    )
    if (
        not isinstance(host_result, dict)
        or not isinstance(receipt, dict)
        or not isinstance(authorization, dict)
        or not isinstance(filesystem_policy, dict)
    ):
        raise ValueError("host receipt is missing host_result, receipt or authorization")
    required_host_facts = {
        "capability": "frontend-engineering-vnext",
        "package_fingerprint": expected_fingerprint,
        "host_invoked": True,
    }
    if any(host.get(key) != value for key, value in required_host_facts.items()):
        raise ValueError("host receipt does not match the expected capability identity")
    if (
        host_result.get("status") != "SUCCESS"
        or host_result.get("execution_observed") is not True
        or host_result.get("final_message") != "READY"
    ):
        raise ValueError("host receipt is not an observed completed handshake")
    if authorization.get("capability_id") != "frontend-engineering-vnext":
        raise ValueError("host authorization capability does not match the frontend package")
    required_authorization = {
        "package_write_allowed": False,
        "mode": "READ_ONLY",
        "network": "DENY",
        "mcp": "DENY",
        "providers": "DENY",
        "shell": "DENY",
        "credentials": "DENY",
    }
    if any(filesystem_policy.get(key) != value for key, value in required_authorization.items()):
        raise ValueError("host authorization is not the expected read-only bounded policy")

    build_receipt = _read_object(source_root / "build-receipt.json")
    if build_receipt.get("source_tree_digest") != _tree_digest(source_root):
        raise ValueError("source artifact tree does not match its build receipt")
    before = _snapshot(output_root)
    output_root.mkdir(parents=True)
    copied: list[dict[str, Any]] = []
    for name in SOURCE_FILES:
        source = source_root / name
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"source artifact file is unavailable or unsafe: {name}")
        target = output_root / name
        target.write_bytes(source.read_bytes())
        copied.append({"path": name, "bytes": target.stat().st_size, "sha256": _digest(target)})
    after = _snapshot(output_root)
    expected_files = {
        item["path"]: {"bytes": item["bytes"], "sha256": item["sha256"]} for item in copied
    }
    if after != expected_files or _tree_digest(output_root) != build_receipt.get(
        "source_tree_digest"
    ):
        raise ValueError("composition copy is not byte-identical to the source artifact")

    generated_at = time.time_ns()
    report = {
        "schema_version": "P8.1-COMPOSITION-BRIDGE-1",
        "task_id": "PHASE8.1-001",
        "status": "PARTIAL",
        "run_id": run_id,
        "producer_id": "phase81-harness-composition-bridge",
        "producer_kind": "AUTHORIZED_EXACT_ARTIFACT_COPY",
        "host": {
            "receipt_path": str(host_receipt_path.relative_to(PROJECT_ROOT)),
            "receipt_digest": _digest(host_receipt_path),
            "invocation_id": receipt.get("invocation_id"),
            "capability": host.get("capability"),
            "package_fingerprint": host.get("package_fingerprint"),
            "host_result_status": host_result.get("status"),
            "execution_observed": host_result.get("execution_observed"),
            "final_message": host_result.get("final_message"),
            "load_observation": host_result.get("load_observation"),
            "authorization": {
                "authorization_id": authorization.get("authorization_id"),
                "capability_id": authorization.get("capability_id"),
                "filesystem_mode": filesystem_policy.get("mode"),
                "workspace": filesystem_policy.get("workspace"),
                "allowed_roots": filesystem_policy.get("allowed_roots"),
                "package_write_allowed": filesystem_policy.get("package_write_allowed"),
                "network": filesystem_policy.get("network"),
                "mcp": filesystem_policy.get("mcp"),
                "providers": filesystem_policy.get("providers"),
                "shell": filesystem_policy.get("shell"),
                "credentials": filesystem_policy.get("credentials"),
            },
        },
        "source": {
            "root": str(source_root.relative_to(PROJECT_ROOT)),
            "build_receipt": str((source_root / "build-receipt.json").relative_to(PROJECT_ROOT)),
            "build_receipt_digest": _digest(source_root / "build-receipt.json"),
            "tree_digest": _tree_digest(source_root),
            "files": copied,
        },
        "composed_artifact": {
            "root": str(output_root.relative_to(PROJECT_ROOT)),
            "tree_digest": _tree_digest(output_root),
            "files": copied,
        },
        "workspace_observation": {
            "before_snapshot_digest": _snapshot_digest(before),
            "after_snapshot_digest": _snapshot_digest(after),
            "changed_paths": sorted(set(before) | set(after)),
            "capability_file_mutations": 0,
            "global_mutations": 0,
            "external_producer": False,
            "manual_mutation_during_run": False,
            "authorization_id": authorization.get("authorization_id"),
            "authorized_host_workspace": filesystem_policy.get("workspace"),
            "source_read_only": True,
            "composition_output_confined_to_evidence": True,
        },
        "ordered_chain": [
            "HOST_RESPONSE_OBSERVED",
            "EXACT_ARTIFACT_IDENTITY_CHECKED",
            "COMPOSITION_COPY_CREATED",
            "COMPOSITION_COPY_RECHECKED",
            "BROWSER_MAY_SERVE_COMPOSED_ROOT",
        ],
        "limitations": [
            "HOST_LOAD_UNOBSERVABLE",
            "This is an observable harness composition chain, not full host skill-load causality.",
            "The bridge copies an existing exact artifact and does not generate application code.",
        ],
        "generated_at_ns": generated_at,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    canonical_receipt = EVIDENCE_ROOT / "composition-receipt.json"
    if canonical_receipt != receipt_path:
        canonical_receipt.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host-receipt", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--run-id", default="P81-COMPOSE-001")
    arguments = parser.parse_args()
    report = compose(
        host_receipt_path=arguments.host_receipt,
        source_root=arguments.source_root,
        output_root=arguments.output_root,
        receipt_path=arguments.receipt,
        expected_fingerprint=arguments.fingerprint,
        run_id=arguments.run_id,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
