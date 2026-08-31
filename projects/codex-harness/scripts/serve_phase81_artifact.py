"""Serve one exact Phase 8.1 artifact and record the serving root binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
EVIDENCE_ROOT = PROJECT_ROOT / "evidence" / "phase-8.1"
SOURCE_FILES = ("index.html", "styles.css", "app.js", "fixture_server.py")


def file_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def tree_digest(root: Path) -> str:
    payload = "\n".join(f"{name}:{file_digest(root / name)}" for name in SOURCE_FILES)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--run-id", default="P81-SERVER-001")
    args = parser.parse_args()

    artifact_root = args.artifact_root.resolve(strict=True)
    if not artifact_root.is_relative_to(EVIDENCE_ROOT.resolve()):
        raise ValueError("artifact root must remain inside Phase 8.1 evidence")
    observed_digest = tree_digest(artifact_root)
    if observed_digest != args.expected_digest:
        raise ValueError("artifact digest does not match the expected current digest")
    command = [sys.executable, str(artifact_root / "fixture_server.py"), "--port", str(args.port)]
    started_at_ns = time.time_ns()
    child = subprocess.Popen(command, cwd=artifact_root)
    receipt = {
        "schema_version": "P8.1-SERVER-BINDING-1",
        "task_id": "PHASE8.1-001",
        "run_id": args.run_id,
        "artifact_root": str(artifact_root.relative_to(PROJECT_ROOT)),
        "artifact_digest": observed_digest,
        "port": args.port,
        "base_url": f"http://127.0.0.1:{args.port}/",
        "command": command,
        "pid": child.pid,
        "started_at_ns": started_at_ns,
        "network": "LOOPBACK_ONLY",
        "process_started": child.poll() is None,
        "binding_header": "X-Phase81-Artifact-Digest",
    }
    receipt_path = args.receipt.resolve()
    if not receipt_path.is_relative_to(EVIDENCE_ROOT.resolve()):
        child.terminate()
        raise ValueError("receipt must remain inside Phase 8.1 evidence")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    try:
        return child.wait()
    except KeyboardInterrupt:
        child.terminate()
        return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
