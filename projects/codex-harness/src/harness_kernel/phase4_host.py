"""Supported Codex app-server boundary for one explicitly approved pilot."""

from __future__ import annotations

import hashlib
import json
import os
import select
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import suppress
from pathlib import Path
from threading import Event, Lock
from typing import Protocol

from .phase4_models import (
    CapabilityInvocationRequest,
    ExecutionMode,
    FactStatus,
    HostInvocationResult,
    HostLoadObservation,
    HostPreparation,
    InvocationResultStatus,
    Phase4Budget,
    Phase4Event,
    ProtocolMessageObservation,
)


class HostProtocolError(RuntimeError):
    """Raised when the official host returns an invalid or incomplete message."""


class HostTimeoutError(TimeoutError):
    """Raised when the bounded app-server protocol exceeds its time budget."""


HostBinding = tuple[
    tuple[str, ...],
    str,
    str,
    tuple[tuple[str, str], ...],
    str | None,
    str | None,
]

_MAX_PROTOCOL_JSON_NESTING = 64
_SAFE_HOST_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def _json_nesting_exceeds(payload: bytes, *, max_depth: int) -> bool:
    """Bound structural JSON nesting before handing untrusted bytes to the parser."""

    depth = 0
    escaped = False
    in_string = False
    for byte in payload:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                in_string = False
            continue
        if byte == 34:
            in_string = True
        elif byte in {91, 123}:
            depth += 1
            if depth > max_depth:
                return True
        elif byte in {93, 125}:
            depth = max(0, depth - 1)
    return False


def _reject_non_finite_json(value: str) -> object:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _sha256_fd(fd: int) -> str:
    """Hash an already-open regular file without reopening its pathname."""

    try:
        position = os.lseek(fd, 0, os.SEEK_CUR)
        os.lseek(fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
        os.lseek(fd, position, os.SEEK_SET)
    except OSError as exc:
        raise HostProtocolError("pinned host file cannot be hashed safely") from exc
    return "sha256:" + digest.hexdigest()


def _read_fd_bounded(fd: int, *, max_bytes: int) -> bytes:
    """Read a bounded descriptor while keeping the descriptor identity pinned."""

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(1024 * 1024, max_bytes - total + 1))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_bytes:
            raise HostProtocolError("host authentication file exceeds its bound")
        chunks.append(chunk)


def _open_pinned_files(pinned_files: tuple[tuple[str, str], ...]) -> tuple[int, ...]:
    """Open the exact hashed host files and expose them through stable fd paths."""

    if not hasattr(os, "O_NOFOLLOW") or not Path("/proc/self/fd").is_dir():
        raise HostProtocolError("host executable descriptor execution is unavailable")
    descriptors: list[int] = []
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        for raw_path, expected_digest in pinned_files:
            descriptor = os.open(raw_path, flags)
            descriptors.append(descriptor)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or not metadata.st_mode & (
                stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            ):
                raise HostProtocolError("pinned host file is not an executable regular file")
            if _sha256_fd(descriptor) != expected_digest:
                raise HostProtocolError("pinned host file fingerprint changed")
        return tuple(descriptors)
    except OSError as exc:
        for descriptor in descriptors:
            with suppress(OSError):
                os.close(descriptor)
        raise HostProtocolError("pinned host file cannot be opened safely") from exc
    except HostProtocolError:
        for descriptor in descriptors:
            with suppress(OSError):
                os.close(descriptor)
        raise


class AppServerClient(Protocol):
    def call(
        self,
        method: str,
        params: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]: ...

    def notify(self, method: str, params: dict[str, object]) -> None: ...

    def respond(self, request_id: object, result: dict[str, object]) -> None: ...

    def stream(
        self,
        *,
        timeout_seconds: float,
        cancel_event: Event | None = None,
    ) -> Iterator[dict[str, object]]: ...

    def close(self) -> None: ...


class CapabilityInvocationAdapter(Protocol):
    def prepare_invocation(self, request: CapabilityInvocationRequest) -> HostPreparation: ...

    def validate_invocation(self, request: CapabilityInvocationRequest) -> tuple[str, ...]: ...

    def request_invocation(
        self,
        request: CapabilityInvocationRequest,
        *,
        budget: Phase4Budget,
        cancel_event: Event | None = None,
    ) -> HostInvocationResult: ...

    def observe_invocation(self, result: HostInvocationResult) -> HostInvocationResult: ...

    def cancel_invocation(self, request: CapabilityInvocationRequest) -> str: ...

    def collect_result(self, result: HostInvocationResult) -> HostInvocationResult: ...


class _SubprocessClient:
    """Small JSONL client with fixed process construction and bounded reads."""

    def __init__(
        self,
        *,
        cwd: Path,
        command: tuple[str, ...],
        pinned_files: tuple[tuple[str, str], ...],
        host_executable_path: str,
        host_executable_digest: str,
        host_interpreter_path: str | None = None,
        host_interpreter_digest: str | None = None,
        allow_host_authentication: bool = False,
        max_line_bytes: int = 512 * 1024,
    ) -> None:
        self.cwd = cwd
        self.command = command
        self.pinned_files = pinned_files
        self.host_executable_path = host_executable_path
        self.host_executable_digest = host_executable_digest
        self.host_interpreter_path = host_interpreter_path
        self.host_interpreter_digest = host_interpreter_digest
        self.allow_host_authentication = allow_host_authentication
        self.max_line_bytes = max_line_bytes
        self._next_id = 1
        self._protocol_message_count = 0
        self._mcp_event_count = 0
        self._approval_request_count = 0
        self._protocol_observations: list[ProtocolMessageObservation] = []
        self._stdout_buffer = b""
        _verify_pinned_files(pinned_files)
        self._runtime_directory = tempfile.TemporaryDirectory(prefix="phase4-codex-runtime-")
        runtime_root = Path(self._runtime_directory.name)
        runtime_home = runtime_root / "home"
        runtime_codex_home = runtime_root / "codex-home"
        runtime_home.mkdir()
        runtime_codex_home.mkdir()
        pinned_descriptors: tuple[int, ...] = ()
        try:
            if self.allow_host_authentication:
                self._copy_host_transport_authentication(runtime_codex_home)
            if any(raw_path not in command for raw_path, _ in pinned_files):
                raise HostProtocolError("pinned host file is not present in the process command")
            pinned_descriptors = _open_pinned_files(pinned_files)
            descriptor_paths = {
                raw_path: f"/proc/self/fd/{descriptor}"
                for (raw_path, _), descriptor in zip(pinned_files, pinned_descriptors, strict=True)
            }
            process_command = tuple(descriptor_paths.get(item, item) for item in command)
            self._process = subprocess.Popen(
                list(process_command),
                cwd=str(cwd),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=False,
                bufsize=0,
                close_fds=True,
                pass_fds=pinned_descriptors,
                start_new_session=True,
                env=self._safe_environment(
                    runtime_home=runtime_home,
                    runtime_codex_home=runtime_codex_home,
                    runtime_tmp=runtime_root,
                ),
            )
        except Exception:
            self._runtime_directory.cleanup()
            raise
        finally:
            for descriptor in pinned_descriptors:
                with suppress(OSError):
                    os.close(descriptor)

    @staticmethod
    def _copy_host_transport_authentication(runtime_codex_home: Path) -> None:
        """Copy only brokered app-server transport auth into the child runtime.

        This is deliberately separate from capability credentials.  A
        capability's ``credential_policy`` never enables this control-plane
        transport path; only the adapter's explicit host-authentication mode
        can do so.
        """

        configured_home = os.environ.get("CODEX_HOME")
        source_home = Path(configured_home) if configured_home else Path.home() / ".codex"
        if not source_home.is_absolute():
            return
        if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            return
        home_fd: int | None = None
        auth_fd: int | None = None
        try:
            source_home = source_home.resolve(strict=True)
            home_fd = os.open(
                source_home,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
        except (FileNotFoundError, OSError):
            return
        try:
            home_metadata = os.fstat(home_fd)
            if not stat.S_ISDIR(home_metadata.st_mode):
                return
            auth_fd = os.open(
                "auth.json",
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=home_fd,
            )
            before = os.fstat(auth_fd)
            if not stat.S_ISREG(before.st_mode):
                return
            content = _read_fd_bounded(auth_fd, max_bytes=4 * 1024 * 1024)
            after = os.fstat(auth_fd)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise HostProtocolError("host authentication file changed during safe copy")
        finally:
            if auth_fd is not None:
                os.close(auth_fd)
            if home_fd is not None:
                os.close(home_fd)
        copied_auth = runtime_codex_home / "auth.json"
        try:
            copied_fd = os.open(
                copied_auth,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o600,
            )
            try:
                offset = 0
                while offset < len(content):
                    offset += os.write(copied_fd, content[offset:])
                os.fsync(copied_fd)
            finally:
                os.close(copied_fd)
        except OSError as exc:
            raise HostProtocolError("host authentication file cannot be copied safely") from exc

    @staticmethod
    def _safe_environment(
        *, runtime_home: Path, runtime_codex_home: Path, runtime_tmp: Path
    ) -> dict[str, str]:
        allowed = (
            "HOME",
            "USER",
            "LOGNAME",
            "LANG",
            "LC_ALL",
            "TERM",
            "TMPDIR",
            "CODEX_HOME",
        )
        result = {key: os.environ[key] for key in allowed if key in os.environ}
        # The host executable and interpreter are passed by descriptor.  A fixed
        # system path prevents secondary helpers from being selected by an
        # attacker-controlled inherited PATH.
        result["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        result["HOME"] = str(runtime_home)
        result["CODEX_HOME"] = str(runtime_codex_home)
        result["TMPDIR"] = str(runtime_tmp)
        result["NO_COLOR"] = "1"
        return result

    def _send(self, payload: Mapping[str, object]) -> None:
        if self._process.stdin is None:
            raise HostProtocolError("app-server stdin is unavailable")
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > self.max_line_bytes:
            raise HostProtocolError("app-server request exceeds the line bound")
        try:
            self._process.stdin.write((encoded + "\n").encode("utf-8"))
            self._process.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise HostProtocolError("app-server stdin is closed") from exc

    def _read(self, timeout_seconds: float) -> dict[str, object]:
        if self._process.stdout is None:
            raise HostProtocolError("app-server stdout is unavailable")
        if timeout_seconds <= 0:
            raise HostTimeoutError("app-server response timed out")
        deadline = time.monotonic() + timeout_seconds
        while b"\n" not in self._stdout_buffer:
            if len(self._stdout_buffer) > self.max_line_bytes:
                raise HostProtocolError("app-server response exceeds the line bound")
            if self._process.poll() is not None:
                raise HostProtocolError("app-server exited before returning a response")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HostTimeoutError("app-server response timed out")
            ready, _, _ = select.select([self._process.stdout], [], [], remaining)
            if not ready:
                raise HostTimeoutError("app-server response timed out")
            try:
                chunk = os.read(self._process.stdout.fileno(), 64 * 1024)
            except OSError as exc:
                raise HostProtocolError("app-server stdout cannot be read") from exc
            if not chunk:
                raise HostProtocolError("app-server closed stdout")
            self._stdout_buffer += chunk
        line, _, self._stdout_buffer = self._stdout_buffer.partition(b"\n")
        if len(line) > self.max_line_bytes:
            raise HostProtocolError("app-server response exceeds the line bound")
        try:
            if _json_nesting_exceeds(line, max_depth=_MAX_PROTOCOL_JSON_NESTING):
                raise HostProtocolError("app-server message exceeds the nesting bound")
            value = json.loads(
                line.decode("utf-8"),
                parse_constant=_reject_non_finite_json,
            )
        except HostProtocolError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise HostProtocolError("app-server returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise HostProtocolError("app-server message must be an object")
        self._protocol_message_count += 1
        if self._protocol_message_count > 4_096:
            raise HostProtocolError("app-server protocol message budget exceeded")
        method = _text(value.get("method"))
        normalized_method = method or None
        if normalized_method is None:
            message_kind = "response"
        elif "id" in value:
            message_kind = "request"
        else:
            message_kind = "notification"
        self._protocol_observations.append(
            ProtocolMessageObservation(
                sequence=self._protocol_message_count - 1,
                method=normalized_method,
                message_kind=message_kind,
                has_id="id" in value,
                has_error="error" in value,
            )
        )
        if method.startswith("mcpServer/"):
            self._mcp_event_count += 1
        if method.endswith("requestApproval"):
            self._approval_request_count += 1
        return value

    def protocol_counts(self) -> tuple[int, int, int]:
        return (
            self._protocol_message_count,
            self._mcp_event_count,
            self._approval_request_count,
        )

    def protocol_observations(self) -> tuple[ProtocolMessageObservation, ...]:
        return tuple(self._protocol_observations)

    def call(
        self,
        method: str,
        params: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        if timeout_seconds <= 0:
            raise HostTimeoutError("app-server response timed out")
        request_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout_seconds
        while True:
            message = self._read(deadline - time.monotonic())
            if message.get("id") == request_id:
                if "error" in message:
                    raise HostProtocolError(f"app-server rejected {method}")
                return message
            message_method = _text(message.get("method"))
            if "id" in message and message_method.endswith("requestApproval"):
                self.respond(message["id"], {"decision": "decline"})

    def notify(self, method: str, params: dict[str, object]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def respond(self, request_id: object, result: dict[str, object]) -> None:
        self._send({"jsonrpc": "2.0", "id": request_id, "result": result})

    def stream(
        self,
        *,
        timeout_seconds: float,
        cancel_event: Event | None = None,
    ) -> Iterator[dict[str, object]]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            if cancel_event is not None and cancel_event.is_set():
                yield {"__phase4_cancel_requested__": True}
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HostTimeoutError("app-server stream timed out")
            try:
                yield self._read(min(remaining, 0.25))
            except HostTimeoutError:
                if time.monotonic() >= deadline:
                    raise

    def close(self) -> None:
        process = self._process
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    if process.pid is not None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except OSError:
                            process.kill()
                    with suppress(subprocess.TimeoutExpired):
                        process.wait(timeout=0.25)
        finally:
            self._runtime_directory.cleanup()


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) and value else default


def _integer(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and value >= 0 else default


def _bounded_output(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


_FORBIDDEN_HOST_METHOD_PREFIXES = (
    "item/commandexecution",
    "item/filechange",
    "item/mcptoolcall",
    "item/websearch",
    "item/toolcall",
    "item/network",
    "item/providercall",
    "item/credential",
    "item/subagent",
    "commandexecution",
    "filechange",
    "mcptoolcall",
    "websearch",
    "toolcall",
    "tool/",
    "shell/",
    "network/",
    "provider/",
    "mcp/",
    "mcpserver/",
)
_FORBIDDEN_HOST_ITEM_TYPES = frozenset(
    {
        "commandexecution",
        "filechange",
        "mcptoolcall",
        "websearch",
        "toolcall",
        "customtoolcall",
        "functioncall",
        "computeraction",
        "shell",
        "networkrequest",
        "providercall",
        "credentialaccess",
        "subagentcall",
    }
)


def _sha256_regular_file(path: Path) -> str:
    """Hash one resolved executable without following a mutable target later."""

    try:
        metadata = path.lstat()
    except OSError as exc:
        raise HostProtocolError("host executable cannot be inspected") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise HostProtocolError("host executable is not a regular file")
    if not metadata.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
        raise HostProtocolError("host executable is not executable")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise HostProtocolError("host executable cannot be hashed") from exc
    return "sha256:" + digest.hexdigest()


def _resolve_regular_executable(program: str) -> tuple[Path, str]:
    configured_name = {
        "codex": "CODEX_EXECUTABLE",
        "node": "NODE_EXECUTABLE",
    }.get(program)
    configured = os.environ.get(configured_name) if configured_name is not None else None
    candidate: str | None
    if configured is not None:
        candidate = configured
        if not Path(candidate).is_absolute():
            raise HostProtocolError(f"{configured_name} must be an absolute path")
    else:
        candidate = shutil.which(program, path=_SAFE_HOST_PATH)
    if not candidate:
        raise HostProtocolError(f"host executable {program} is unavailable")
    try:
        path = Path(candidate).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise HostProtocolError(f"host executable {program} cannot be resolved") from exc
    return path, _sha256_regular_file(path)


def _resolve_host_binding() -> HostBinding:
    """Resolve Codex and its Node interpreter to immutable absolute paths and hashes."""

    codex_path, codex_digest = _resolve_regular_executable("codex")
    command_args = (
        "-c",
        "mcp_servers={}",
        "-c",
        "features.apps=false",
        "app-server",
        "--listen",
        "stdio://",
    )
    try:
        with codex_path.open("r", encoding="utf-8") as handle:
            first_line = handle.readline(256).strip()
    except (OSError, UnicodeError) as exc:
        raise HostProtocolError("host executable shebang cannot be inspected") from exc
    pinned_files: list[tuple[str, str]] = [(str(codex_path), codex_digest)]
    command: tuple[str, ...]
    interpreter_path: str | None = None
    interpreter_digest: str | None = None
    if first_line.startswith("#!") and "node" in first_line:
        node_path, node_digest = _resolve_regular_executable("node")
        command = (str(node_path), str(codex_path), *command_args)
        pinned_files.append((str(node_path), node_digest))
        interpreter_path = str(node_path)
        interpreter_digest = node_digest
    else:
        command = (str(codex_path), *command_args)
    return (
        command,
        str(codex_path),
        codex_digest,
        tuple(pinned_files),
        interpreter_path,
        interpreter_digest,
    )


def _verify_pinned_files(pinned_files: tuple[tuple[str, str], ...]) -> None:
    if not pinned_files:
        raise HostProtocolError("host executable pin is missing")
    for raw_path, expected_digest in pinned_files:
        path = Path(raw_path)
        if not path.is_absolute():
            raise HostProtocolError("host executable pin is not absolute")
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise HostProtocolError("host executable pin cannot be resolved") from exc
        if resolved != path:
            raise HostProtocolError("host executable pin changed its resolved path")
        if _sha256_regular_file(path) != expected_digest:
            raise HostProtocolError("host executable fingerprint changed")


class CodexAppServerAdapter:
    """Invoke one named Skill through Codex's official app-server JSON-RPC API."""

    command: tuple[str, ...] = (
        "codex",
        "-c",
        "mcp_servers={}",
        "-c",
        "features.apps=false",
        "app-server",
        "--listen",
        "stdio://",
    )
    _developer_instructions = (
        "This is a Harness-controlled pilot. The Harness policy is authoritative. "
        "Do not use shell, scripts, network, MCP, providers, credentials, subagents, "
        "or tools; do not change files; do not change acceptance criteria; return only "
        "a bounded final response."
    )

    def __init__(
        self,
        *,
        transport_factory: Callable[[], AppServerClient] | None = None,
        host_authentication: bool = False,
    ) -> None:
        if type(host_authentication) is not bool:
            raise ValueError("host_authentication must be boolean")
        self._transport_factory = transport_factory
        self._active_sessions: dict[str, tuple[AppServerClient, str, str]] = {}
        self._active_lock = Lock()
        self._host_binding: HostBinding | None = None
        self._host_binding_error: str | None = None
        # This is control-plane authentication for the official app-server,
        # never a capability credential grant or a model-visible tool.
        self._host_authentication = host_authentication

    def _resolved_host_binding(
        self,
    ) -> HostBinding | None:
        if self._transport_factory is not None:
            return None
        if self._host_binding is None and self._host_binding_error is None:
            try:
                self._host_binding = _resolve_host_binding()
            except HostProtocolError:
                self._host_binding_error = "HOST_EXECUTABLE_UNAVAILABLE"
        return self._host_binding

    def _client(self, workspace: Path) -> AppServerClient:
        if self._transport_factory is not None:
            return self._transport_factory()
        binding = self._resolved_host_binding()
        if binding is None:
            raise HostProtocolError(self._host_binding_error or "HOST_EXECUTABLE_UNAVAILABLE")
        (
            command,
            executable_path,
            executable_digest,
            pinned_files,
            interpreter_path,
            interpreter_digest,
        ) = binding
        return _SubprocessClient(
            cwd=workspace,
            command=command,
            pinned_files=pinned_files,
            host_executable_path=executable_path,
            host_executable_digest=executable_digest,
            host_interpreter_path=interpreter_path,
            host_interpreter_digest=interpreter_digest,
            allow_host_authentication=self._host_authentication,
        )

    @property
    def host_authentication_mode(self) -> str:
        """Expose the transport-auth mode without presenting it as a capability grant."""

        return "HOST_ONLY_CONTROL_PLANE" if self._host_authentication else "NONE"

    def prepare_invocation(self, request: CapabilityInvocationRequest) -> HostPreparation:
        errors = self.validate_invocation(request)
        resolved_binding = self._resolved_host_binding()
        return HostPreparation(
            supported=not errors,
            reason="official Codex app-server JSON-RPC boundary is available"
            if not errors
            else "; ".join(errors),
            official_support={
                "initialize": "OFFICIAL_DOCUMENTED",
                "skills/list": "OFFICIAL_DOCUMENTED",
                "thread/start": "OFFICIAL_DOCUMENTED",
                "turn/start": "OFFICIAL_DOCUMENTED",
                "skill_input_item": "OFFICIAL_DOCUMENTED",
                "item_and_turn_events": "HOST_OBSERVED",
                "skill_load_event": "UNKNOWN",
                "host_executable": (
                    "PINNED_SHA256"
                    if self._transport_factory is not None or resolved_binding is not None
                    else "UNAVAILABLE"
                ),
                "host_interpreter": (
                    "PINNED_SHA256"
                    if self._transport_factory is not None
                    or (resolved_binding is not None and resolved_binding[5] is not None)
                    else "UNAVAILABLE"
                ),
                "forbidden_action_events": "FAIL_CLOSED",
            },
        )

    def validate_invocation(self, request: CapabilityInvocationRequest) -> tuple[str, ...]:
        errors: list[str] = []
        if not Path(request.workspace).is_absolute():
            errors.append("WORKSPACE_MUST_BE_ABSOLUTE")
        if not Path(request.skill_path).is_absolute():
            errors.append("SKILL_PATH_MUST_BE_ABSOLUTE")
        if request.context.skill_path != request.skill_path:
            errors.append("CONTEXT_SKILL_PATH_MISMATCH")
        if request.authorization.network_policy != "DENY":
            errors.append("NETWORK_POLICY_UNSUPPORTED")
        if request.authorization.shell_policy != "DENY":
            errors.append("SHELL_POLICY_UNSUPPORTED")
        if request.authorization.mcp_policy != "DENY":
            errors.append("MCP_POLICY_UNSUPPORTED")
        if request.authorization.provider_policy != "DENY":
            errors.append("PROVIDER_POLICY_UNSUPPORTED")
        if request.authorization.credential_policy != "DENY":
            errors.append("CREDENTIAL_POLICY_UNSUPPORTED")
        errors.extend(self._validate_filesystem_policy(request))
        if (
            self._transport_factory is None
            and request.authorization.requested_execution_mode is ExecutionMode.CONTROLLED_REAL
        ):
            binding = self._resolved_host_binding()
            if binding is None:
                errors.append(self._host_binding_error or "HOST_EXECUTABLE_UNAVAILABLE")
            elif request.authorization.host_executable_digest is None:
                errors.append("HOST_EXECUTABLE_NOT_BOUND")
            elif request.authorization.host_executable_digest != binding[2]:
                errors.append("HOST_EXECUTABLE_FINGERPRINT_MISMATCH")
            elif request.authorization.host_interpreter_digest is None:
                errors.append("HOST_INTERPRETER_NOT_BOUND")
            elif binding[5] is None:
                errors.append("HOST_INTERPRETER_UNAVAILABLE")
            elif request.authorization.host_interpreter_digest != binding[5]:
                errors.append("HOST_INTERPRETER_FINGERPRINT_MISMATCH")
        return tuple(errors)

    def request_invocation(
        self,
        request: CapabilityInvocationRequest,
        *,
        budget: Phase4Budget,
        cancel_event: Event | None = None,
    ) -> HostInvocationResult:
        validation_errors = self.validate_invocation(request)
        if validation_errors:
            return self._blocked_result(validation_errors[0])
        if cancel_event is not None and cancel_event.is_set():
            return self._blocked_result(
                "CANCELLATION_REQUESTED_BEFORE_HOST_START",
                status=InvocationResultStatus.CANCELLED,
            )
        client: AppServerClient | None = None
        events: list[Phase4Event] = []
        final_message: str | None = None
        thread_id: str | None = None
        session_id: str | None = None
        turn_id: str | None = None
        host_version = "UNKNOWN"
        denied_approvals = 0
        host_action_count = 0
        started_at = int(time.time())
        completed_at: int | None = None
        invocation_observed = False
        execution_observed = False
        load_observation = HostLoadObservation.UNOBSERVABLE
        cancellation_status = "NOT_REQUESTED"
        status = InvocationResultStatus.UNKNOWN
        error_code: str | None = None
        protocol_message_count = 0
        mcp_event_count = 0
        approval_request_count = 0
        protocol_messages: tuple[ProtocolMessageObservation, ...] = ()
        host_executable_path: str | None = None
        host_executable_digest: str | None = None
        host_command: tuple[str, ...] = ()
        host_interpreter_path: str | None = None
        host_interpreter_digest: str | None = None
        binding = self._resolved_host_binding()
        if binding is not None:
            (
                host_command,
                host_executable_path,
                host_executable_digest,
                _,
                host_interpreter_path,
                host_interpreter_digest,
            ) = binding
        deadline = time.monotonic() + budget.timeout_seconds
        try:
            client = self._client(Path(request.workspace))
            initialize = client.call(
                "initialize",
                {
                    "clientInfo": {"name": "codex-state-of-art-harness", "version": "0.1.0"},
                    "capabilities": {"experimentalApi": True},
                },
                timeout_seconds=self._remaining_timeout(deadline),
            )
            initialize_result = _mapping(initialize.get("result"))
            host_version = _text(initialize_result.get("userAgent"), "UNKNOWN")
            client.notify("initialized", {})
            skills_response = client.call(
                "skills/list",
                {"cwds": [request.workspace], "forceReload": True},
                timeout_seconds=self._remaining_timeout(deadline),
            )
            if not self._skill_is_discovered(skills_response, request):
                return self._blocked_result("SKILL_NOT_DISCOVERED", host_version=host_version)
            thread_response = client.call(
                "thread/start",
                self._thread_params(request),
                timeout_seconds=self._remaining_timeout(deadline),
            )
            thread = _mapping(_mapping(thread_response.get("result")).get("thread"))
            thread_id = _text(thread.get("id")) or None
            session_id = _text(thread.get("sessionId")) or None
            if thread_id is None:
                raise HostProtocolError("app-server thread response has no id")
            turn_response = client.call(
                "turn/start",
                self._turn_params(request, thread_id),
                timeout_seconds=self._remaining_timeout(deadline),
            )
            turn = _mapping(_mapping(turn_response.get("result")).get("turn"))
            turn_id = _text(turn.get("id")) or None
            if turn_id is None:
                raise HostProtocolError("app-server turn response has no id")
            invocation_observed = True
            with self._active_lock:
                self._active_sessions[request.invocation_id] = (client, thread_id, turn_id)
            self._append_event(
                events,
                Phase4Event(
                    sequence=len(events),
                    method="turn/start",
                    fact_status=FactStatus.HOST_OBSERVED,
                    event_class="HOST_INVOCATION_ACKNOWLEDGED",
                    item_id=turn_id,
                    status="started",
                    thread_id=thread_id,
                    turn_id=turn_id,
                ),
                budget,
            )
            for message in client.stream(
                timeout_seconds=self._remaining_timeout(deadline),
                cancel_event=cancel_event,
            ):
                if message.get("__phase4_cancel_requested__") is True:
                    cancellation_status = self._interrupt(
                        client,
                        thread_id,
                        turn_id,
                        timeout_seconds=max(0.0, min(0.25, deadline - time.monotonic())),
                    )
                    status = (
                        InvocationResultStatus.CANCELLED
                        if cancellation_status == "HOST_INTERRUPT_ACKNOWLEDGED"
                        else InvocationResultStatus.UNKNOWN
                    )
                    error_code = (
                        "CANCELLATION_UNSUPPORTED_BY_HOST"
                        if status is InvocationResultStatus.UNKNOWN
                        else None
                    )
                    break
                method = _text(message.get("method"), "unknown")
                if not self._message_matches_invocation(message, thread_id, turn_id):
                    self._append_event(
                        events,
                        self._event_from_message(
                            message,
                            sequence=len(events),
                            event_class="CORRELATION_REJECTED",
                            detail="host event did not match the authorized thread and turn",
                        ),
                        budget,
                    )
                    status = InvocationResultStatus.FAILURE
                    error_code = "HOST_EVENT_CORRELATION_MISMATCH"
                    break
                handled, host_request_error = self._handle_host_request(
                    message,
                    client,
                    events,
                    budget,
                )
                if handled:
                    if host_request_error is not None:
                        status = InvocationResultStatus.FAILURE
                        error_code = host_request_error
                        break
                    continue
                if "id" in message and method.endswith("requestApproval"):
                    client.respond(message["id"], {"decision": "decline"})
                    denied_approvals += 1
                    self._append_event(
                        events,
                        self._event_from_message(
                            message,
                            sequence=len(events),
                            event_class="APPROVAL_DENIED",
                            detail="approval denied by Phase 4 policy",
                        ),
                        budget,
                    )
                    continue
                if self._is_forbidden_host_action(message):
                    host_action_count += 1
                    self._append_event(
                        events,
                        self._event_from_message(
                            message,
                            sequence=len(events),
                            event_class="FORBIDDEN_HOST_ACTION",
                            detail=(
                                "host reported a tool, shell, file, network, MCP or provider action"
                            ),
                        ),
                        budget,
                    )
                    status = InvocationResultStatus.FAILURE
                    error_code = (
                        "HOST_TOOL_BUDGET_EXCEEDED"
                        if host_action_count > budget.max_tool_calls
                        else "FORBIDDEN_HOST_ACTION_OBSERVED"
                    )
                    break
                event = self._event_from_message(message, sequence=len(events))
                self._append_event(events, event, budget)
                if method == "item/completed":
                    item = _mapping(_mapping(message.get("params")).get("item"))
                    if _text(item.get("type")) == "agentMessage":
                        final_message = _bounded_output(
                            _text(item.get("text")), budget.max_output_bytes
                        )
                if method == "turn/completed":
                    execution_observed = True
                    completed_at = int(time.time())
                    turn_status = _text(
                        _mapping(_mapping(message.get("params")).get("turn")).get("status")
                    )
                    status = (
                        InvocationResultStatus.SUCCESS
                        if turn_status in {"completed", "complete", "success"}
                        else InvocationResultStatus.FAILURE
                    )
                    if status is InvocationResultStatus.FAILURE:
                        error_code = "HOST_TURN_NOT_COMPLETED"
                    if denied_approvals:
                        status = InvocationResultStatus.PARTIAL
                    if self._has_load_event(events, request):
                        load_observation = HostLoadObservation.OBSERVED
                    break
        except HostTimeoutError:
            status = InvocationResultStatus.TIMED_OUT
            error_code = "HOST_INVOCATION_TIMEOUT"
            cancellation_status = "CANCELLATION_NOT_ATTEMPTED_DEADLINE_EXPIRED"
        except (HostProtocolError, OSError, ValueError) as exc:
            status = InvocationResultStatus.FAILURE
            error_code = type(exc).__name__.upper()
        finally:
            if client is not None:
                counter_getter = getattr(client, "protocol_counts", None)
                observation_getter = getattr(client, "protocol_observations", None)
                if callable(counter_getter):
                    try:
                        (
                            protocol_message_count,
                            mcp_event_count,
                            approval_request_count,
                        ) = counter_getter()
                    except (TypeError, ValueError):
                        status = InvocationResultStatus.FAILURE
                        error_code = "HOST_PROTOCOL_COUNTER_INVALID"
                else:
                    protocol_message_count = len(events)
                    mcp_event_count = sum(
                        1 for event in events if event.method.startswith("mcpServer/")
                    )
                    approval_request_count = denied_approvals
                if callable(observation_getter):
                    try:
                        raw_observations = observation_getter()
                        protocol_messages = tuple(raw_observations)
                        if any(
                            not isinstance(item, ProtocolMessageObservation)
                            for item in protocol_messages
                        ):
                            raise ValueError("protocol observations contain an invalid record")
                    except (TypeError, ValueError):
                        status = InvocationResultStatus.FAILURE
                        error_code = "HOST_PROTOCOL_OBSERVATION_INVALID"
                elif not callable(counter_getter):
                    protocol_messages = tuple(
                        ProtocolMessageObservation(
                            sequence=index,
                            method=event.method,
                            message_kind="notification",
                            has_id=False,
                            has_error=False,
                        )
                        for index, event in enumerate(events)
                    )
                if protocol_messages and len(protocol_messages) != protocol_message_count:
                    status = InvocationResultStatus.FAILURE
                    error_code = "HOST_PROTOCOL_OBSERVATION_INCOMPLETE"
                if not all(
                    type(value) is int and value >= 0
                    for value in (
                        protocol_message_count,
                        mcp_event_count,
                        approval_request_count,
                    )
                ):
                    status = InvocationResultStatus.FAILURE
                    error_code = "HOST_PROTOCOL_COUNTER_INVALID"
                    protocol_message_count = 0
                    mcp_event_count = 0
                    approval_request_count = 0
                elif protocol_message_count > 4_096:
                    status = InvocationResultStatus.FAILURE
                    error_code = "HOST_PROTOCOL_MESSAGE_BUDGET_EXCEEDED"
                denied_approvals = max(denied_approvals, approval_request_count)
            with self._active_lock:
                self._active_sessions.pop(request.invocation_id, None)
            if client is not None:
                with suppress(OSError):
                    client.close()
        if mcp_event_count:
            status = InvocationResultStatus.FAILURE
            error_code = "MCP_EVENT_OBSERVED"
        elif approval_request_count and status is InvocationResultStatus.SUCCESS:
            status = InvocationResultStatus.PARTIAL
        if status is InvocationResultStatus.UNKNOWN and error_code is None:
            error_code = "HOST_RESULT_UNAVAILABLE"
        return HostInvocationResult(
            status=status,
            thread_id=thread_id,
            session_id=session_id,
            turn_id=turn_id,
            host_version=host_version,
            events=tuple(events),
            final_message=final_message,
            load_observation=load_observation,
            invocation_observed=invocation_observed,
            execution_observed=execution_observed,
            denied_approvals=denied_approvals,
            cancellation_status=cancellation_status,
            error_code=error_code,
            started_at=started_at,
            completed_at=completed_at,
            protocol_message_count=protocol_message_count,
            mcp_event_count=mcp_event_count,
            approval_request_count=approval_request_count,
            protocol_messages=protocol_messages,
            host_executable_path=host_executable_path,
            host_executable_digest=host_executable_digest,
            host_command=host_command,
            host_interpreter_path=host_interpreter_path,
            host_interpreter_digest=host_interpreter_digest,
        )

    def _turn_params(
        self, request: CapabilityInvocationRequest, thread_id: str
    ) -> dict[str, object]:
        criteria = "\n".join(f"- {item}" for item in request.acceptance_criteria)
        prompt = (
            f"${request.skill_name}\nTask: {request.task}\n"
            f"Acceptance criteria:\n{criteria}\n"
            "Return a bounded final response."
        )
        return {
            "threadId": thread_id,
            "cwd": request.workspace,
            "input": [
                {"type": "text", "text": prompt},
                {"type": "skill", "name": request.skill_name, "path": request.skill_path},
            ],
            "approvalPolicy": "on-request",
            "sandboxPolicy": self._turn_sandbox_policy(request),
            "runtimeWorkspaceRoots": [request.workspace],
            "clientUserMessageId": request.invocation_id,
        }

    def _thread_params(self, request: CapabilityInvocationRequest) -> dict[str, object]:
        """Build the thread-start request so specialized hosts can bind tools."""

        return {
            "cwd": request.workspace,
            "ephemeral": True,
            "sandbox": self._thread_sandbox(request),
            "approvalPolicy": "on-request",
            "runtimeWorkspaceRoots": [request.workspace],
            "developerInstructions": self._developer_instructions,
        }

    def _thread_sandbox(self, request: CapabilityInvocationRequest) -> str:
        """Return the host sandbox for the default read-only adapter."""

        del request
        return "read-only"

    def _turn_sandbox_policy(self, request: CapabilityInvocationRequest) -> dict[str, object]:
        """Return the host turn sandbox for the default read-only adapter."""

        del request
        return {"type": "readOnly", "networkAccess": False}

    def _validate_filesystem_policy(
        self,
        request: CapabilityInvocationRequest,
    ) -> tuple[str, ...]:
        mode = request.authorization.filesystem_policy.get("mode", "READ_ONLY")
        return () if mode == "READ_ONLY" else ("FILESYSTEM_MODE_UNSUPPORTED",)

    @staticmethod
    def _skill_is_discovered(
        response: Mapping[str, object], request: CapabilityInvocationRequest
    ) -> bool:
        result = _mapping(response.get("result"))
        data = result.get("data")
        if not isinstance(data, list):
            return False
        for entry in data:
            entry_map = _mapping(entry)
            skills = entry_map.get("skills")
            if not isinstance(skills, list):
                continue
            for skill in skills:
                skill_map = _mapping(skill)
                if (
                    _text(skill_map.get("name")) == request.skill_name
                    and _text(skill_map.get("path")) == request.skill_path
                    and skill_map.get("enabled", True) is True
                ):
                    return True
        return False

    def _message_matches_invocation(
        self, message: Mapping[str, object], thread_id: str, turn_id: str
    ) -> bool:
        params = _mapping(message.get("params"))
        nodes = (
            message,
            params,
            _mapping(params.get("thread")),
            _mapping(params.get("turn")),
        )
        for node in nodes:
            for key, expected in (
                ("threadId", thread_id),
                ("thread_id", thread_id),
                ("turnId", turn_id),
                ("turn_id", turn_id),
            ):
                if key in node and node[key] != expected:
                    return False
        turn = _mapping(params.get("turn"))
        if "id" in turn and turn["id"] != turn_id:
            return False
        thread = _mapping(params.get("thread"))
        if "id" in thread and thread["id"] != thread_id:
            return False
        method = _text(message.get("method"))
        thread_seen = (
            any(key in node for node in nodes for key in ("threadId", "thread_id"))
            or "id" in thread
        )
        turn_seen = any(key in node for node in nodes for key in ("turnId", "turn_id")) or (
            "id" in turn
        )
        item = _mapping(params.get("item"))
        terminal_item = method == "item/completed" and _text(item.get("type")) == "agentMessage"
        if method in {"turn/completed", "turn/failed", "turn/cancelled"} or terminal_item:
            return thread_seen and turn_seen
        return True

    def _event_from_message(
        self,
        message: Mapping[str, object],
        *,
        sequence: int,
        event_class: str | None = None,
        detail: str | None = None,
    ) -> Phase4Event:
        method = _text(message.get("method"), "unknown")
        params = _mapping(message.get("params"))
        nodes = (
            message,
            params,
            _mapping(params.get("thread")),
            _mapping(params.get("turn")),
            _mapping(params.get("item")),
        )
        observed_thread_id: str | None = None
        observed_turn_id: str | None = None
        for node in nodes:
            if observed_thread_id is None:
                for key in ("threadId", "thread_id"):
                    observed_thread_id = _text(node.get(key)) or None
                    if observed_thread_id is not None:
                        break
            if observed_turn_id is None:
                for key in ("turnId", "turn_id"):
                    observed_turn_id = _text(node.get(key)) or None
                    if observed_turn_id is not None:
                        break
        if observed_thread_id is None:
            observed_thread_id = _text(_mapping(params.get("thread")).get("id")) or None
        if observed_turn_id is None:
            observed_turn_id = _text(_mapping(params.get("turn")).get("id")) or None
        item = _mapping(params.get("item"))
        item_type = _text(item.get("type")) or None
        item_id = _text(item.get("id")) or None
        status = _text(item.get("status")) or None
        if not status:
            status = _text(_mapping(params.get("turn")).get("status")) or None
        if detail is None and method in {"skill/loaded", "skill/load/completed"}:
            load_values = tuple(
                value
                for value in (
                    params.get("skillName"),
                    params.get("name"),
                    params.get("path"),
                    item.get("name"),
                    item.get("path"),
                )
                if isinstance(value, str) and value
            )
            detail = " ".join(load_values)[:2_048] or None
        if event_class is None:
            event_class = "HOST_EVENT"
        return Phase4Event(
            sequence=sequence,
            method=method,
            fact_status=FactStatus.HOST_OBSERVED,
            event_class=event_class,
            item_type=item_type,
            item_id=item_id,
            status=status,
            detail=detail,
            thread_id=observed_thread_id,
            turn_id=observed_turn_id,
        )

    @staticmethod
    def _append_event(events: list[Phase4Event], event: Phase4Event, budget: Phase4Budget) -> None:
        if len(events) >= budget.max_host_events:
            raise HostProtocolError("host event budget exceeded")
        events.append(event)

    @staticmethod
    def _has_load_event(events: list[Phase4Event], request: CapabilityInvocationRequest) -> bool:
        return any(
            event.method in {"skill/loaded", "skill/load/completed"}
            and event.detail is not None
            and request.skill_name in event.detail
            and (request.skill_path in event.detail or request.skill_name in event.detail)
            for event in events
        )

    def _is_forbidden_host_action(self, message: Mapping[str, object]) -> bool:
        method = _text(message.get("method")).casefold()
        if method.startswith(_FORBIDDEN_HOST_METHOD_PREFIXES):
            return True
        params = _mapping(message.get("params"))
        item = _mapping(params.get("item"))
        item_type = _text(item.get("type")).casefold().replace("_", "").replace("-", "")
        return item_type in _FORBIDDEN_HOST_ITEM_TYPES or any(
            token in item_type
            for token in (
                "tool",
                "command",
                "shell",
                "network",
                "provider",
                "credential",
                "subagent",
            )
        )

    def _handle_host_request(
        self,
        message: Mapping[str, object],
        client: AppServerClient,
        events: list[Phase4Event],
        budget: Phase4Budget,
    ) -> tuple[bool, str | None]:
        """Handle a specialized host request before generic action rejection."""

        del message, client, events, budget
        return False, None

    @staticmethod
    def _remaining_timeout(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HostTimeoutError("app-server invocation timed out")
        return remaining

    @staticmethod
    def _interrupt(
        client: AppServerClient,
        thread_id: str,
        turn_id: str,
        *,
        timeout_seconds: float,
    ) -> str:
        if timeout_seconds <= 0:
            return "CANCELLATION_NOT_ATTEMPTED_DEADLINE_EXPIRED"
        try:
            client.call(
                "turn/interrupt",
                {"threadId": thread_id, "turnId": turn_id},
                timeout_seconds=timeout_seconds,
            )
        except (HostProtocolError, HostTimeoutError, OSError):
            return "CANCELLATION_UNSUPPORTED_BY_HOST"
        return "HOST_INTERRUPT_ACKNOWLEDGED"

    @staticmethod
    def _blocked_result(
        error_code: str,
        *,
        host_version: str = "UNKNOWN",
        status: InvocationResultStatus = InvocationResultStatus.BLOCKED,
    ) -> HostInvocationResult:
        now = int(time.time())
        return HostInvocationResult(
            status=status,
            thread_id=None,
            session_id=None,
            turn_id=None,
            host_version=host_version,
            events=(),
            final_message=None,
            load_observation=HostLoadObservation.UNOBSERVABLE,
            invocation_observed=False,
            execution_observed=False,
            denied_approvals=0,
            cancellation_status="NOT_REQUESTED",
            error_code=error_code,
            started_at=now,
            completed_at=now,
        )

    def observe_invocation(self, result: HostInvocationResult) -> HostInvocationResult:
        return result

    def cancel_invocation(self, request: CapabilityInvocationRequest) -> str:
        with self._active_lock:
            active = self._active_sessions.get(request.invocation_id)
        if active is None:
            return "CANCELLATION_REQUIRES_ACTIVE_SESSION"
        client, thread_id, turn_id = active
        try:
            client.notify("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})
        except (HostProtocolError, OSError):
            return "CANCELLATION_REQUEST_FAILED"
        return "HOST_INTERRUPT_REQUESTED"

    def collect_result(self, result: HostInvocationResult) -> HostInvocationResult:
        return result
