"""Deterministic source lint for the Phase 8 dependency-free frontend pilot."""

from __future__ import annotations

import argparse
import re
from html.parser import HTMLParser
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
PILOT_ROOT = PROJECT_ROOT / "evidence/phase-8/pilots/frontend-engineering/app"
FORBIDDEN = ("http://", "https://", "javascript:", "eval(", "innerHTML", "onclick=")


class _IdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.headings: list[tuple[int, str]] = []
        self.external_scripts = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"] or "")
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append((int(tag[1]), values.get("id", "")))
        if tag == "script" and values.get("src", "").startswith(("http://", "https://")):
            self.external_scripts += 1


def lint(root: Path = PILOT_ROOT) -> list[str]:
    findings: list[str] = []
    html = (root / "index.html").read_text(encoding="utf-8")
    css = (root / "styles.css").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    parser = _IdParser()
    parser.feed(html)
    if len(parser.ids) != len(set(parser.ids)):
        findings.append("duplicate HTML id")
    if parser.external_scripts:
        findings.append("external script source")
    if parser.headings.count((1, "page-title")) != 1:
        findings.append("expected exactly one page-title h1")
    heading_levels = [item[0] for item in parser.headings]
    if heading_levels and any(
        level > previous + 1
        for previous, level in zip(
            (0, *heading_levels[:-1]),
            heading_levels,
            strict=True,
        )
    ):
        findings.append("heading level skips hierarchy")
    for name, source in (("index.html", html), ("styles.css", css), ("app.js", js)):
        for marker in FORBIDDEN:
            if marker in source:
                findings.append(f"{name}: forbidden marker {marker}")
    required_tokens = ("--canvas", "--ink", "--accent", "--focus", "--space")
    for token in required_tokens:
        if token not in css:
            findings.append(f"styles.css: missing token {token}")
    for marker in ("aria-live", "prefers-reduced-motion", "/api/queue", "Idempotency-Key"):
        if marker not in html + css + js:
            findings.append(f"pilot: missing required behavior {marker}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PILOT_ROOT)
    arguments = parser.parse_args()
    findings = lint(arguments.root)
    if findings:
        for finding in findings:
            print(f"FAIL {finding}")
        return 1
    print("PASS phase8 frontend source lint")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
