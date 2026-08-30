"""Strict, bounded validation for the pilot's transport and service boundary."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

MAX_BODY_BYTES = 16_384
MAX_ID_LENGTH = 64
MAX_HEADER_LENGTH = 128
REQUIRED_FIELDS = frozenset(
    {"client_id", "patient_id", "provider_id", "starts_at", "duration_minutes"}
)


class ValidationError(ValueError):
    """Raised when input is not valid for the public contract."""


class DuplicateJSONKeyError(ValidationError):
    """Raised when a JSON object repeats a key."""


class NonFiniteJSONError(ValidationError):
    """Raised when JSON contains NaN or an infinity value."""


class PayloadTooLargeError(ValidationError):
    """Raised when a request body exceeds the pilot's hard bound."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise NonFiniteJSONError(f"non-finite JSON number: {value}")


def parse_json_body(raw_body: bytes) -> object:
    """Parse one bounded JSON document with duplicate/non-finite rejection."""

    if not isinstance(raw_body, bytes):
        raise ValidationError("request body must be bytes")
    if len(raw_body) > MAX_BODY_BYTES:
        raise PayloadTooLargeError("request body exceeds the maximum size")
    try:
        text = raw_body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("request body is not valid UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
        )
    except (DuplicateJSONKeyError, NonFiniteJSONError):
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ValidationError("request body is not valid JSON") from exc


def validate_header(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field_name} is required")
    if len(value) > MAX_HEADER_LENGTH:
        raise ValidationError(f"{field_name} is too long")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValidationError(f"{field_name} contains a control character")
    return value


def validate_identifier(value: object, field_name: str, *, max_length: int = MAX_ID_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")
    if len(value) > max_length:
        raise ValidationError(f"{field_name} is too long")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValidationError(f"{field_name} contains a control character")
    return value


def _reject_nonfinite_values(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise NonFiniteJSONError("non-finite number is not allowed")
    if isinstance(value, Mapping):
        for nested in value.values():
            _reject_nonfinite_values(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_nonfinite_values(nested)


def _canonical_utc(value: str) -> str:
    if "T" not in value:
        raise ValidationError("starts_at must be an ISO-8601 UTC timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValidationError("starts_at must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValidationError("starts_at must use UTC")
    normalized = parsed.astimezone(UTC)
    rendered = normalized.strftime("%Y-%m-%dT%H:%M:%S")
    if normalized.microsecond:
        rendered += f".{normalized.microsecond:06d}".rstrip("0")
    return rendered + "Z"


def validate_create_payload(payload: object) -> dict[str, object]:
    """Return a normalized copy of the exact create request shape."""

    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object")
    _reject_nonfinite_values(payload)
    actual_fields = set(payload)
    missing = REQUIRED_FIELDS - actual_fields
    unknown = actual_fields - REQUIRED_FIELDS
    if missing:
        raise ValidationError("request body is missing required fields")
    if unknown:
        raise ValidationError("request body contains unknown fields")

    client_id = validate_identifier(payload["client_id"], "client_id")
    patient_id = validate_identifier(payload["patient_id"], "patient_id")
    provider_id = validate_identifier(payload["provider_id"], "provider_id")
    starts_at_value = payload["starts_at"]
    if not isinstance(starts_at_value, str) or len(starts_at_value) > 64:
        raise ValidationError("starts_at must be a bounded string")
    starts_at = _canonical_utc(starts_at_value)
    duration = payload["duration_minutes"]
    if isinstance(duration, bool) or not isinstance(duration, int):
        raise ValidationError("duration_minutes must be an integer")
    if not 15 <= duration <= 120:
        raise ValidationError("duration_minutes must be between 15 and 120")
    return {
        "client_id": client_id,
        "patient_id": patient_id,
        "provider_id": provider_id,
        "starts_at": starts_at,
        "duration_minutes": duration,
    }


def canonical_request_hash(payload: Mapping[str, object]) -> str:
    """Hash the normalized request shape independently of object key order."""

    normalized = validate_create_payload(dict(payload))
    encoded = json.dumps(
        normalized,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
