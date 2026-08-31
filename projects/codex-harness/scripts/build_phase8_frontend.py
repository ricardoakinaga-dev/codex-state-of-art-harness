"""Build the dependency-free Phase 8 web pilot into a bounded artifact root."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
PILOT_ROOT = PROJECT_ROOT / "evidence/phase-8/pilots/frontend-engineering"
SOURCE_ROOT = PILOT_ROOT / "app"
DEFAULT_OUTPUT = PILOT_ROOT / "build/final"
SOURCE_FILES = ("index.html", "styles.css", "app.js", "fixture_server.py")


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_output(path: Path) -> Path:
    resolved = path.resolve()
    pilot = PILOT_ROOT.resolve()
    if not resolved.is_relative_to(pilot) or resolved == pilot:
        raise ValueError("build output must remain inside the Phase 8 pilot")
    return resolved


def build(output: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    target = _safe_output(output)
    target.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, object]] = []
    for name in SOURCE_FILES:
        source = SOURCE_ROOT / name
        if not source.is_file():
            raise FileNotFoundError(f"missing source file: {name}")
        destination = target / name
        shutil.copyfile(source, destination)
        copied.append(
            {"path": name, "bytes": destination.stat().st_size, "sha256": digest(destination)}
        )
    receipt = {
        "schema_version": "P8-BUILD-1",
        "build": "dependency-free-existing-web-stack",
        "source_root": "evidence/phase-8/pilots/frontend-engineering/app",
        "output_root": str(target.relative_to(PROJECT_ROOT)),
        "files": copied,
        "external_requests": 0,
        "generated_assets": [],
    }
    (target / "build-receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    receipt = build(arguments.output)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
