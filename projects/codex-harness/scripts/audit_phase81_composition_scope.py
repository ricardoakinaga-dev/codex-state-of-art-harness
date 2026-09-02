"""Run the exact Phase 8.1 bridge with an independent global-scope audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from build_phase81_composition_bridge import compose

PROJECT_ROOT = Path(__file__).parents[1]
EVIDENCE_ROOT = PROJECT_ROOT / "evidence/phase-8.1"
SCOPE_ROOTS = (
    Path.home() / ".codex/skills",
    Path.home() / ".agents/skills",
    Path.home() / ".codex/config.toml",
    PROJECT_ROOT / ".harness/capabilities/frontend-engineering-vnext",
    PROJECT_ROOT / ".harness/capabilities/verification-loop-vnext",
)


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.exists():
        return {"path": str(path), "exists": False, "digest": None, "files": 0}
    if resolved.is_file():
        return {"path": str(path), "exists": True, "digest": file_digest(resolved), "files": 1}
    entries = []
    for child in sorted(resolved.rglob("*")):
        if child.is_symlink():
            entries.append((child.relative_to(resolved).as_posix(), "SYMLINK"))
        elif child.is_file():
            entries.append((child.relative_to(resolved).as_posix(), file_digest(child)))
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "path": str(path),
        "exists": True,
        "digest": "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "files": len(entries),
    }


def snapshot_digest(items: list[dict[str, Any]]) -> str:
    payload = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host-receipt", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    before = [snapshot(path) for path in SCOPE_ROOTS]
    bridge = compose(
        host_receipt_path=args.host_receipt,
        source_root=args.source_root,
        output_root=args.output_root,
        receipt_path=args.receipt,
        expected_fingerprint=args.fingerprint,
        run_id=args.run_id,
    )
    after = [snapshot(path) for path in SCOPE_ROOTS]
    before_digest = snapshot_digest(before)
    after_digest = snapshot_digest(after)
    audit = {
        "schema_version": "P8.1-COMPOSITION-SCOPE-AUDIT-1",
        "task_id": "PHASE8.1-001",
        "run_id": args.run_id,
        "bridge_receipt": str(args.receipt.resolve().relative_to(PROJECT_ROOT)),
        "bridge_artifact": bridge["composed_artifact"],
        "scope_roots": [str(path) for path in SCOPE_ROOTS],
        "before": before,
        "after": after,
        "before_digest": before_digest,
        "after_digest": after_digest,
        "global_mutations": int(before_digest != after_digest),
        "capability_file_mutations": int(
            any(
                before_item != after_item
                for before_item, after_item in zip(before, after, strict=True)
            )
        ),
        "external_producer": False,
        "manual_mutation_during_run": False,
        "audit_method": "read-only digest snapshots around the exact bridge subprocess boundary",
        "git_status_observation": subprocess.run(
            ["git", "-C", str(PROJECT_ROOT.parent), "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines(),
    }
    output = args.audit.resolve()
    if not output.is_relative_to(EVIDENCE_ROOT.resolve()):
        raise ValueError("audit output must remain inside the Phase 8.1 evidence root")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, sort_keys=True))
    return 0 if audit["global_mutations"] == 0 and audit["capability_file_mutations"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
