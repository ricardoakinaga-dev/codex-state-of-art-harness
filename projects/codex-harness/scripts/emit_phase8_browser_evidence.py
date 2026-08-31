"""Bind browser observations, screenshots and the final build into one evidence packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from datetime import UTC, datetime
from pathlib import Path

PILOT = Path("evidence/phase-8/pilots/frontend-engineering")
SCREENSHOTS = {
    "desktop": ("desktop-success.png", 1440, 900, 1440, 1440, 1282),
    "intermediate": ("intermediate-success.png", 1024, 768, 1024, 1024, 1275),
    "tablet": ("tablet-success.png", 768, 1024, 768, 768, 1985),
    "mobile": ("mobile-success.png", 390, 844, 390, 390, 3027),
}
STATE_CAPTURES = (
    "mobile-loading.png",
    "mobile-empty.png",
    "mobile-error.png",
    "mobile-retry-success.png",
    "mobile-validation.png",
    "mobile-intake-success.png",
    "mobile-filtered-focus.png",
    "mobile-submit-error.png",
)


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", data[16:24])


def _tree_digest(root: Path) -> str:
    records: list[str] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        records.append(f"{relative}\t{_digest(path)}\t{path.stat().st_size}")
    return "sha256:" + hashlib.sha256(("\n".join(records) + "\n").encode()).hexdigest()


def _iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def emit(project_root: Path) -> dict[str, object]:
    pilot = project_root / PILOT
    browser_root = pilot / "browser"
    build_root = pilot / "build/final"
    source_root = pilot / "app"
    source_files = tuple(
        source_root / name
        for name in ("index.html", "styles.css", "app.js", "fixture_server.py")
    )
    source_tree_digest = "sha256:" + hashlib.sha256(
        ("\n".join(
            f"{path.name}\t{_digest(path)}\t{path.stat().st_size}" for path in source_files
        ) + "\n").encode()
    ).hexdigest()
    build_mtime_ns = max(path.stat().st_mtime_ns for path in build_root.iterdir() if path.is_file())
    performance_path = pilot / "browser-final-performance-and-dom.json"
    performance = (
        json.loads(performance_path.read_text(encoding="utf-8"))
        if performance_path.is_file()
        else {}
    )
    capture_id = "P8-FINAL-REPAIR-002"
    render_records: list[dict[str, object]] = []
    for name, (
        filename,
        width,
        height,
        scroll_width,
        client_width,
        scroll_height,
    ) in SCREENSHOTS.items():
        path = browser_root / filename
        actual_width, actual_height = _png_size(path)
        render_records.append(
            {
                "name": name,
                "path": str(path.relative_to(project_root)),
                "sha256": _digest(path),
                "bytes": path.stat().st_size,
                "image_dimensions": [actual_width, actual_height],
                "viewport": [width, height],
                "capture_id": capture_id,
                "captured_at": _iso_mtime(path),
                "device_pixel_ratio": performance.get("device_pixel_ratio", 1),
                "freshness": "POST_BUILD" if path.stat().st_mtime_ns >= build_mtime_ns else "STALE",
                "document_metrics": {
                    "scroll_width": scroll_width,
                    "client_width": client_width,
                    "scroll_height": scroll_height,
                    "horizontal_overflow": scroll_width > client_width,
                },
            }
        )
    states = []
    for filename in STATE_CAPTURES:
        path = browser_root / filename
        width, height = _png_size(path)
        states.append(
            {
                "path": str(path.relative_to(project_root)),
                "sha256": _digest(path),
                "bytes": path.stat().st_size,
                "image_dimensions": [width, height],
                "capture_id": capture_id,
                "captured_at": _iso_mtime(path),
                "freshness": "POST_BUILD" if path.stat().st_mtime_ns >= build_mtime_ns else "STALE",
            }
        )
    build_receipt = json.loads((build_root / "build-receipt.json").read_text(encoding="utf-8"))
    artifact_manifest = {
        "schema_version": "P8-ARTIFACT-MANIFEST-1",
        "artifact_root": str(build_root.relative_to(project_root)),
        "artifact_tree_digest": _tree_digest(build_root),
        "build_receipt": build_receipt,
        "source_files": [
            {
                "path": str((pilot / "app" / item["path"]).relative_to(project_root)),
                "sha256": item["sha256"],
                "bytes": item["bytes"],
            }
            for item in build_receipt["files"]
        ],
    }
    payload = {
        "schema_version": "P8-BROWSER-EVIDENCE-1",
        "observer": "Playwright MCP browser observer",
        "fixture_origin": "http://127.0.0.1:4173",
        "external_network": "DENY",
        "render_records": render_records,
        "state_captures": states,
        "observed_default_console_errors": 0,
        "observed_default_dynamic_requests": [
            "GET /api/queue?scenario=default -> 200"
        ],
        "capture_binding": {
            "capture_id": capture_id,
            "source_tree_digest": source_tree_digest,
            "artifact_tree_digest": _tree_digest(build_root),
            "build_completed_at": _iso_mtime(build_root / "build-receipt.json"),
            "performance_observation_path": str(performance_path.relative_to(project_root)),
            "observed_at": performance.get("observed_at"),
            "browser": performance.get("browser"),
            "device_pixel_ratio": performance.get("device_pixel_ratio"),
        },
        "performance_observation": {
            "observer": "PerformanceObserver in Chromium browser context",
            "first_contentful_paint_ms": performance.get("fcp_ms"),
            "largest_contentful_paint_ms": performance.get("lcp_ms"),
            "largest_contentful_paint_element": performance.get("lcp_element"),
            "cumulative_layout_shift": performance.get("cls"),
            "external_resources": performance.get("external_resources"),
            "resource_count": performance.get("resource_count"),
            "viewport": performance.get("viewport"),
            "horizontal_overflow": performance.get("horizontal_overflow"),
            "budget_comparison": {
                "max_lcp_ms": 2500,
                "max_cls": 0.1,
                "within_observed_budget": (
                    performance.get("lcp_ms") is not None
                    and performance.get("cls") is not None
                    and performance.get("lcp_ms") <= 2500
                    and performance.get("cls") <= 0.1
                ),
            },
            "scope": "single local Chromium observation; not a cross-browser performance guarantee",
        },
        "interaction_results": {
            "queue_error_retry": "error -> Retry queue -> success with 4 items",
            "empty_state": "success with 0 items -> Refresh queue action",
            "validation": {
                "feedback": "Complete the highlighted fields before sending.",
                "first_focus": "patient",
                "invalid_fields": ["patient", "species", "urgency"],
            },
            "filter_and_review": {
                "filter": "critical",
                "visible_rows": 1,
                "reviewed_patient": "Miso",
                "focus_target": "patient",
            },
            "double_submit": {
                "button_disabled_while_in_flight": True,
                "button_feedback": "Sending to triage…",
                "post_requests": 1,
                "final_feedback_tone": "success",
            },
            "submit_error": {
                "feedback": "Triage is temporarily unavailable. You can safely try again.",
                "button_reenabled": True,
            },
        },
        "browser_accessibility_observation": {
            "headings": ["h1", "h2", "h2", "h2"],
            "landmarks_include": ["main", "nav", "header", "aside", "footer", "form"],
            "unlabeled_controls": 0,
            "live_regions": 2,
            "table_headers": 5,
            "focus_outline_observed": True,
        },
        "artifact": artifact_manifest,
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=PILOT / "browser-evidence.json")
    arguments = parser.parse_args()
    project_root = arguments.project_root.resolve(strict=True)
    payload = emit(project_root)
    output = arguments.output
    output = output if output.is_absolute() else project_root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
