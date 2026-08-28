"""Structured errors for the contract boundary.

Errors expose a stable code and path, while deliberately omitting raw input
values.  This keeps malformed or sensitive JSON from being echoed into logs or
consumer-facing messages.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_JSON = "INVALID_JSON"
    DESERIALIZATION_ERROR = "DESERIALIZATION_ERROR"
    SERIALIZATION_ERROR = "SERIALIZATION_ERROR"
    DUPLICATE_KEY = "DUPLICATE_KEY"
    SIZE_LIMIT_EXCEEDED = "SIZE_LIMIT_EXCEEDED"


@dataclass(frozen=True, slots=True)
class ErrorDetail:
    code: str
    message: str
    path: str = "$"


class ContractError(Exception):
    """Base exception with machine-readable code and location."""

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | str = ErrorCode.INVALID_INPUT,
        path: str = "$",
        details: Iterable[ErrorDetail] = (),
    ) -> None:
        self.code = code.value if isinstance(code, ErrorCode) else code
        self.path = path
        self.details = tuple(details)
        self.message = message
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        return f"{self.code} at {self.path}: {self.message}"


class ContractValidationError(ContractError):
    """Raised when a parsed or constructed contract violates an invariant."""

    def __init__(self, findings: Iterable[object] = ()) -> None:
        normalized = tuple(findings)
        details = tuple(
            ErrorDetail(
                code=str(getattr(finding, "code", "INVARIANT_VIOLATION")),
                message=str(getattr(finding, "message", "contract is invalid")),
                path=str(getattr(finding, "path", "$")),
            )
            for finding in normalized
        )
        first = details[0] if details else ErrorDetail("VALIDATION_ERROR", "contract is invalid")
        self.findings = normalized
        super().__init__(
            first.message,
            code=ErrorCode.VALIDATION_ERROR,
            path=first.path,
            details=details,
        )


class DeserializationError(ContractError):
    """Raised for malformed, unsafe, or type-incompatible JSON data."""

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | str = ErrorCode.DESERIALIZATION_ERROR,
        path: str = "$",
    ) -> None:
        super().__init__(message, code=code, path=path)


class SerializationError(ContractError):
    """Raised when a value cannot be represented as contract JSON."""

    def __init__(self, message: str, *, path: str = "$") -> None:
        super().__init__(message, code=ErrorCode.SERIALIZATION_ERROR, path=path)


ValidationError = ContractValidationError
SchemaError = ContractValidationError
