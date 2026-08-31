"""Run a deterministic, dependency-free static accessibility audit of the pilot."""

from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path


class AccessibilityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.ids: set[str] = set()
        self.labels: set[str] = set()
        self.controls: list[dict[str, str]] = []
        self.headings: list[tuple[int, str]] = []
        self.landmarks: set[str] = set()
        self.live_regions = 0
        self._control_stack: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        self.tags.append(tag)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        if tag == "label" and attributes.get("for"):
            self.labels.add(attributes["for"])
        if tag in {"input", "select", "textarea", "button"}:
            control = {"tag": tag, "text": "", **attributes}
            self.controls.append(control)
            self._control_stack.append(control)
        if tag.startswith("h") and len(tag) == 2 and tag[1].isdigit():
            self.headings.append((int(tag[1]), attributes.get("id", "")))
        if tag in {"main", "nav", "header", "footer", "aside", "form"} or attributes.get("role"):
            self.landmarks.add(attributes.get("role", tag))
        if attributes.get("aria-live"):
            self.live_regions += 1

    def handle_data(self, data: str) -> None:
        if self._control_stack:
            self._control_stack[-1]["text"] += " ".join(data.split())

    def handle_endtag(self, tag: str) -> None:
        if tag in self.tags:
            index = len(self.tags) - 1 - self.tags[::-1].index(tag)
            self.tags.pop(index)
        if self._control_stack and self._control_stack[-1]["tag"] == tag:
            self._control_stack.pop()


def audit(path: Path) -> dict[str, object]:
    parser = AccessibilityParser()
    parser.feed(path.read_text(encoding="utf-8"))
    failures: list[str] = []
    control_failures: list[str] = []
    for control in parser.controls:
        if control["tag"] == "button":
            named = control.get("aria-label") or control.get("title") or control.get("text")
        else:
            named = control.get("aria-label") or control.get("id")
        missing_label = (
            control["tag"] != "button"
            and control.get("id")
            and control["id"] not in parser.labels
            and not control.get("aria-label")
        )
        if not named or missing_label:
            control_failures.append(f"{control['tag']}:{control.get('id', '<unnamed>')}")
    if len([level for level, _ in parser.headings if level == 1]) != 1:
        failures.append("document must have exactly one h1")
    if not {"main", "nav"} <= parser.landmarks:
        failures.append("main and nav landmarks are required")
    if control_failures:
        failures.append("controls without an associated accessible name")
    if parser.live_regions < 1:
        failures.append("at least one live region is required")
    payload = {
        "schema_version": "P8-A11Y-STATIC-1",
        "source": str(path),
        "status": "PASS" if not failures else "FAIL",
        "checks": {
            "h1_count": len([level for level, _ in parser.headings if level == 1]),
            "heading_levels": [level for level, _ in parser.headings],
            "landmarks": sorted(parser.landmarks),
            "control_count": len(parser.controls),
            "live_region_count": parser.live_regions,
            "control_failures": control_failures,
        },
        "failures": failures,
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--html",
        type=Path,
        default=Path("evidence/phase-8/pilots/frontend-engineering/app/index.html"),
    )
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = audit(arguments.html.resolve(strict=True))
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
