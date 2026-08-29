"""Bounded, non-executing parser for declarative ``SKILL.md`` metadata."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from .phase3_models import ParseStatus, SkillDocument, SkillSection


class SkillParseError(ValueError):
    """Raised only for direct parser API misuse; malformed content is returned."""


class _MetadataStructureError(ValueError):
    """Raised internally when structured metadata exceeds parser safety bounds."""


_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,199}$")
_VERSION_IDENTIFIER = r"(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
_VERSION = re.compile(
    rf"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    rf"(?:-{_VERSION_IDENTIFIER}(?:\.{_VERSION_IDENTIFIER})*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_LINK = re.compile(r"\[[^\]]{1,200}\]\(([^)\s]{1,400})\)")
_UNSAFE_ACTIVATION = re.compile(
    r"\b(?:always\s+activate|activate\s+for\s+every\s+request|ignore\s+(?:all\s+)?policy)\b",
    re.I,
)
_MAX_TEXT_BYTES = 64 * 1024
_MAX_VERSION_LENGTH = 256
_MAX_FRONT_LINES = 512
_MAX_SECTION_LINES = 128
_MAX_LIST_ITEMS = 64
_MAX_METADATA_NESTING = 64


def _is_semver(value: str) -> bool:
    return len(value) <= _MAX_VERSION_LENGTH and _VERSION.fullmatch(value) is not None


def _array_nesting_exceeds(value: str) -> bool:
    depth = 0
    escaped = False
    in_string = False
    for character in value:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "[":
            depth += 1
            if depth > _MAX_METADATA_NESTING:
                return True
        elif character == "]":
            depth = max(0, depth - 1)
    return False


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _has_mapping_separator(value: str) -> bool:
    in_quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if in_quote is not None:
            if in_quote == '"' and escaped:
                escaped = False
            elif in_quote == '"' and character == "\\":
                escaped = True
            elif character == in_quote:
                in_quote = None
            continue
        if character in {"'", '"'}:
            in_quote = character
        elif character == ":" and (index + 1 == len(value) or value[index + 1].isspace()):
            return True
    return False


def _scalar_metadata(value: str) -> str:
    clean = value.strip()
    if not clean:
        return ""
    if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in {"'", '"'}:
        clean = clean[1:-1]
    elif (
        clean[0] in "[{"
        or clean.startswith(("- ", "*", "&", "!"))
        or clean in {"|", ">"}
        or _has_mapping_separator(clean)
    ):
        raise _MetadataStructureError("front matter structured metadata is unsupported")
    if "\x00" in clean:
        raise _MetadataStructureError("front matter metadata contains NUL")
    return clean[:400]


def _items(value: str, pending: Iterable[str] = ()) -> tuple[str, ...]:
    raw = value.strip()
    values: list[str] = list(pending)
    if raw:
        parsed: object = None
        if raw.startswith("["):
            if _array_nesting_exceeds(raw):
                raise _MetadataStructureError("front matter list nesting exceeds its bound")
            try:
                parsed = json.loads(
                    raw,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
                )
            except RecursionError as exc:
                raise _MetadataStructureError(
                    "front matter list nesting exceeds its bound"
                ) from exc
            except (TypeError, ValueError):
                parsed = None
        if isinstance(parsed, list):
            if not all(isinstance(item, str) for item in parsed):
                raise _MetadataStructureError("front matter structured metadata is unsupported")
            values.extend(parsed)
        elif raw.startswith("["):
            raise _MetadataStructureError("front matter structured list is malformed")
        else:
            values.extend(_scalar_metadata(part) for part in raw.split(",") if part.strip())
    result: list[str] = []
    for item in values[:_MAX_LIST_ITEMS]:
        if "\x00" not in item and item not in result:
            result.append(item[:400])
    return tuple(result)


def _sections(body_lines: list[str]) -> tuple[SkillSection, ...]:
    headings: list[tuple[str, int]] = []
    for index, line in enumerate(body_lines):
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match:
            headings.append((match.group(1).strip()[:160], index))
    result: list[SkillSection] = []
    for position, (title, start) in enumerate(headings):
        end = headings[position + 1][1] if position + 1 < len(headings) else len(body_lines)
        lines: list[str] = []
        for line in body_lines[start + 1 : end][:_MAX_SECTION_LINES]:
            clean = line.strip()
            if clean.startswith(("- ", "* ")):
                clean = clean[2:].strip()
            if clean:
                lines.append(clean[:400])
        result.append(SkillSection(title, tuple(lines)))
    return tuple(result)


def _section_values(sections: tuple[SkillSection, ...], names: set[str]) -> tuple[str, ...]:
    result: list[str] = []
    for section in sections:
        if section.title.casefold().strip() not in names:
            continue
        for line in section.lines:
            if line not in result:
                result.append(line)
    return tuple(result[:_MAX_LIST_ITEMS])


def _parse_front_matter(
    lines: list[str],
) -> tuple[dict[str, str], dict[str, tuple[str, ...]], int, list[str]]:
    values: dict[str, str] = {}
    lists: dict[str, tuple[str, ...]] = {}
    errors: list[str] = []
    if not lines or lines[0].strip() != "---":
        return values, lists, 0, errors
    end = None
    for index, line in enumerate(lines[1 : _MAX_FRONT_LINES + 1], start=1):
        if line.strip() == "---":
            end = index
            break
    if end is None:
        return values, lists, 0, ["front matter closing delimiter is missing"]
    current_key: str | None = None
    pending: list[str] = []
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.strip()
        if stripped.startswith("-") and current_key is not None:
            try:
                pending.append(_scalar_metadata(stripped[1:]))
            except _MetadataStructureError as exc:
                errors.append(str(exc))
            continue
        if current_key is not None:
            lists[current_key] = _items("", pending)
            current_key = None
            pending = []
        if ":" not in stripped:
            errors.append("front matter line has no key separator")
            continue
        key, raw = stripped.split(":", 1)
        key = key.strip()
        if not _KEY.fullmatch(key):
            errors.append(f"invalid front matter key: {key[:80]}")
            current_key = None
            pending = []
            continue
        normalized = key.casefold().replace("-", "_")
        if normalized in values or normalized in lists:
            errors.append(f"duplicate front matter key: {normalized}")
            current_key = None
            pending = []
            continue
        raw_value = raw.strip()
        if raw_value:
            try:
                if raw_value.startswith("["):
                    parsed_items = _items(raw_value)
                    values[normalized] = raw_value[:2000]
                    lists[normalized] = parsed_items
                else:
                    if "," in raw_value:
                        parsed_items = _items(raw_value)
                        values[normalized] = _scalar_metadata(raw_value)[:2000]
                        lists[normalized] = parsed_items
                    else:
                        values[normalized] = _scalar_metadata(raw_value)[:2000]
            except _MetadataStructureError as exc:
                errors.append(str(exc))
            current_key = None
            pending = []
        else:
            current_key = normalized
            pending = []
    if current_key is not None:
        lists[current_key] = _items("", pending)
    return values, lists, end, errors


def parse_skill_text(text: str, *, source: str = "SKILL.md") -> SkillDocument:
    """Parse only bounded metadata and Markdown section labels from text."""

    if not isinstance(text, str) or "\x00" in text:
        raise SkillParseError("skill text must be a NUL-free string")
    if len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
        return SkillDocument(
            source,
            ParseStatus.INVALID,
            None,
            "",
            None,
            {},
            (),
            (),
            "",
            errors=("SKILL.md exceeds the parser byte bound",),
        )
    lines = text.splitlines()
    try:
        values, lists, front_end, errors = _parse_front_matter(lines)
    except _MetadataStructureError as exc:
        return SkillDocument(
            source,
            ParseStatus.INVALID,
            None,
            "",
            None,
            {},
            (),
            (),
            "",
            errors=(str(exc),),
        )
    if errors and front_end == 0 and lines and lines[0].strip() == "---":
        return SkillDocument(
            source,
            ParseStatus.INVALID,
            None,
            "",
            None,
            values,
            tuple(values.items()),
            (),
            "",
            errors=tuple(errors),
        )
    body_lines = lines[front_end + 1 :] if front_end else lines
    body = "\n".join(body_lines)
    sections = _sections(body_lines)
    front_matter_values = (*values.values(), *(item for items in lists.values() for item in items))
    if _UNSAFE_ACTIVATION.search(body) or any(
        _UNSAFE_ACTIVATION.search(value) for value in front_matter_values
    ):
        errors.append("unsafe always-activate directive is treated as data and rejected")
    if not front_end:
        if not text.strip():
            return SkillDocument(
                source,
                ParseStatus.INVALID,
                None,
                "",
                None,
                {},
                (),
                sections,
                body,
                errors=("SKILL.md has no front matter or body",),
            )
        legacy_errors = ["legacy SKILL.md without front matter"]
        legacy_errors.extend(errors)
        legacy_activates = _section_values(sections, {"activation", "when to use", "triggers"})
        legacy_do_not = _section_values(
            sections, {"do not use", "do not activate", "avoid", "never use"}
        )
        legacy_missing_exclusion = bool(legacy_activates and not legacy_do_not)
        if legacy_missing_exclusion:
            legacy_errors.append("do-not-activate metadata is missing; activation remains blocked")
        return SkillDocument(
            source,
            ParseStatus.INVALID if errors or legacy_missing_exclusion else ParseStatus.LEGACY,
            None,
            "",
            None,
            {},
            (),
            sections,
            body,
            activates_when=legacy_activates,
            do_not_activate_when=legacy_do_not,
            references=tuple(_LINK.findall(body))[:_MAX_LIST_ITEMS],
            gates=_section_values(sections, {"gates", "quality gates"}),
            stop_conditions=_section_values(sections, {"stop", "stop conditions"}),
            errors=tuple(legacy_errors),
        )

    capability_id = values.get("name")
    if not capability_id or not _ID.fullmatch(capability_id):
        errors.append("front matter name is missing or invalid")
        capability_id = None
    description = values.get("description", values.get("short_description", ""))
    version = values.get("version")
    if version is not None and not _is_semver(version):
        errors.append("front matter version is not semantic-version shaped")
        version = None
    known = {
        "name",
        "description",
        "short_description",
        "version",
        "activates_when",
        "activation",
        "when_to_use",
        "do_not_activate_when",
        "do_not_use",
        "references",
        "dependencies",
        "tools",
        "providers",
        "conflicts",
        "domains",
        "primary_type",
        "platform_limits",
        "gates",
        "stop_conditions",
        "stop",
        "compatibility",
    }
    unknown_values = [(key, value) for key, value in values.items() if key not in known]
    unknown_values.extend(
        (key, ", ".join(items)) for key, items in lists.items() if key not in known
    )
    unknown = tuple(unknown_values)
    activates = _items(values.get("activates_when", ""), lists.get("activates_when", ()))
    activates = activates or _items(values.get("activation", ""), lists.get("activation", ()))
    activates = activates or _items(values.get("when_to_use", ""), lists.get("when_to_use", ()))
    do_not = _items(values.get("do_not_activate_when", ""), lists.get("do_not_activate_when", ()))
    do_not = do_not or _items(values.get("do_not_use", ""), lists.get("do_not_use", ()))
    references = _items(values.get("references", ""), lists.get("references", ()))
    references = references or tuple(_LINK.findall(body))[:_MAX_LIST_ITEMS]
    section_activation = _section_values(sections, {"activation", "when to use", "triggers"})
    section_block = _section_values(
        sections, {"do not use", "do not activate", "avoid", "never use"}
    )
    section_gates = _section_values(sections, {"gates", "quality gates"})
    section_stops = _section_values(sections, {"stop", "stop conditions"})
    activates = activates or section_activation
    do_not = do_not or section_block
    if activates and not do_not:
        errors.append("do-not-activate metadata is missing; activation remains blocked")
    parse_status = (
        ParseStatus.VALID if capability_id is not None and not errors else ParseStatus.INVALID
    )
    return SkillDocument(
        source,
        parse_status,
        capability_id,
        description[:2000],
        version,
        values,
        unknown,
        sections,
        body,
        activates_when=activates,
        do_not_activate_when=do_not,
        references=references,
        dependencies=_items(values.get("dependencies", ""), lists.get("dependencies", ())),
        tools=_items(values.get("tools", ""), lists.get("tools", ())),
        providers=_items(values.get("providers", ""), lists.get("providers", ())),
        conflicts=_items(values.get("conflicts", ""), lists.get("conflicts", ())),
        domains=_items(values.get("domains", ""), lists.get("domains", ())),
        primary_type=values.get("primary_type", "SPECIALIST").upper(),
        platform_limits=(
            _items(values.get("platform_limits", ""), lists.get("platform_limits", ()))
            or _items(values.get("compatibility", ""), lists.get("compatibility", ()))
        ),
        gates=_items(values.get("gates", ""), lists.get("gates", ())) or section_gates,
        stop_conditions=(
            _items(values.get("stop_conditions", ""), lists.get("stop_conditions", ()))
            or _items(values.get("stop", ""), lists.get("stop", ()))
            or section_stops
        ),
        errors=tuple(errors),
    )


def parse_skill_bytes(payload: bytes, *, source: str = "SKILL.md") -> SkillDocument:
    if not isinstance(payload, bytes):
        raise SkillParseError("skill payload must be bytes")
    if len(payload) > _MAX_TEXT_BYTES:
        return SkillDocument(
            source,
            ParseStatus.INVALID,
            None,
            "",
            None,
            {},
            (),
            (),
            "",
            errors=("SKILL.md exceeds the parser byte bound",),
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return SkillDocument(
            source,
            ParseStatus.INVALID,
            None,
            "",
            None,
            {},
            (),
            (),
            "",
            errors=("SKILL.md is not valid UTF-8",),
        )
    return parse_skill_text(text, source=source)
