from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from harness_kernel.phase4_evidence import (
    EvidenceError,
    EvidenceWriter,
    build_review_manifest,
    snapshot_tree,
)


def test_evidence_writer_is_project_local_atomic_and_redacts_secrets(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    writer = EvidenceWriter(root)
    writer.write_json(
        "reports/summary.json",
        {"password": "do-not-publish", "message": "secret=also-private"},
    )

    payload = (root / "reports" / "summary.json").read_text(encoding="utf-8")
    assert "do-not-publish" not in payload
    assert "also-private" not in payload
    manifest = build_review_manifest(root, ("reports/summary.json",))
    assert manifest["entry_count"] == 1


def test_evidence_writer_rejects_escape_and_symlinked_directories(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    writer = EvidenceWriter(root)
    with pytest.raises(EvidenceError):
        writer.write_text("../outside.txt", "unsafe")

    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(EvidenceError):
        writer.write_text("link/file.txt", "unsafe")


def test_evidence_writer_rejects_nonfinite_and_cyclic_json(tmp_path: Path) -> None:
    writer = EvidenceWriter(tmp_path / "evidence")
    with pytest.raises(EvidenceError, match="serialized safely"):
        writer.write_json("reports/nonfinite.json", {"value": math.nan})
    cyclic: list[object] = []
    cyclic.append(cyclic)
    with pytest.raises(EvidenceError, match="serialized safely"):
        writer.write_json("reports/cyclic.json", cyclic)


def test_review_manifest_binds_repository_inputs_and_metadata_snapshot_is_content_free(
    tmp_path: Path,
) -> None:
    root = tmp_path / "evidence"
    writer = EvidenceWriter(root)
    writer.write_text("reports/summary.json", "{}\n")
    source = tmp_path / "source.py"
    source.write_text("print('bounded')\n", encoding="utf-8")

    manifest = build_review_manifest(
        root,
        ("reports/summary.json",),
        bound_files=(("source.py", source),),
    )
    snapshot = snapshot_tree((tmp_path,), max_entries=64)

    assert manifest["entry_count"] == 2
    assert any(item["scope"] == "repository" for item in manifest["entries"])
    assert "print('bounded')" not in json.dumps(snapshot)


def test_snapshot_digests_all_roots_when_serialized_sample_is_bounded(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "one.txt").write_text("first", encoding="utf-8")
    (second / "two.txt").write_text("second", encoding="utf-8")

    snapshot = snapshot_tree((first, second), max_entries=1)

    assert snapshot["truncated"] is True
    assert snapshot["entry_count"] == 1
    assert snapshot["scanned_entry_count"] == 2
    assert len(snapshot["root_entry_digests"]) == 2


def test_snapshot_supports_a_regular_file_root_without_reading_contents(tmp_path: Path) -> None:
    target = tmp_path / "config.toml"
    target.write_text("secret = 'not read'\n", encoding="utf-8")

    snapshot = snapshot_tree((target,))

    assert snapshot["roots"] == [{"root": str(target), "status": "OBSERVED_FILE"}]
    assert snapshot["scanned_entry_count"] == 1
    assert "not read" not in json.dumps(snapshot)
