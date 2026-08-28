"""Safe, read-only command line inspection for the Phase 1 kernel."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, TextIO

from .classification import classify_task
from .errors import ContractError, ContractValidationError, DeserializationError
from .models import (
    ArtifactRecord,
    CapabilityInvocation,
    CapabilityManifest,
    CritiqueReport,
    EvidenceRecord,
    ExecutionGraph,
    QualityReport,
    RegistryOrigin,
    RouteDecision,
    RunSummary,
    SourceType,
    TaskProfile,
    TelemetryEvent,
    VerificationReport,
)
from .registry import CapabilityRegistry, RegistryDiagnostic
from .routing import minimum_route
from .serialization import MAX_JSON_BYTES, from_dict, to_dict
from .telemetry import TelemetryLog
from .validation import ValidationCode, ValidationFinding, ValidationResult, validate

MAX_TEXT_CHARS = 10_000
MAX_PATH_CHARS = 4_096
MAX_JSON_DEPTH = 64
MAX_CONFIG_PATH_CHARS = 512
MAX_CONFIG_INTEGER = 1_000_000_000
MAX_REGISTRY_FILES = 256
MAX_TELEMETRY_EVENTS = 1_024
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}$")

_CONFIG_KEYS = frozenset(
    {
        "schema_version",
        "project_id",
        "strict_validation",
        "registry",
        "paths",
        "budgets",
        "telemetry",
    }
)
_REGISTRY_KEYS = frozenset({"manifest_dir", "capability_dir"})
_PATH_KEYS = frozenset({"state_dir", "evidence_dir", "telemetry_dir", "eval_dir", "cache_dir"})
_BUDGET_KEYS = frozenset(
    {"max_iterations", "max_failures", "max_parallelism", "max_context_tokens"}
)
_TELEMETRY_KEYS = frozenset(
    {"redaction_enabled", "append_only", "allow_unobserved_capability_loaded"}
)

_SCHEMA_MODELS: dict[str, type[Any]] = {
    "TP-1": TaskProfile,
    "RD-1": RouteDecision,
    "EG-1": ExecutionGraph,
    "CM-1": CapabilityManifest,
    "CI-1": CapabilityInvocation,
    "AR-1": ArtifactRecord,
    "ER-1": EvidenceRecord,
    "VR-1": VerificationReport,
    "CR-1": CritiqueReport,
    "QR-1": QualityReport,
    "TE-1": TelemetryEvent,
    "RS-1": RunSummary,
}


class CliError(Exception):
    """An intentionally safe, non-sensitive command error."""

    def __init__(self, code: str, message: str, *, exit_code: int = 2) -> None:
        self.code = code
        self.safe_message = message
        self.exit_code = exit_code
        super().__init__(message)


def _validate_path_text(value: str) -> None:
    if not value or len(value) > MAX_PATH_CHARS or "\x00" in value:
        raise CliError("PATH_INVALID", "input path is invalid")
    normalized = value.replace("\\", "/")
    if any(part == ".." for part in normalized.split("/")):
        raise CliError("PATH_INVALID", "input path is outside the project boundary")


def _check_json_depth(raw: bytes) -> None:
    depth = 0
    in_string = False
    escaped = False
    for byte in raw:
        if in_string:
            if escaped:
                escaped = False
            elif byte == ord("\\"):
                escaped = True
            elif byte == ord('"'):
                in_string = False
            continue
        if byte == ord('"'):
            in_string = True
        elif byte in (ord("{"), ord("[")):
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise CliError("DEPTH_LIMIT_EXCEEDED", "JSON nesting exceeds the supported limit")
        elif byte in (ord("}"), ord("]")):
            depth = max(0, depth - 1)


def _root(value: str | None) -> Path:
    if value is not None:
        _validate_path_text(value)
    candidate = Path(value) if value else Path.cwd()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CliError("PATH_INVALID", "project root is unavailable") from exc
    if not resolved.is_dir():
        raise CliError("PATH_INVALID", "project root is not a directory")
    return resolved


def _input_path(source: str, root: Path) -> Path:
    if not source or source == "-":
        raise CliError("PATH_INVALID", "input path is invalid")
    _validate_path_text(source)
    candidate = Path(source)
    try:
        resolved = (
            candidate.resolve(strict=True)
            if candidate.is_absolute()
            else (root / candidate).resolve(strict=True)
        )
    except (OSError, RuntimeError) as exc:
        raise CliError("INPUT_UNAVAILABLE", "input could not be read") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CliError("PATH_INVALID", "input path is outside the project boundary") from exc
    if not resolved.is_file():
        raise CliError("INPUT_UNAVAILABLE", "input is not a regular file")
    return resolved


def _read_bytes(source: str, root: Path, stdin: TextIO) -> bytes:
    if source == "-":
        stream: Any = getattr(stdin, "buffer", stdin)
        try:
            raw = stream.read(MAX_JSON_BYTES + 1)
        except (AttributeError, OSError, TypeError, ValueError) as exc:
            raise CliError("INPUT_UNAVAILABLE", "stdin could not be read") from exc
    else:
        path = _input_path(source, root)
        try:
            with path.open("rb") as handle:
                raw = handle.read(MAX_JSON_BYTES + 1)
        except CliError:
            raise
        except (OSError, ValueError) as exc:
            raise CliError("INPUT_UNAVAILABLE", "input could not be read") from exc
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not isinstance(raw, (bytes, bytearray)):
        raise CliError("INPUT_UNAVAILABLE", "input could not be read")
    raw = bytes(raw)
    if len(raw) > MAX_JSON_BYTES:
        raise CliError("SIZE_LIMIT_EXCEEDED", "input exceeds the supported size limit")
    return raw


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DeserializationError("duplicate JSON object key", code="DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise DeserializationError("non-finite JSON number is not allowed", code="INVALID_JSON")


def _read_json(source: str, root: Path, stdin: TextIO) -> Mapping[str, Any] | list[Any]:
    raw = _read_bytes(source, root, stdin)
    _check_json_depth(raw)
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except DeserializationError as exc:
        raise CliError(str(exc.code), "input JSON is invalid") from exc
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise CliError("INVALID_JSON", "input JSON is invalid") from exc
    if not isinstance(value, (Mapping, list)):
        raise CliError("INVALID_INPUT", "input JSON must be an object or array")
    return value


def _safe_path(path: object) -> str:
    value = str(path)
    if len(value) <= 256 and re.fullmatch(r"\$(?:\.[A-Za-z_][A-Za-z0-9_]*|\[\d*\])*", value):
        return value
    return "$"


def _finding_dict(finding: object) -> dict[str, str]:
    raw_code = getattr(finding, "code", "INVALID_INPUT")
    code = str(getattr(raw_code, "value", raw_code))
    message = str(getattr(finding, "message", "contract is invalid"))
    if len(message) > 240:
        message = "contract validation failed"
    path = (
        "$"
        if code == ValidationCode.UNKNOWN_FIELD.value
        else _safe_path(getattr(finding, "path", "$"))
    )
    return {"code": code, "path": path, "message": message}


def _validation_findings(values: Iterable[object]) -> tuple[ValidationFinding, ...]:
    normalized: list[ValidationFinding] = []
    for value in values:
        raw_code = getattr(value, "code", ValidationCode.INVARIANT_VIOLATION)
        code_value = str(getattr(raw_code, "value", raw_code))
        try:
            code = ValidationCode(code_value)
        except ValueError:
            code = ValidationCode.INVARIANT_VIOLATION
        normalized.append(
            ValidationFinding(
                code=code,
                message=str(getattr(value, "message", "contract is invalid")),
                path=_safe_path(getattr(value, "path", "$")),
            )
        )
    return tuple(normalized)


def _validation_payload(
    result: ValidationResult, *, document_schema: str | None = None
) -> dict[str, object]:
    return {
        "status": "PASS" if result.is_valid else "FAIL",
        "valid": result.is_valid,
        "record_type": result.record_type,
        "document_schema": document_schema,
        "findings": [_finding_dict(item) for item in result.findings],
    }


def _config_path_is_safe(value: object) -> bool:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_CONFIG_PATH_CHARS:
        return False
    normalized = value.replace("\\", "/")
    return not normalized.startswith("/") and ".." not in normalized.split("/")


def _config_unknown_fields(
    value: Mapping[str, Any], allowed: frozenset[str], path: str, findings: list[ValidationFinding]
) -> None:
    for _key in sorted(set(value) - allowed):
        findings.append(
            ValidationFinding(
                ValidationCode.UNKNOWN_FIELD,
                "configuration field is not supported",
                path,
            )
        )


def _config_result(value: Mapping[str, Any]) -> ValidationResult:
    findings: list[ValidationFinding] = []
    required = (
        "schema_version",
        "project_id",
        "strict_validation",
        "registry",
        "paths",
        "budgets",
        "telemetry",
    )
    for key in required:
        if key not in value:
            findings.append(
                ValidationFinding(
                    ValidationCode.REQUIRED_FIELD,
                    "required configuration field is missing",
                    f"$.{key}",
                )
            )
    if value.get("schema_version") != "HK-1":
        findings.append(
            ValidationFinding(
                ValidationCode.INVALID_VERSION,
                "unsupported configuration schema",
                "$.schema_version",
            )
        )
    if not isinstance(value.get("project_id"), str) or not _IDENTIFIER.fullmatch(
        str(value.get("project_id", ""))
    ):
        findings.append(
            ValidationFinding(
                ValidationCode.INVALID_ID,
                "project_id must be a valid identifier",
                "$.project_id",
            )
        )
    if not isinstance(value.get("strict_validation"), bool):
        findings.append(
            ValidationFinding(
                ValidationCode.INVALID_TYPE,
                "strict_validation must be boolean",
                "$.strict_validation",
            )
        )
    _config_unknown_fields(value, _CONFIG_KEYS, "$", findings)
    sections = (
        ("registry", _REGISTRY_KEYS),
        ("paths", _PATH_KEYS),
        ("budgets", _BUDGET_KEYS),
        ("telemetry", _TELEMETRY_KEYS),
    )
    for section, allowed in sections:
        section_value = value.get(section)
        if not isinstance(section_value, Mapping):
            findings.append(
                ValidationFinding(
                    ValidationCode.INVALID_TYPE,
                    "configuration section must be an object",
                    f"$.{section}",
                )
            )
            continue
        _config_unknown_fields(section_value, allowed, f"$.{section}", findings)
        for key in sorted(allowed - set(section_value)):
            findings.append(
                ValidationFinding(
                    ValidationCode.REQUIRED_FIELD,
                    "required configuration field is missing",
                    f"$.{section}.{key}",
                )
            )
        if section in {"registry", "paths"}:
            for key, item in section_value.items():
                if key in allowed and not _config_path_is_safe(item):
                    findings.append(
                        ValidationFinding(
                            ValidationCode.INVALID_REFERENCE,
                            "configuration path must be a bounded project-relative path",
                            f"$.{section}.{key}",
                        )
                    )
        elif section == "budgets":
            for key, item in section_value.items():
                if key in allowed and (
                    not isinstance(item, int)
                    or isinstance(item, bool)
                    or item < 0
                    or item > MAX_CONFIG_INTEGER
                ):
                    findings.append(
                        ValidationFinding(
                            ValidationCode.INVARIANT_VIOLATION,
                            "budget must be a bounded non-negative integer",
                            f"$.{section}.{key}",
                        )
                    )
        else:
            for key, item in section_value.items():
                if key in allowed and not isinstance(item, bool):
                    findings.append(
                        ValidationFinding(
                            ValidationCode.INVALID_TYPE,
                            "telemetry setting must be boolean",
                            f"$.{section}.{key}",
                        )
                    )
    return ValidationResult(
        valid=not findings, findings=tuple(findings), record_type="KernelConfig"
    )


def _contract_from_value(
    value: Mapping[str, Any],
) -> tuple[object | None, dict[str, object] | None]:
    schema = value.get("schema_version")
    if schema == "HK-1":
        result = _config_result(value)
        return None, _validation_payload(result, document_schema="HK-1")
    if not isinstance(schema, str) or schema not in _SCHEMA_MODELS:
        result = ValidationResult(
            valid=False,
            findings=(),
            record_type=None,
        )
        return None, {
            **_validation_payload(result),
            "findings": [
                {
                    "code": "INVALID_VERSION",
                    "path": "$.schema_version",
                    "message": "unsupported contract schema",
                }
            ],
        }
    model_type = _SCHEMA_MODELS[schema]
    try:
        value_object = from_dict(value, model_type)
    except ContractValidationError as exc:
        result = ValidationResult(
            valid=False,
            findings=_validation_findings(exc.findings),
            record_type=model_type.__name__,
        )
        return None, _validation_payload(result, document_schema=schema)
    except DeserializationError as exc:
        result = ValidationResult(
            valid=False,
            findings=(
                ValidationFinding(
                    code=ValidationCode.INVALID_TYPE,
                    message="contract field could not be decoded",
                    path=_safe_path(exc.path),
                ),
            ),
            record_type=model_type.__name__,
        )
        return None, _validation_payload(result, document_schema=schema)
    except ContractError as exc:
        raise CliError(str(exc.code), "contract input could not be decoded") from exc
    return value_object, _validation_payload(validate(value_object), document_schema=schema)


def _load_contract(
    source: str, root: Path, stdin: TextIO, expected: type[Any] | None = None
) -> object:
    value = _read_json(source, root, stdin)
    if not isinstance(value, Mapping):
        raise CliError("INVALID_INPUT", "contract input must be an object")
    schema = value.get("schema_version")
    model_type = expected or _SCHEMA_MODELS.get(str(schema))
    if model_type is None:
        raise CliError("INVALID_VERSION", "unsupported contract schema")
    try:
        result = from_dict(value, model_type)
    except ContractError as exc:
        raise CliError(str(exc.code), "contract input could not be decoded") from exc
    return result


def _manifest_files(root: Path) -> tuple[Path, ...]:
    config_path = root / ".harness" / "config" / "kernel.json"
    try:
        config = _read_json(str(config_path), root, sys.stdin)
    except CliError as exc:
        raise CliError("CONFIG_INVALID", "project configuration is unavailable") from exc
    if not isinstance(config, Mapping) or not _config_result(config).is_valid:
        raise CliError("CONFIG_INVALID", "project configuration is invalid")
    registry_config = config["registry"]
    assert isinstance(registry_config, Mapping)

    def configured_directory(key: str) -> Path:
        value = registry_config[key]
        if not isinstance(value, str) or not _config_path_is_safe(value):
            raise CliError("CONFIG_INVALID", "project registry paths are invalid")
        try:
            resolved = (root / value).resolve(strict=False)
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise CliError("CONFIG_INVALID", "project registry paths are invalid") from exc
        return resolved

    registry_directory = configured_directory("manifest_dir")
    if not registry_directory.is_dir():
        raise CliError("REGISTRY_UNAVAILABLE", "project registry is unavailable")
    paths = [path for path in registry_directory.glob("*.json") if path.is_file()]
    capability_directory = configured_directory("capability_dir")
    if capability_directory.is_dir():
        for capability in capability_directory.iterdir():
            manifest = capability / "manifest.json"
            if capability.is_dir() and manifest.is_file():
                paths.append(manifest)
    result = tuple(sorted(paths))
    if len(result) > MAX_REGISTRY_FILES:
        raise CliError(
            "REGISTRY_SIZE_LIMIT", "project registry exceeds the supported manifest limit"
        )
    return result


def _manifest_source_hash(manifest: CapabilityManifest, root: Path) -> str:
    payload = to_dict(manifest)
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("manifest provenance is invalid")
    provenance["source_hash"] = ""
    digest = hashlib.sha256()
    canonical_manifest = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest.update(b"phase-1-manifest-v1\0")
    digest.update(canonical_manifest)
    for reference in sorted(manifest.provenance.source_refs):
        source_path = _input_path(reference, root)
        digest.update(b"\0source-ref\0")
        digest.update(reference.encode("utf-8"))
        digest.update(b"\0")
        with source_path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _workspace_root(root: Path) -> Path | None:
    if (root / "architecture").is_dir():
        return root
    for candidate in root.parents:
        if (candidate / "architecture").is_dir() and (candidate / "projects").is_dir():
            return candidate
    return None


def _manifest_reference_failures(
    manifest: CapabilityManifest, root: Path
) -> tuple[dict[str, str], ...]:
    workspace = _workspace_root(root)
    failures: list[dict[str, str]] = []
    for reference in manifest.dependencies.references:
        if reference.startswith(("http://", "https://")):
            continue
        if workspace is None or not reference or Path(reference).is_absolute():
            failures.append(
                {
                    "code": "MANIFEST_REFERENCE_UNVERIFIABLE",
                    "path": "$.dependencies.references",
                    "message": "manifest reference cannot be resolved within the workspace",
                }
            )
            continue
        try:
            _validate_path_text(reference)
            target = (workspace / reference).resolve(strict=True)
            target.relative_to(workspace)
        except (CliError, OSError, RuntimeError, ValueError):
            failures.append(
                {
                    "code": "MISSING_MANIFEST_REFERENCE",
                    "path": "$.dependencies.references",
                    "message": "manifest reference does not resolve to a workspace file",
                }
            )
    return tuple(failures)


def _manifest_provenance_failures(
    manifest: CapabilityManifest, root: Path
) -> tuple[dict[str, str], ...]:
    failures: list[dict[str, str]] = []
    provenance = manifest.provenance
    source_type = getattr(provenance.source_type, "value", provenance.source_type)
    if source_type == SourceType.LOCAL.value:
        if len(provenance.source_refs) != 1:
            failures.append(
                {
                    "code": "SOURCE_HASH_UNVERIFIABLE",
                    "path": "$.provenance.source_refs",
                    "message": (
                        "local source hash requires exactly one project-local source reference"
                    ),
                }
            )
        else:
            try:
                source_hash = _manifest_source_hash(manifest, root)
            except (CliError, OSError, ValueError):
                source_hash = ""
            if source_hash != provenance.source_hash:
                failures.append(
                    {
                        "code": "SOURCE_HASH_MISMATCH",
                        "path": "$.provenance.source_hash",
                        "message": "local source content does not match the declared source hash",
                    }
                )

    origin = getattr(provenance.origin, "value", provenance.origin)
    if origin in {RegistryOrigin.PROJECT.value, RegistryOrigin.VENDORED.value}:
        config_path = root / ".harness" / "config" / "kernel.json"
        try:
            config = _read_json(str(config_path), root, sys.stdin)
        except CliError:
            config = None
        if not isinstance(config, Mapping) or config.get("project_id") != provenance.project_scope:
            failures.append(
                {
                    "code": "PROJECT_SCOPE_MISMATCH",
                    "path": "$.provenance.project_scope",
                    "message": (
                        "manifest project ownership does not match the project configuration"
                    ),
                }
            )
    return tuple(failures)


def _load_registry(root: Path) -> tuple[CapabilityRegistry, tuple[dict[str, str], ...]]:
    loaded_manifests: list[CapabilityManifest] = []
    manifests: list[CapabilityManifest] = []
    loaded_by_key: dict[tuple[str, str], CapabilityManifest] = {}
    failures: list[dict[str, str]] = []
    for path in _manifest_files(root):
        try:
            loaded = _load_contract(str(path), root, sys.stdin, CapabilityManifest)
        except CliError:
            failures.append(
                {
                    "code": "INVALID_MANIFEST",
                    "path": "$.manifest",
                    "message": "manifest could not be decoded",
                }
            )
            continue
        if isinstance(loaded, CapabilityManifest):
            loaded_manifests.append(loaded)
    for loaded in loaded_manifests:
        key = (loaded.capability_id, loaded.version)
        existing = loaded_by_key.get(key)
        if existing is not None:
            if to_dict(existing) != to_dict(loaded):
                failures.append(
                    {
                        "code": "MANIFEST_DIVERGENCE",
                        "path": "$.registry",
                        "message": ("manifest sources disagree for the same capability ID/version"),
                    }
                )
            continue
        loaded_by_key[key] = loaded
        reference_failures = _manifest_reference_failures(loaded, root)
        if reference_failures:
            failures.extend(reference_failures)
            continue
        provenance_failures = _manifest_provenance_failures(loaded, root)
        if provenance_failures:
            failures.extend(provenance_failures)
            continue
        manifests.append(loaded)
    try:
        return CapabilityRegistry.from_manifests(manifests), tuple(failures)
    except (TypeError, ValueError):
        failures.append(
            {
                "code": "INVALID_MANIFEST",
                "path": "$.registry",
                "message": "registry metadata is invalid",
            }
        )
        return CapabilityRegistry(), tuple(failures)


def _diagnostic_dict(item: RegistryDiagnostic) -> dict[str, str]:
    severity = getattr(item.severity, "value", item.severity)
    return {
        "code": item.code,
        "message": item.message,
        "capability_id": item.capability_id or "",
        "version": item.version or "",
        "path": _safe_path(item.path),
        "severity": str(severity),
    }


def _doctor(root: Path) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    config_path = root / ".harness" / "config" / "kernel.json"
    try:
        config = _read_json(str(config_path), root, sys.stdin)
        config_result = (
            _config_result(config)
            if isinstance(config, Mapping)
            else ValidationResult(False, (), "KernelConfig")
        )
        checks.append(
            {"id": "PROJECT_CONFIG", "status": "PASS" if config_result.is_valid else "FAIL"}
        )
    except CliError:
        checks.append({"id": "PROJECT_CONFIG", "status": "FAIL"})
    try:
        registry, failures = _load_registry(root)
        checks.append(
            {
                "id": "REGISTRY_METADATA",
                "status": "PASS" if not failures else "FAIL",
                "manifests": len(registry.list()),
            }
        )
    except CliError:
        checks.append({"id": "REGISTRY_METADATA", "status": "FAIL", "manifests": 0})
    capability_root = root / ".harness" / "capabilities"
    checks.append(
        {"id": "CAPABILITY_BOUNDARY", "status": "PASS" if capability_root.is_dir() else "FAIL"}
    )
    checks.append(
        {"id": "CAPABILITY_EXECUTION", "status": "NOT_RUN", "reason": "Phase 1 has no executor"}
    )
    status = "PASS" if all(item["status"] != "FAIL" for item in checks) else "FAIL"
    return {
        "status": status,
        "command": "doctor",
        "root_scope": "project-local",
        "capabilities_executed": False,
        "checks": checks,
    }


def _state_report(root: Path) -> dict[str, object]:
    source = root / ".agent" / "state.json"
    value = _read_json(str(source), root, sys.stdin)
    if not isinstance(value, Mapping):
        raise CliError("INVALID_STATE", "project state is invalid")
    required = (
        "project",
        "status",
        "lifecycle_stage",
        "active_activity",
        "next_gate",
        "next_action",
    )
    if any(
        not isinstance(value.get(key), str) or not str(value.get(key)).strip() for key in required
    ):
        raise CliError("INVALID_STATE", "project state is invalid")
    state = {key: str(value[key]) for key in required}
    return {"status": "PASS", "command": "state", "valid": True, "state": state}


def _telemetry_report(source: str, root: Path, stdin: TextIO) -> dict[str, object]:
    value = _read_json(source, root, stdin)
    raw_events: object = value.get("events") if isinstance(value, Mapping) else value
    if not isinstance(raw_events, list):
        raise CliError("INVALID_INPUT", "telemetry input must contain an events array")
    if len(raw_events) > MAX_TELEMETRY_EVENTS:
        raise CliError("TELEMETRY_SIZE_LIMIT", "telemetry event count exceeds the supported limit")
    log = TelemetryLog()
    for item in raw_events:
        if not isinstance(item, Mapping):
            raise CliError("INVALID_INPUT", "telemetry event input is invalid")
        try:
            event = from_dict(item, TelemetryEvent)
            log = log.append(event)
        except (ContractError, TypeError, ValueError) as exc:
            raise CliError("INVALID_TELEMETRY", "telemetry log is invalid", exit_code=1) from exc
    result = log.validate()
    return {
        "status": "PASS" if result.is_valid else "FAIL",
        "valid": result.is_valid,
        "command": "telemetry validate",
        "record_type": "TelemetryLog",
        "events": len(log.events),
        "findings": [_finding_dict(item) for item in result.findings],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harness-kernel",
        description="Phase 1 project-local contract inspection; no capability execution.",
    )
    commands = parser.add_subparsers(dest="command")

    validate_parser = commands.add_parser(
        "validate", help="validate a local JSON contract or kernel config"
    )
    validate_parser.add_argument("source")
    validate_parser.add_argument("--format", choices=("json", "text"), default="json")
    validate_parser.add_argument("--root", default=None)

    doctor_parser = commands.add_parser(
        "doctor", help="perform deterministic project-local health checks"
    )
    doctor_parser.add_argument("--root", default=None)
    doctor_parser.add_argument("--format", choices=("json", "text"), default="json")
    health_parser = commands.add_parser("health", help="alias for doctor")
    health_parser.add_argument("--root", default=None)
    health_parser.add_argument("--format", choices=("json", "text"), default="json")

    registry_parser = commands.add_parser("registry", help="inspect declarative local manifests")
    registry_parser.add_argument("--root", default=None)
    registry_parser.add_argument("--format", choices=("json", "text"), default="json")
    registry_commands = registry_parser.add_subparsers(dest="registry_command", required=True)
    list_parser = registry_commands.add_parser("list", help="list manifest metadata")
    list_parser.add_argument("--format", choices=("json", "text"), default=None)
    inspect_parser = registry_commands.add_parser("inspect", help="inspect one manifest")
    inspect_parser.add_argument("capability_id")
    inspect_parser.add_argument("--version", default=None)
    inspect_parser.add_argument("--format", choices=("json", "text"), default=None)

    profile_parser = commands.add_parser("profile", help="classify an objective into a TaskProfile")
    profile_parser.add_argument("objective")
    profile_parser.add_argument("--task-id", default="TASK-CLI")
    profile_parser.add_argument("--run-id", default="RUN-CLI")
    profile_parser.add_argument("--format", choices=("json", "text"), default="json")

    route_parser = commands.add_parser(
        "route", help="validate a profile and propose a minimum route"
    )
    route_parser.add_argument("profile", nargs="?")
    route_parser.add_argument("--objective", default=None)
    route_parser.add_argument("--root", default=None)
    route_parser.add_argument("--format", choices=("json", "text"), default="json")

    state_parser = commands.add_parser("state", help="inspect the project control state")
    state_parser.add_argument("--root", default=None)
    state_parser.add_argument("--format", choices=("json", "text"), default="json")

    telemetry_parser = commands.add_parser("telemetry", help="inspect versioned telemetry")
    telemetry_parser.add_argument("--root", default=None)
    telemetry_parser.add_argument("--format", choices=("json", "text"), default="json")
    telemetry_commands = telemetry_parser.add_subparsers(dest="telemetry_command", required=True)
    telemetry_validate = telemetry_commands.add_parser(
        "validate", help="validate an append-only event log"
    )
    telemetry_validate.add_argument("source")
    telemetry_validate.add_argument("--format", choices=("json", "text"), default=None)
    return parser


def _render(payload: Mapping[str, object], output_format: str, command: str) -> None:
    if output_format == "text":
        status = payload.get("status", "UNKNOWN")
        detail = payload.get("record_type") or payload.get("command") or command
        print(f"{status} {command}: {detail}")
        return
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the read-only Phase 1 CLI and return a process exit code."""

    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        if args.command == "validate":
            project_root = _root(args.root)
            value = _read_json(args.source, project_root, sys.stdin)
            if not isinstance(value, Mapping):
                raise CliError("INVALID_INPUT", "contract input must be an object")
            _, payload = _contract_from_value(value)
            assert payload is not None
            _render(payload, args.format, "validate")
            return 0 if payload["valid"] else 1
        if args.command in {"doctor", "health"}:
            payload = _doctor(_root(args.root))
            payload = {**payload, "command": args.command}
            _render(payload, args.format, args.command)
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "registry":
            project_root = _root(args.root)
            registry, failures = _load_registry(project_root)
            output_format = args.format or "json"
            if args.registry_command == "list":
                manifests = tuple(registry.list())
                payload = {
                    "status": "PASS" if not failures else "FAIL",
                    "command": "registry list",
                    "valid": not failures,
                    "count": len(manifests),
                    "manifests": [to_dict(item) for item in manifests],
                    "findings": list(failures),
                }
                _render(payload, output_format, "registry list")
                return 0 if payload["status"] == "PASS" else 1
            inspection = registry.inspect(args.capability_id, args.version)
            payload = {
                "status": "PASS" if inspection.usable and not failures else "FAIL",
                "command": "registry inspect",
                "valid": inspection.is_valid,
                "usable": inspection.usable,
                "manifest": to_dict(inspection.manifest) if inspection.manifest else None,
                "diagnostics": [_diagnostic_dict(item) for item in inspection.diagnostics],
                "findings": list(failures),
            }
            _render(payload, output_format, "registry inspect")
            return 0 if payload["status"] == "PASS" else 1
        if args.command == "profile":
            if len(args.objective) > MAX_TEXT_CHARS:
                raise CliError("SIZE_LIMIT_EXCEEDED", "objective exceeds the supported size limit")
            if _IDENTIFIER.fullmatch(args.task_id) is None:
                raise CliError("INVALID_INPUT", "task id is invalid")
            if _IDENTIFIER.fullmatch(args.run_id) is None:
                raise CliError("INVALID_INPUT", "run id is invalid")
            profile = classify_task(
                args.objective,
                task_id=args.task_id,
                run_id=args.run_id,
            )
            payload = {
                "status": "PASS",
                "command": "profile",
                "valid": True,
                "record_type": "TaskProfile",
                "profile": to_dict(profile),
            }
            _render(payload, args.format, "profile")
            return 0
        if args.command == "route":
            project_root = _root(args.root)
            if args.profile is None and args.objective is None:
                raise CliError("INVALID_INPUT", "route requires a profile or objective")
            if args.objective is not None and len(args.objective) > MAX_TEXT_CHARS:
                raise CliError("SIZE_LIMIT_EXCEEDED", "objective exceeds the supported size limit")
            profile_value = (
                _load_contract(args.profile, project_root, sys.stdin, TaskProfile)
                if args.profile is not None
                else classify_task(str(args.objective), task_id="TASK-CLI", run_id="RUN-CLI")
            )
            if not isinstance(profile_value, TaskProfile):
                raise CliError("INVALID_INPUT", "route profile is invalid")
            profile = profile_value
            registry, failures = _load_registry(project_root)
            route = minimum_route(profile, registry)
            result = validate(route)
            payload = {
                **_validation_payload(result, document_schema="RD-1"),
                "command": "route",
                "executed": False,
                "route": to_dict(route),
                "registry_findings": list(failures),
            }
            _render(payload, args.format, "route")
            return 0 if result.is_valid and not failures else 1
        if args.command == "state":
            payload = _state_report(_root(args.root))
            _render(payload, args.format, "state")
            return 0
        if args.command == "telemetry":
            project_root = _root(args.root)
            if args.telemetry_command != "validate":
                raise CliError("INVALID_INPUT", "unknown telemetry command")
            payload = _telemetry_report(args.source, project_root, sys.stdin)
            _render(payload, args.format or "json", "telemetry validate")
            return 0 if payload["status"] == "PASS" else 1
    except CliError as exc:
        payload = {"status": "ERROR", "code": exc.code, "message": exc.safe_message}
        output_format = getattr(args, "format", None) or "json"
        _render(payload, output_format, str(getattr(args, "command", "harness-kernel")))
        return exc.exit_code
    return 2
