from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest

import harness_kernel.boundary as boundary_module
from harness_kernel import phase3_paths as phase3_paths_module
from harness_kernel import phase4_execution as phase4_execution_module
from harness_kernel import phase4_host as phase4_host_module
from harness_kernel.boundary import BoundaryError, ProjectBoundary
from harness_kernel.persistence import RunStore
from harness_kernel.phase3_models import Phase3Limits
from harness_kernel.phase3_paths import PathSafetyError
from harness_kernel.phase4_execution import ReplayLedgerError
from harness_kernel.phase4_host import HostProtocolError, _SubprocessClient
from harness_kernel.providers import ProviderRegistry


def test_transport_authentication_copy_is_projected_into_ephemeral_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_home = tmp_path / "source-codex-home"
    runtime_home = tmp_path / "runtime-codex-home"
    source_home.mkdir()
    runtime_home.mkdir()
    auth = source_home / "auth.json"
    auth.write_bytes(b'{"token":"brokered"}\n')
    monkeypatch.setenv("CODEX_HOME", str(source_home))

    _SubprocessClient._copy_host_transport_authentication(runtime_home)

    copied = runtime_home / "auth.json"
    assert copied.read_bytes() == auth.read_bytes()
    assert copied.stat().st_mode & 0o777 == 0o600


def test_transport_authentication_rejects_symlink_and_relative_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside-auth.json"
    outside.write_text("secret", encoding="utf-8")
    source_home = tmp_path / "source-codex-home"
    source_home.mkdir()
    (source_home / "auth.json").symlink_to(outside)
    runtime_home = tmp_path / "runtime-codex-home"
    runtime_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(source_home))

    _SubprocessClient._copy_host_transport_authentication(runtime_home)
    assert not (runtime_home / "auth.json").exists()


def test_transport_authentication_rejects_nonregular_and_changed_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_home = tmp_path / "source-codex-home"
    runtime_home = tmp_path / "runtime-codex-home"
    source_home.mkdir()
    runtime_home.mkdir()
    (source_home / "auth.json").mkdir()
    monkeypatch.setenv("CODEX_HOME", str(source_home))

    _SubprocessClient._copy_host_transport_authentication(runtime_home)
    assert not (runtime_home / "auth.json").exists()

    auth = source_home / "auth.json"
    auth.rmdir()
    auth.write_bytes(b"brokered-auth")
    original_fstat = phase4_host_module.os.fstat
    calls = 0

    def changed_after_read(fd: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        result = original_fstat(fd)
        if calls == 3:
            values = list(result)
            values[8] += 1
            return os.stat_result(values)
        return result

    monkeypatch.setattr(phase4_host_module.os, "fstat", changed_after_read)

    with pytest.raises(HostProtocolError, match="changed during safe copy"):
        _SubprocessClient._copy_host_transport_authentication(runtime_home)
    assert not (runtime_home / "auth.json").exists()


def test_transport_authentication_fsync_failure_removes_partial_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_home = tmp_path / "source-codex-home"
    runtime_home = tmp_path / "runtime-codex-home"
    source_home.mkdir()
    runtime_home.mkdir()
    (source_home / "auth.json").write_bytes(b"brokered-auth")
    monkeypatch.setenv("CODEX_HOME", str(source_home))

    def fail_fsync(_fd: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(phase4_host_module.os, "fsync", fail_fsync)

    with pytest.raises(HostProtocolError, match="cannot be copied safely"):
        _SubprocessClient._copy_host_transport_authentication(runtime_home)
    assert not (runtime_home / "auth.json").exists()

    monkeypatch.setenv("CODEX_HOME", "relative-codex-home")
    _SubprocessClient._copy_host_transport_authentication(runtime_home)
    assert not (runtime_home / "auth.json").exists()


def test_transport_authentication_source_open_error_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_home = tmp_path / "source-codex-home"
    runtime_home = tmp_path / "runtime-codex-home"
    source_home.mkdir()
    runtime_home.mkdir()
    (source_home / "auth.json").write_bytes(b"brokered-auth")
    monkeypatch.setenv("CODEX_HOME", str(source_home))
    original_open = phase4_host_module.os.open

    def fail_source(path: object, *args: object, **kwargs: object) -> int:
        if Path(path) == source_home:
            raise OSError("simulated source open failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(phase4_host_module.os, "open", fail_source)

    _SubprocessClient._copy_host_transport_authentication(runtime_home)

    assert not (runtime_home / "auth.json").exists()


def test_transport_authentication_destination_open_error_is_typed_and_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_home = tmp_path / "source-codex-home"
    runtime_home = tmp_path / "runtime-codex-home"
    source_home.mkdir()
    runtime_home.mkdir()
    (source_home / "auth.json").write_bytes(b"brokered-auth")
    monkeypatch.setenv("CODEX_HOME", str(source_home))
    original_open = phase4_host_module.os.open
    destination = runtime_home / "auth.json"

    def fail_destination(path: object, *args: object, **kwargs: object) -> int:
        if Path(path) == destination:
            raise OSError("simulated destination open failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(phase4_host_module.os, "open", fail_destination)

    with pytest.raises(HostProtocolError, match="cannot be copied safely"):
        _SubprocessClient._copy_host_transport_authentication(runtime_home)
    assert not destination.exists()


def test_transport_authentication_zero_byte_write_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_home = tmp_path / "source-codex-home"
    runtime_home = tmp_path / "runtime-codex-home"
    source_home.mkdir()
    runtime_home.mkdir()
    (source_home / "auth.json").write_bytes(b"brokered-auth")
    monkeypatch.setenv("CODEX_HOME", str(source_home))
    original_write = phase4_host_module.os.write
    calls = 0

    def zero_once_then_write(fd: int, payload: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return 0
        return original_write(fd, payload)

    monkeypatch.setattr(phase4_host_module.os, "write", zero_once_then_write)

    with pytest.raises(HostProtocolError, match="cannot be copied safely"):
        _SubprocessClient._copy_host_transport_authentication(runtime_home)
    assert not (runtime_home / "auth.json").exists()


def test_bounded_walk_fails_closed_when_file_fstat_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "safe.txt").write_text("safe", encoding="utf-8")
    original_open = phase3_paths_module.os.open
    original_fstat = phase3_paths_module.os.fstat
    opened_file_fd: int | None = None

    def remember_file_open(path: str, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal opened_file_fd
        descriptor = original_open(path, flags, *args, **kwargs)
        if path == "safe.txt" and kwargs.get("dir_fd") is not None:
            opened_file_fd = descriptor
        return descriptor

    def fail_file_fstat(descriptor: int) -> os.stat_result:
        if opened_file_fd is not None and descriptor == opened_file_fd:
            raise OSError("simulated fstat failure")
        return original_fstat(descriptor)

    monkeypatch.setattr(phase3_paths_module.os, "open", remember_file_open)
    monkeypatch.setattr(phase3_paths_module.os, "fstat", fail_file_fstat)
    monkeypatch.setattr(
        phase3_paths_module,
        "_directory_flags",
        lambda: os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
    )

    result = phase3_paths_module.bounded_walk(
        root,
        Phase3Limits(max_depth=4, max_total_files=20, max_total_bytes=10_000),
    )

    assert result.files == ()
    assert result.unsafe_paths == ("safe.txt",)
    assert result.errors == ()


def test_secure_filesystem_guards_reject_unavailable_platform_and_non_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with monkeypatch.context() as context:
        context.delattr(phase3_paths_module.os, "O_NOFOLLOW", raising=False)
        with pytest.raises(PathSafetyError, match="unavailable"):
            phase3_paths_module._directory_flags()

    regular = tmp_path / "regular"
    regular.write_text("not a directory", encoding="utf-8")
    with pytest.raises(PathSafetyError, match="cannot be opened safely"):
        phase3_paths_module._open_directory(regular)


def test_secure_relative_read_rejects_a_changed_base_identity(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "safe.txt").write_text("safe", encoding="utf-8")

    with pytest.raises(PathSafetyError, match="changed during safe open"):
        phase3_paths_module.read_bounded_file(
            root,
            "safe.txt",
            max_bytes=100,
            expected_base_identity=(0, 0),
        )


def test_atomic_create_preserves_first_conflicting_record_under_race(
    tmp_path: Path,
) -> None:
    boundary = ProjectBoundary(tmp_path)
    relative = ".harness/state/runs/RUN-P7-2-RACE.json"
    barrier = Barrier(2)
    records = (
        {"run_id": "RUN-P7-2-RACE", "status": "FIRST"},
        {"run_id": "RUN-P7-2-RACE", "status": "SECOND"},
    )

    def create(record: dict[str, str]) -> str:
        barrier.wait()
        try:
            boundary.atomic_create_json(relative, record)
        except BoundaryError:
            return "conflict"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(create, records))

    assert sorted(outcomes) == ["conflict", "created"]
    assert boundary.read_json(relative) in records


def test_run_store_does_not_overwrite_conflicting_first_writer_under_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary = ProjectBoundary(tmp_path)
    store = RunStore(boundary)
    run_id = "RUN-P7-2-STORE-RACE"
    records = (
        {"run_id": run_id, "status": "FIRST"},
        {"run_id": run_id, "status": "SECOND"},
    )
    barrier = Barrier(2)
    gate_calls = 0
    original_resolve = ProjectBoundary.resolve

    def gate_initial_existence_check(
        self: ProjectBoundary, relative: str, *, allow_missing: bool = False
    ) -> Path:
        nonlocal gate_calls
        result = original_resolve(self, relative, allow_missing=allow_missing)
        if relative == f".harness/state/runs/{run_id}.json" and allow_missing:
            gate_calls += 1
            if gate_calls <= 2:
                barrier.wait()
        return result

    monkeypatch.setattr(ProjectBoundary, "resolve", gate_initial_existence_check)

    def write(record: dict[str, str]) -> str:
        try:
            store.write_record(run_id, record)
        except BoundaryError:
            return "conflict"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(write, records))

    assert sorted(outcomes) == ["conflict", "created"]
    assert store.load_record(run_id) in records


def test_run_store_does_not_treat_directory_fsync_failure_as_idempotent_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boundary = ProjectBoundary(tmp_path)
    store = RunStore(boundary)
    cases = (
        (".harness/state/runs/RUN-FSYNC-JSON.json", {"run_id": "RUN-FSYNC-JSON"}, "json"),
        (".harness/state/runs/RUN-FSYNC-BYTES.json", b"payload", "bytes"),
    )
    real_fsync = boundary_module.os.fsync

    for relative, value, kind in cases:
        calls = 0

        def fail_directory_fsync(file_descriptor: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated directory durability failure")
            real_fsync(file_descriptor)

        monkeypatch.setattr(boundary_module.os, "fsync", fail_directory_fsync)
        with pytest.raises(BoundaryError, match="created atomically"):
            if kind == "json":
                store._write_once_json(  # noqa: SLF001
                    relative,
                    value,
                    corrupt_message="corrupt",
                    collision_message="collision",
                )
            else:
                store._write_once_bytes(  # noqa: SLF001
                    relative,
                    value,
                    corrupt_message="corrupt",
                    collision_message="collision",
                )
        assert boundary.resolve(relative).is_file()


def test_ledger_locking_unavailable_is_a_typed_fail_closed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(phase4_execution_module, "fcntl", None)

    with (
        pytest.raises(ReplayLedgerError, match="unavailable"),
        phase4_execution_module._ledger_lock(
            tmp_path / ".harness" / "phase4" / "invocation-ledger.json",
            workspace=tmp_path,
        ),
    ):
        raise AssertionError("unavailable locking must not enter the critical section")


def test_legacy_ledger_is_upgraded_atomically_and_entries_are_preserved(tmp_path: Path) -> None:
    ledger = tmp_path / ".harness" / "phase4" / "invocation-ledger.json"
    ledger.parent.mkdir(parents=True)
    parent_metadata = ledger.parent.stat()
    anchor_name = phase4_execution_module._ledger_anchor_name(ledger, tmp_path)
    (tmp_path / anchor_name).write_text(
        phase4_execution_module.json.dumps(
            {
                "schema_version": phase4_execution_module._LEDGER_ANCHOR_SCHEMA,
                "parent_dev": parent_metadata.st_dev,
                "parent_ino": parent_metadata.st_ino,
                "ledger_initialized": False,
                "ledger_token": None,
            }
        ),
        encoding="utf-8",
    )
    entries = {
        "INV-LEGACY": {
            "idempotency_key": "IDEM-LEGACY",
            "request_digest": "sha256:" + "1" * 64,
            "status": "SUCCESS",
        }
    }
    ledger.write_text(
        phase4_execution_module.json.dumps({"schema_version": "P4-LEDGER-1", "entries": entries}),
        encoding="utf-8",
    )

    with phase4_execution_module._ledger_lock(ledger, workspace=tmp_path):
        pass

    upgraded = phase4_execution_module.json.loads(ledger.read_text(encoding="utf-8"))
    anchor = phase4_execution_module.json.loads(
        (tmp_path / anchor_name).read_text(encoding="utf-8")
    )
    assert upgraded["entries"] == entries
    assert phase4_execution_module._is_ledger_token(upgraded["ledger_token"])
    assert upgraded["ledger_token"] == anchor["ledger_token"]
    assert anchor["ledger_initialized"] is True


def test_cancel_without_active_session_is_explicitly_not_active() -> None:
    adapter = phase4_host_module.CodexAppServerAdapter(transport_factory=lambda: None)  # type: ignore[arg-type]
    request = SimpleNamespace(invocation_id="INV-P7-2-INACTIVE")

    assert adapter.cancel_invocation(request) == "CANCELLATION_REQUIRES_ACTIVE_SESSION"  # type: ignore[arg-type]


def test_pinned_executable_digest_is_bound_to_the_exact_regular_file(tmp_path: Path) -> None:
    executable = tmp_path / "host"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    digest = "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest()

    phase4_host_module._verify_pinned_files(((str(executable), digest),))
    executable.write_text("#!/bin/sh\necho changed\n", encoding="utf-8")

    with pytest.raises(HostProtocolError, match="fingerprint"):
        phase4_host_module._verify_pinned_files(((str(executable), digest),))


def test_provider_registry_rejects_side_effecting_provider_types() -> None:
    class SideEffectingProvider:
        @property
        def descriptor(self) -> object:
            raise AssertionError("descriptor must not be inspected before type admission")

        def execute(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("unadmitted provider must never execute")

    with pytest.raises(ValueError, match="built-in deterministic fixture"):
        ProviderRegistry().register(SideEffectingProvider())  # type: ignore[arg-type]


def test_project_boundary_rejects_nonregular_and_oversized_atomic_byte_inputs(
    tmp_path: Path,
) -> None:
    boundary = ProjectBoundary(tmp_path)
    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(BoundaryError, match="regular file"):
        boundary.read_bytes("directory")
    with pytest.raises(BoundaryError, match="require bytes"):
        boundary.atomic_create_bytes("wrong-type", "text")  # type: ignore[arg-type]
    bounded_root = tmp_path / "bounded"
    bounded_root.mkdir()
    bounded = ProjectBoundary(bounded_root, max_file_bytes=1)
    with pytest.raises(BoundaryError, match="size limit"):
        bounded.atomic_create_bytes("too-large", b"12")
