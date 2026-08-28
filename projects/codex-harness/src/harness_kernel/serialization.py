"""Deterministic, data-only JSON conversion for contract models."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import MISSING, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from types import UnionType
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

from .errors import ContractValidationError, DeserializationError, SerializationError

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100_000


def _check_json_shape(raw: bytes) -> None:
    """Reject pathological nesting and container counts before JSON decoding."""

    depth = 0
    nodes = 0
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
            continue
        if byte in (ord("{"), ord("[")):
            depth += 1
            nodes += 1
            if depth > MAX_JSON_DEPTH:
                raise DeserializationError(
                    "JSON nesting exceeds the supported limit", code="DEPTH_LIMIT_EXCEEDED"
                )
        elif byte in (ord("}"), ord("]")):
            depth -= 1
            if depth < 0:
                raise DeserializationError("invalid JSON", code="INVALID_JSON")
        elif byte in (ord(","), ord(":")):
            nodes += 1
        if nodes > MAX_JSON_NODES:
            raise DeserializationError(
                "JSON container count exceeds the supported limit", code="SIZE_LIMIT_EXCEEDED"
            )


def _check_data_shape(value: object) -> None:
    """Apply the same bounds to mappings passed directly to ``from_dict``."""

    stack: list[tuple[object, int]] = [(value, 0)]
    seen: set[int] = set()
    nodes = 0
    while stack:
        current, depth = stack.pop()
        if isinstance(current, (Mapping, list, tuple)):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            nodes += 1
            if depth > MAX_JSON_DEPTH:
                raise DeserializationError(
                    "JSON nesting exceeds the supported limit", code="DEPTH_LIMIT_EXCEEDED"
                )
            if nodes > MAX_JSON_NODES:
                raise DeserializationError(
                    "JSON container count exceeds the supported limit", code="SIZE_LIMIT_EXCEEDED"
                )
            children = current.values() if isinstance(current, Mapping) else current
            stack.extend((child, depth + 1) for child in children)


def _json_key(model_field: Any) -> str:
    return str(model_field.metadata.get("json_key", model_field.name))


def to_primitive(value: Any, *, path: str = "$") -> Any:
    """Convert supported values to JSON primitives without executing them."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SerializationError("non-finite numbers are not valid contract JSON", path=path)
        return value
    if isinstance(value, Enum):
        return to_primitive(value.value, path=path)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            _json_key(model_field): to_primitive(
                getattr(value, model_field.name), path=f"{path}.{_json_key(model_field)}"
            )
            for model_field in fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [to_primitive(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SerializationError("JSON object keys must be strings", path=path)
            result[key] = to_primitive(item, path=f"{path}.{key}")
        return result
    raise TypeError(f"unsupported value for contract JSON at {path}: {type(value).__name__}")


def to_dict(value: Any) -> dict[str, Any]:
    """Return a JSON-compatible mapping for a dataclass contract."""

    primitive = to_primitive(value)
    if not isinstance(primitive, dict):
        raise TypeError("contract serialization requires a dataclass or mapping root")
    return primitive


def to_json(value: Any, *, sort_keys: bool = True) -> str:
    """Serialize a contract reproducibly using compact UTF-8 JSON."""

    try:
        return json.dumps(
            to_primitive(value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=sort_keys,
        )
    except SerializationError:
        raise
    except (RecursionError, TypeError, ValueError) as exc:
        raise SerializationError("value cannot be represented as contract JSON") from exc


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DeserializationError("duplicate JSON object key", code="DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise DeserializationError("non-finite JSON number is not allowed", code="INVALID_JSON")


def _convert(value: Any, annotation: Any, *, path: str) -> Any:
    if annotation is Any or annotation is object:
        return value
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (UnionType, Union):
        if value is None and type(None) in args:
            return None
        for option in args:
            if option is type(None):
                continue
            try:
                return _convert(value, option, path=path)
            except DeserializationError:
                continue
        raise DeserializationError("value does not match the declared contract type", path=path)
    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            raise DeserializationError("expected JSON array", path=path)
        item_type = args[0] if args else Any
        return tuple(_convert(item, item_type, path=f"{path}[{i}]") for i, item in enumerate(value))
    if origin is list:
        if not isinstance(value, list):
            raise DeserializationError("expected JSON array", path=path)
        item_type = args[0] if args else Any
        return [_convert(item, item_type, path=f"{path}[{i}]") for i, item in enumerate(value)]
    if origin in (dict, Mapping):
        if not isinstance(value, dict):
            raise DeserializationError("expected JSON object", path=path)
        return value
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        try:
            return annotation(value)
        except (TypeError, ValueError) as exc:
            raise DeserializationError("invalid enum value", path=path) from exc
    if isinstance(annotation, type) and is_dataclass(annotation):
        if not isinstance(value, Mapping):
            raise DeserializationError("expected JSON object", path=path)
        return _construct_dataclass(value, annotation, path=path)
    if annotation is str:
        if not isinstance(value, str):
            raise DeserializationError("expected string", path=path)
        return value
    if annotation is bool:
        if not isinstance(value, bool):
            raise DeserializationError("expected boolean", path=path)
        return value
    if annotation is int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise DeserializationError("expected integer", path=path)
        return value
    if annotation is float:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise DeserializationError("expected number", path=path)
        return float(value)
    if annotation in (datetime, date, time):
        if not isinstance(value, str):
            raise DeserializationError("expected timestamp string", path=path)
        try:
            return annotation.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DeserializationError("invalid ISO timestamp", path=path) from exc
    if annotation is type(None):
        if value is not None:
            raise DeserializationError("expected null", path=path)
        return None
    return value


def _construct_dataclass[T](data: Mapping[str, Any], model_type: type[T], *, path: str) -> T:
    model_fields = fields(cast(Any, model_type))
    by_key = {_json_key(model_field): model_field for model_field in model_fields}
    unknown = [key for key in data if key not in by_key]
    if unknown:
        from .validation import ValidationCode, ValidationFinding

        finding = ValidationFinding(
            code=ValidationCode.UNKNOWN_FIELD,
            message="unknown field is not part of the contract",
            path=f"{path}.{unknown[0]}",
        )
        raise ContractValidationError((finding,))
    hints = get_type_hints(model_type)
    values: dict[str, Any] = {}
    for model_field in model_fields:
        key = _json_key(model_field)
        if key not in data:
            if model_field.default is not MISSING:
                values[model_field.name] = model_field.default
                continue
            if model_field.default_factory is not MISSING:
                values[model_field.name] = model_field.default_factory()
                continue
            raise DeserializationError("required field is missing", path=f"{path}.{key}")
        values[model_field.name] = _convert(
            data[key], hints.get(model_field.name, Any), path=f"{path}.{key}"
        )
    try:
        return model_type(**values)
    except TypeError as exc:
        raise DeserializationError("contract object has invalid fields", path=path) from exc


def from_dict[T](data: Mapping[str, Any] | type[T], model_type: type[T] | Mapping[str, Any]) -> T:
    """Build a typed contract from JSON-compatible data and validate it."""

    if isinstance(data, type):
        data, model_type = model_type, data
    if not isinstance(data, Mapping) or not isinstance(model_type, type):
        raise DeserializationError("expected a mapping and a model type")
    _check_data_shape(data)
    if model_type is dict:
        return dict(data)  # type: ignore[return-value]
    if not is_dataclass(model_type):
        raise DeserializationError("model type must be a dataclass contract")
    try:
        value = _construct_dataclass(data, model_type, path="$")
        from .validation import validate

        result = validate(value)
        if not result.is_valid:
            result.raise_for_error()
        return value
    except RecursionError as exc:
        raise DeserializationError(
            "contract nesting exceeds the supported limit", code="DEPTH_LIMIT_EXCEEDED"
        ) from exc


def from_json[T](
    payload: str | bytes | bytearray | type[T], model_type: type[T] | str | bytes
) -> T:
    """Parse JSON without evaluating code, then construct and validate a model."""

    if isinstance(payload, type):
        payload, model_type = model_type, payload
    if not isinstance(model_type, type):
        raise DeserializationError("model type is required")
    if isinstance(payload, str):
        raw = payload.encode("utf-8")
    elif isinstance(payload, (bytes, bytearray)):
        raw = bytes(payload)
    else:
        raise DeserializationError("JSON payload must be text or bytes")
    if len(raw) > MAX_JSON_BYTES:
        raise DeserializationError("JSON payload exceeds size limit", code="SIZE_LIMIT_EXCEEDED")
    _check_json_shape(raw)
    try:
        data = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except DeserializationError:
        raise
    except RecursionError as exc:
        raise DeserializationError(
            "JSON nesting exceeds the supported limit", code="DEPTH_LIMIT_EXCEEDED"
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeserializationError("invalid JSON", code="INVALID_JSON") from exc
    if not isinstance(data, Mapping):
        raise DeserializationError("contract JSON must contain an object")
    return from_dict(data, model_type)


serialize = to_json
deserialize = from_json
loads = from_json
dumps = to_json
