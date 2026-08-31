from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from harness_kernel import phase3_paths as paths
from harness_kernel.phase3_models import CapabilityRoot, Phase3Limits, RootScope
from harness_kernel.phase3_paths import PathSafetyError


def test_canonicalize_root_reports_missing_and_invalid_roots(tmp_path: Path) -> None:
    with pytest.raises(PathSafetyError, match="absolute"):
        paths.canonicalize_root("relative", root_id="root", scope=RootScope.PROJECT)

    missing = paths.canonicalize_root(
        tmp_path / "missing", root_id="root", scope=RootScope.PROJECT, allow_missing=True
    )
    assert missing.security_status == "UNAVAILABLE"
    assert missing.readable is False
    with pytest.raises(PathSafetyError, match="unavailable"):
        paths.canonicalize_root(
            tmp_path / "missing-again",
            root_id="root",
            scope=RootScope.PROJECT,
            allow_missing=False,
        )

    regular = tmp_path / "regular"
    regular.write_text("not a directory", encoding="utf-8")
    with pytest.raises(PathSafetyError, match="directory"):
        paths.canonicalize_root(regular, root_id="root", scope=RootScope.PROJECT)

    link = tmp_path / "root-link"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable")
    with pytest.raises(PathSafetyError, match="symlink"):
        paths.canonicalize_root(link, root_id="root", scope=RootScope.PROJECT)


def test_canonicalize_root_rejects_canonicalization_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    original_resolve = Path.resolve

    def fail_resolve(self: Path, *, strict: bool = False) -> Path:
        if self == root and strict:
            raise OSError("simulated canonicalization failure")
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    with pytest.raises(PathSafetyError, match="canonicalized"):
        paths.canonicalize_root(root, root_id="root", scope=RootScope.PROJECT)


def test_canonicalize_root_rejects_metadata_errors_and_non_directory_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    original_lstat = Path.lstat

    def fail_lstat(self: Path) -> os.stat_result:
        if self == root:
            raise OSError("simulated root metadata failure")
        return original_lstat(self)

    monkeypatch.setattr(Path, "lstat", fail_lstat)
    with pytest.raises(PathSafetyError, match="metadata"):
        paths.canonicalize_root(root, root_id="root", scope=RootScope.PROJECT)

    resolved_file = tmp_path / "resolved-file"
    resolved_file.write_text("not a directory", encoding="utf-8")
    monkeypatch.undo()
    original_resolve = Path.resolve

    def resolve_to_file(self: Path, *, strict: bool = False) -> Path:
        if self == root and strict:
            return resolved_file
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_to_file)
    with pytest.raises(PathSafetyError, match="resolve to a directory"):
        paths.canonicalize_root(root, root_id="root", scope=RootScope.PROJECT)


def test_root_reference_requires_absolute_and_matching_canonical_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    relative_canonical = CapabilityRoot(
        "root", RootScope.PROJECT, str(root), canonical_path="relative"
    )
    with pytest.raises(PathSafetyError, match="canonicalized"):
        paths.canonical_root_key(relative_canonical)
    with pytest.raises(PathSafetyError, match="canonicalized"):
        paths.canonical_root_key("relative")

    external = tmp_path / "external"
    external.mkdir()
    forged = CapabilityRoot("root", RootScope.PROJECT, str(root), canonical_path=str(external))
    with pytest.raises(PathSafetyError, match="canonicalized"):
        paths.canonical_root_key(forged)

    original_resolve = Path.resolve

    def fail_resolve(self: Path, *, strict: bool = False) -> Path:
        if self == root:
            raise OSError("simulated root comparison failure")
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    with pytest.raises(PathSafetyError, match="canonicalized"):
        paths._root_path(forged)


def test_safe_relative_path_rejects_a_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable")
    with pytest.raises(PathSafetyError, match="escapes"):
        paths.safe_relative_path(root, "link/secret.txt")
    assert paths.safe_relative_path(root, "safe/file.txt") == "safe/file.txt"


def test_validated_base_fails_closed_for_missing_symlink_and_regular_paths(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    assert paths._validated_base(missing, missing_ok=True) is None
    with pytest.raises(PathSafetyError, match="unavailable"):
        paths._validated_base(missing)

    regular = tmp_path / "regular"
    regular.write_text("file", encoding="utf-8")
    with pytest.raises(PathSafetyError, match="directory"):
        paths._validated_base(regular)

    link = tmp_path / "link"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable")
    with pytest.raises(PathSafetyError, match="symlink"):
        paths._validated_base(link)


def test_validated_base_reports_metadata_and_canonicalization_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    original_lstat = Path.lstat

    def fail_lstat(self: Path) -> os.stat_result:
        if self == root:
            raise OSError("simulated base metadata failure")
        return original_lstat(self)

    monkeypatch.setattr(Path, "lstat", fail_lstat)
    with pytest.raises(PathSafetyError, match="metadata"):
        paths._validated_base(root)

    monkeypatch.undo()
    original_resolve = Path.resolve

    def fail_resolve(self: Path, *, strict: bool = False) -> Path:
        if self == root and strict:
            raise OSError("simulated base canonicalization failure")
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    with pytest.raises(PathSafetyError, match="canonicalize"):
        paths._validated_base(root)

    resolved_file = tmp_path / "resolved-file"
    resolved_file.write_text("not a directory", encoding="utf-8")
    monkeypatch.undo()

    def resolve_to_file(self: Path, *, strict: bool = False) -> Path:
        if self == root and strict:
            return resolved_file
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_to_file)
    with pytest.raises(PathSafetyError, match="resolve to a directory"):
        paths._validated_base(root)


def test_directory_flags_require_descriptor_relative_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(paths.os, "supports_dir_fd", frozenset())
    with pytest.raises(PathSafetyError, match="unavailable"):
        paths._directory_flags()


def test_open_directory_rejects_a_non_directory_after_descriptor_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_open = paths.os.open
    original_fstat = paths.os.fstat
    opened: list[int] = []

    def open_directory(*args: object, **kwargs: object) -> int:
        descriptor = original_open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
        opened.append(descriptor)
        return descriptor

    def report_regular(descriptor: int) -> os.stat_result:
        result = original_fstat(descriptor)
        values = list(result)
        values[0] = stat.S_IFREG | (result.st_mode & 0o777)
        return os.stat_result(values)

    monkeypatch.setattr(paths.os, "open", open_directory)
    monkeypatch.setattr(paths.os, "supports_dir_fd", frozenset({open_directory}))
    monkeypatch.setattr(paths.os, "fstat", report_regular)
    with pytest.raises(PathSafetyError, match="only directories"):
        paths._open_directory(tmp_path)

    assert opened
    with pytest.raises(OSError):
        original_fstat(opened[0])


def test_open_directory_translates_os_error_and_closes_non_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        paths._open_directory(missing)

    regular = tmp_path / "regular"
    regular.write_text("file", encoding="utf-8")
    with pytest.raises(PathSafetyError, match="opened safely"):
        paths._open_directory(regular)

    original_open = paths.os.open

    def fail_open(*args: object, **kwargs: object) -> int:
        raise OSError("simulated directory open failure")

    monkeypatch.setattr(paths.os, "open", fail_open)
    monkeypatch.setattr(paths.os, "supports_dir_fd", frozenset({fail_open}))
    with pytest.raises(PathSafetyError, match="opened safely"):
        paths._open_directory(tmp_path)
    monkeypatch.setattr(paths.os, "open", original_open)


def test_read_bounded_file_rejects_invalid_bound_directory_and_oversize(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    nested = root / "nested"
    nested.mkdir()
    (root / "large.txt").write_text("0123456789", encoding="utf-8")

    for bound in (0, False, "10"):
        with pytest.raises(PathSafetyError, match="positive"):
            paths.read_bounded_file(root, "large.txt", max_bytes=bound)  # type: ignore[arg-type]
    with pytest.raises(PathSafetyError, match="regular"):
        paths.read_bounded_file(root, "nested", max_bytes=100)
    with pytest.raises(PathSafetyError, match="bound"):
        paths.read_bounded_file(root, "large.txt", max_bytes=3)


def test_read_and_metadata_translate_open_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "file.txt").write_text("safe", encoding="utf-8")

    def fail_relative(*args: object, **kwargs: object) -> int:
        raise OSError("simulated relative open failure")

    monkeypatch.setattr(paths, "_open_relative", fail_relative)
    with pytest.raises(PathSafetyError, match="cannot be read"):
        paths.read_bounded_file(root, "file.txt", max_bytes=100)
    with pytest.raises(PathSafetyError, match="metadata"):
        paths.bounded_file_metadata(root, "file.txt")


def test_open_relative_without_identity_check_and_missing_leaf_are_safe(tmp_path: Path) -> None:
    root = tmp_path / "root"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (nested / "file.txt").write_text("safe", encoding="utf-8")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)

    descriptor = paths._open_relative(
        root, ("nested", "file.txt"), flags=flags, expected_base_identity=None
    )
    try:
        assert os.read(descriptor, 100) == b"safe"
    finally:
        os.close(descriptor)

    with pytest.raises(FileNotFoundError):
        paths._open_relative(root, ("nested", "missing.txt"), flags=flags)

    with pytest.raises(PathSafetyError, match="changed during safe open"):
        paths._open_relative(
            root,
            ("nested", "file.txt"),
            flags=flags,
            expected_base_identity=(0, 0),
        )


def test_open_relative_translates_leaf_os_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "file.txt").write_text("safe", encoding="utf-8")
    original_open = paths.os.open

    def fail_leaf(value: object, flags: int, *args: object, **kwargs: object) -> int:
        if str(value) == "file.txt" and kwargs.get("dir_fd") is not None:
            raise OSError("simulated leaf open failure")
        return original_open(value, flags, *args, **kwargs)

    monkeypatch.setattr(paths.os, "open", fail_leaf)
    monkeypatch.setattr(paths.os, "supports_dir_fd", frozenset({fail_leaf}))
    with pytest.raises(PathSafetyError, match="path cannot be opened safely"):
        paths._open_relative(
            root,
            ("file.txt",),
            flags=os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )


def test_bounded_file_metadata_rejects_missing_nonregular_and_hardlink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(PathSafetyError, match="unavailable"):
        paths.bounded_file_metadata(root, "missing.txt")

    nested = root / "nested"
    nested.mkdir()
    with pytest.raises(PathSafetyError, match="regular"):
        paths.bounded_file_metadata(root, "nested")

    source = tmp_path / "outside.txt"
    source.write_text("private", encoding="utf-8")
    alias = root / "README.md"
    try:
        alias.hardlink_to(source)
    except OSError:
        pytest.skip("hardlinks are unavailable")
    with pytest.raises(PathSafetyError, match="hard link"):
        paths.bounded_file_metadata(root, "README.md")


def test_bounded_walk_reports_missing_scan_and_entry_stat_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing"
    result = paths.bounded_walk(missing, Phase3Limits())
    assert result.files == ()
    assert result.errors == ("root is unavailable",)

    root = tmp_path / "root"
    root.mkdir()
    original_scandir = paths.os.scandir

    def fail_scan(_fd: int) -> object:
        raise OSError("simulated scan failure")

    monkeypatch.setattr(paths.os, "scandir", fail_scan)
    result = paths.bounded_walk(root, Phase3Limits())
    assert result.files == ()
    assert result.errors and "OSError" in result.errors[0]
    monkeypatch.setattr(paths.os, "scandir", original_scandir)

    class BrokenEntry:
        name = "broken.txt"

        def stat(self, *, follow_symlinks: bool = False) -> os.stat_result:
            raise OSError("simulated entry stat failure")

    class FakeScan:
        def __enter__(self) -> list[BrokenEntry]:
            return [BrokenEntry()]

        def __exit__(self, *_args: object) -> bool:
            return False

    monkeypatch.setattr(paths.os, "scandir", lambda _fd: FakeScan())
    result = paths.bounded_walk(root, Phase3Limits())
    assert result.files == ()
    assert result.errors == ("broken.txt: OSError",)


def test_bounded_walk_handles_case_collision_with_a_nonregular_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    regular = root / "README.md"
    regular.write_text("readme", encoding="utf-8")
    regular_stat = regular.stat()
    nonregular_values = list(regular_stat)
    nonregular_values[0] = stat.S_IFIFO | (regular_stat.st_mode & 0o777)

    class Entry:
        def __init__(self, name: str, metadata: os.stat_result) -> None:
            self.name = name
            self.metadata = metadata

        def stat(self, *, follow_symlinks: bool = False) -> os.stat_result:
            return self.metadata

    class Scan:
        def __enter__(self) -> list[Entry]:
            return [
                Entry("README.md", regular_stat),
                Entry("readme.md", os.stat_result(nonregular_values)),
            ]

        def __exit__(self, *_args: object) -> bool:
            return False

    monkeypatch.setattr(paths.os, "scandir", lambda _fd: Scan())
    result = paths.bounded_walk(root, Phase3Limits())
    assert result.files == ("README.md",)
    assert result.unsafe_paths == ("readme.md",)


def test_bounded_walk_preserves_original_on_regular_case_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    regular = root / "README.md"
    regular.write_text("readme", encoding="utf-8")
    metadata = regular.stat()

    class Entry:
        def __init__(self, name: str) -> None:
            self.name = name

        def stat(self, *, follow_symlinks: bool = False) -> os.stat_result:
            return metadata

    class Scan:
        def __enter__(self) -> list[Entry]:
            return [Entry("README.md"), Entry("readme.md")]

        def __exit__(self, *_args: object) -> bool:
            return False

    monkeypatch.setattr(paths.os, "scandir", lambda _fd: Scan())
    result = paths.bounded_walk(root, Phase3Limits())
    assert result.files == ("README.md",)
    assert result.unsafe_paths == ("readme.md", "README.md")


def test_bounded_walk_does_not_duplicate_an_already_reported_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    first = root / "A.txt"
    first.write_text("first", encoding="utf-8")
    third = root / "b.txt"
    third.write_text("third", encoding="utf-8")
    metadata = first.stat()
    descriptors: dict[str, int] = {}
    original_open = paths.os.open
    original_fstat = paths.os.fstat

    class Entry:
        def __init__(self, name: str) -> None:
            self.name = name

        def stat(self, *, follow_symlinks: bool = False) -> os.stat_result:
            return metadata

    class Scan:
        def __enter__(self) -> list[Entry]:
            return [Entry("A.txt"), Entry("a.txt"), Entry("b.txt")]

        def __exit__(self, *_args: object) -> bool:
            return False

    def remember_open(value: object, flags: int, *args: object, **kwargs: object) -> int:
        descriptor = original_open(value, flags, *args, **kwargs)
        if kwargs.get("dir_fd") is not None and str(value) in {"A.txt", "b.txt"}:
            descriptors[str(value)] = descriptor
        return descriptor

    def alias_third(descriptor: int) -> os.stat_result:
        if descriptor == descriptors.get("b.txt"):
            return metadata
        return original_fstat(descriptor)

    monkeypatch.setattr(paths.os, "scandir", lambda _fd: Scan())
    monkeypatch.setattr(paths.os, "open", remember_open)
    monkeypatch.setattr(paths.os, "supports_dir_fd", frozenset({remember_open}))
    monkeypatch.setattr(paths.os, "fstat", alias_third)
    result = paths.bounded_walk(root, Phase3Limits())
    assert result.files == ("A.txt",)
    assert result.unsafe_paths == ("a.txt", "A.txt", "b.txt")


def test_bounded_walk_reports_root_open_race_as_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    def root_disappeared(value: str | Path, *, parent_fd: int | None = None) -> int:
        if parent_fd is None:
            raise FileNotFoundError(str(value))
        raise AssertionError("no child should be opened after root disappears")

    monkeypatch.setattr(paths, "_open_directory", root_disappeared)
    result = paths.bounded_walk(root, Phase3Limits())
    assert result.files == ()
    assert result.errors == ("root is unavailable",)


def test_bounded_walk_marks_a_file_unsafe_when_post_open_fstat_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "file.txt").write_text("safe", encoding="utf-8")
    original_open = paths.os.open
    original_fstat = paths.os.fstat
    file_descriptor: int | None = None

    def remember_open(value: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal file_descriptor
        descriptor = original_open(value, flags, *args, **kwargs)
        if kwargs.get("dir_fd") is not None and str(value) == "file.txt":
            file_descriptor = descriptor
        return descriptor

    def fail_file_fstat(descriptor: int) -> os.stat_result:
        if file_descriptor is not None and descriptor == file_descriptor:
            raise OSError("simulated post-open fstat failure")
        return original_fstat(descriptor)

    monkeypatch.setattr(paths.os, "open", remember_open)
    monkeypatch.setattr(paths.os, "supports_dir_fd", frozenset({remember_open}))
    monkeypatch.setattr(paths.os, "fstat", fail_file_fstat)
    result = paths.bounded_walk(root, Phase3Limits())
    assert result.files == ()
    assert result.unsafe_paths == ("file.txt",)


def test_bounded_walk_closes_queued_directories_after_bound_failure(tmp_path: Path) -> None:
    root = tmp_path / "root"
    nested = root / "zdir" / "a_nested"
    nested.mkdir(parents=True)
    (root / "a.txt").write_text("a", encoding="utf-8")
    (root / "zdir" / "z_file.txt").write_text("z", encoding="utf-8")
    with pytest.raises(PathSafetyError, match="file count"):
        paths.bounded_walk(
            root,
            Phase3Limits(max_total_files=1, max_total_bytes=100),
        )


def test_bounded_walk_distinguishes_child_open_failures_and_nonregular_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    child = root / "child"
    child.mkdir()
    (root / "fifo").unlink(missing_ok=True)
    try:
        os.mkfifo(root / "fifo")
    except (AttributeError, OSError):
        pytest.skip("FIFO fixtures are unavailable")

    original_open_directory = paths._open_directory

    def missing_child(value: str | Path, *, parent_fd: int | None = None) -> int:
        if parent_fd is not None and str(value) == "child":
            raise FileNotFoundError(str(value))
        return original_open_directory(value, parent_fd=parent_fd)

    monkeypatch.setattr(paths, "_open_directory", missing_child)
    result = paths.bounded_walk(root, Phase3Limits())
    assert "child: FileNotFoundError" in result.errors
    assert "fifo: non-regular entry" in result.errors


def test_bounded_walk_reports_child_safety_error_and_file_open_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    child = root / "child"
    child.mkdir()
    (root / "file.txt").write_text("safe", encoding="utf-8")
    original_open_directory = paths._open_directory

    def unsafe_child(value: str | Path, *, parent_fd: int | None = None) -> int:
        if parent_fd is not None and str(value) == "child":
            raise PathSafetyError("simulated child safety failure")
        return original_open_directory(value, parent_fd=parent_fd)

    monkeypatch.setattr(paths, "_open_directory", unsafe_child)
    original_open = paths.os.open

    def fail_file_open(value: object, flags: int, *args: object, **kwargs: object) -> int:
        if str(value) == "file.txt" and kwargs.get("dir_fd") is not None:
            raise OSError("simulated file open failure")
        return original_open(value, flags, *args, **kwargs)

    monkeypatch.setattr(paths.os, "open", fail_file_open)
    monkeypatch.setattr(paths.os, "supports_dir_fd", frozenset({fail_file_open}))
    result = paths.bounded_walk(root, Phase3Limits())
    assert result.unsafe_paths == ("child", "file.txt")


def test_bounded_walk_enforces_file_count_and_duplicate_open_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("a", encoding="utf-8")
    (root / "b.txt").write_text("b", encoding="utf-8")
    with pytest.raises(PathSafetyError, match="file count"):
        paths.bounded_walk(
            root,
            Phase3Limits(max_total_files=1, max_total_bytes=100),
        )

    original_open = paths.os.open
    original_fstat = paths.os.fstat
    file_descriptors: dict[str, int] = {}
    first_metadata: os.stat_result | None = None

    def remember_open(value: object, flags: int, *args: object, **kwargs: object) -> int:
        descriptor = original_open(value, flags, *args, **kwargs)
        if kwargs.get("dir_fd") is not None and str(value) in {"a.txt", "b.txt"}:
            file_descriptors[str(value)] = descriptor
        return descriptor

    def alias_second(descriptor: int) -> os.stat_result:
        nonlocal first_metadata
        result = original_fstat(descriptor)
        if descriptor == file_descriptors.get("b.txt") and first_metadata is not None:
            return first_metadata
        if descriptor == file_descriptors.get("a.txt") and first_metadata is None:
            first_metadata = result
        return result

    monkeypatch.setattr(paths.os, "open", remember_open)
    monkeypatch.setattr(paths.os, "supports_dir_fd", frozenset({remember_open}))
    monkeypatch.setattr(paths.os, "fstat", alias_second)
    result = paths.bounded_walk(root, Phase3Limits(max_total_files=10, max_total_bytes=100))
    assert result.files == ("a.txt",)
    assert result.unsafe_paths == ("b.txt", "a.txt")


def test_bounded_walk_rejects_post_open_nonregular_and_repeated_directory_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    child = root / "child"
    child.mkdir()
    (root / "file.txt").write_text("safe", encoding="utf-8")
    original_open = paths.os.open
    original_fstat = paths.os.fstat
    file_descriptor: int | None = None
    child_descriptor: int | None = None
    root_metadata: os.stat_result | None = None

    def remember_open(value: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal child_descriptor, file_descriptor
        descriptor = original_open(value, flags, *args, **kwargs)
        if kwargs.get("dir_fd") is not None and str(value) == "file.txt":
            file_descriptor = descriptor
        if kwargs.get("dir_fd") is not None and str(value) == "child":
            child_descriptor = descriptor
        return descriptor

    def alter_fstat(descriptor: int) -> os.stat_result:
        nonlocal root_metadata
        result = original_fstat(descriptor)
        if root_metadata is None and descriptor not in {file_descriptor, child_descriptor}:
            root_metadata = result
        if descriptor == file_descriptor:
            values = list(result)
            values[0] = stat.S_IFDIR | (result.st_mode & 0o777)
            return os.stat_result(values)
        if descriptor == child_descriptor and root_metadata is not None:
            return root_metadata
        return result

    monkeypatch.setattr(paths.os, "open", remember_open)
    monkeypatch.setattr(paths.os, "supports_dir_fd", frozenset({remember_open}))
    monkeypatch.setattr(paths.os, "fstat", alter_fstat)
    result = paths.bounded_walk(root, Phase3Limits(max_total_files=10, max_total_bytes=100))
    assert "file.txt: non-regular entry" in result.errors
    assert "child" in result.unsafe_paths


def test_redact_path_uses_explicit_root_token(tmp_path: Path) -> None:
    external = tmp_path / "outside" / "secret.txt"
    external.parent.mkdir()
    external.write_text("secret", encoding="utf-8")
    redacted = paths.redact_path(external, root_id="PROJECT")
    assert redacted.startswith("$PROJECT/")
    assert "secret.txt" not in redacted


def test_redact_path_preserves_only_declared_root_labels(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    workspace.mkdir()
    home.mkdir()
    workspace_file = workspace / "src" / "main.py"
    workspace_file.parent.mkdir()
    workspace_file.write_text("pass", encoding="utf-8")
    home_file = home / "config"
    home_file.write_text("safe", encoding="utf-8")
    external = tmp_path / "external"
    external.write_text("outside", encoding="utf-8")

    assert paths.redact_path(workspace_file, workspace_root=workspace) == "$WORKSPACE/src/main.py"
    assert paths.redact_path(workspace, workspace_root=workspace) == "$WORKSPACE"
    assert paths.redact_path(home_file, workspace_root=workspace, home_dir=home) == "$HOME/config"
    assert paths.redact_path(external) != str(external)
    assert paths.redact_path("\x00invalid") == "$REDACTED_PATH"


def test_metadata_surface_and_digest_file_preserve_boundary_contract(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "scripts").mkdir()
    (root / "scripts" / "guide.md").write_text("guide", encoding="utf-8")
    (root / "README.md").write_text("readme", encoding="utf-8")

    assert paths.is_metadata_only_surface("scripts/guide.md") is True
    assert paths.is_metadata_only_surface("README.md") is False
    payload, digest = paths.digest_file(root, "README.md", max_bytes=100)
    assert payload == b"readme"
    assert digest == paths.digest_bytes(payload)
