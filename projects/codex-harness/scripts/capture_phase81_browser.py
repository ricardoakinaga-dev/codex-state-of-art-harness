# ruff: noqa: E501
"""Capture catalog-specific Chromium evidence for P81-COMPOSE-013.

Run with a Python environment that provides Playwright. The browser binary is
pinned separately so the evidence does not depend on a downloaded browser.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, cast

from playwright.sync_api import Browser, Page, Route, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = PROJECT_ROOT / "evidence" / "phase-8.1"
ARTIFACT_ROOT = EVIDENCE_ROOT / "composition-run-013" / "frontend-artifact"
OUTPUT_ROOT = EVIDENCE_ROOT / "browser-018"
MANIFEST_PATH = EVIDENCE_ROOT / "browser-evidence-018.json"
COMPOSITION_RUN = "P81-COMPOSE-013"
CAPTURE_ID = "P81-BROWSER-018"
SERVER_RUN = "P81-SERVER-019"
PORT = 4196
BASE_URL = f"http://127.0.0.1:{PORT}/"
CHROME = Path("/usr/bin/google-chrome")
SOURCE_FILES = ("index.html", "styles.css", "app.js", "fixture_server.py")


def sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def artifact_digest() -> str:
    payload = "\n".join(f"{name}:{sha256(ARTIFACT_ROOT / name)}" for name in SOURCE_FILES)
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


def write_json(name: str, value: object) -> str:
    path = OUTPUT_ROOT / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return path.relative_to(EVIDENCE_ROOT).as_posix()


def wait_for_server() -> None:
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"{BASE_URL}api/health", timeout=0.2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("fixture server did not become ready")


def wait_state(page: Page, phase: str) -> None:
    page.wait_for_function("phase => window.__phase81?.getState().phase === phase", arg=phase)


def observation(page: Page, digest: str, **values: object) -> dict[str, object]:
    return {
        "capture_id": CAPTURE_ID,
        "run_id": COMPOSITION_RUN,
        "captured_at_ns": time.time_ns(),
        "artifact_digest": digest,
        "url": page.url,
        **values,
    }


def collect_layout(page: Page) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        page.evaluate(
            """() => {
          const submit = document.querySelector('#submit-intake');
          const cta = document.querySelector('.page-intro a[href="#intake"]');
          const queue = document.querySelector('.queue-panel');
          const intake = document.querySelector('.intake-panel');
          const queueBox = queue?.getBoundingClientRect();
          const intakeBox = intake?.getBoundingClientRect();
          const overlap = queueBox && intakeBox && !(
            queueBox.right <= intakeBox.left || intakeBox.right <= queueBox.left ||
            queueBox.bottom <= intakeBox.top || intakeBox.bottom <= queueBox.top
          );
          const labels = [...document.querySelectorAll('#intake-form label')].map(label => ({
            text: label.innerText.trim(),
            width: label.getBoundingClientRect().width,
            height: label.getBoundingClientRect().height,
          }));
          const critical = [...document.querySelectorAll('#patient,#species,#urgency,#notes,#submit-intake,#refresh-queue')].map(control => ({
            id: control.id,
            width: control.getBoundingClientRect().width,
            height: control.getBoundingClientRect().height,
            clipped: control.scrollWidth > control.clientWidth || control.scrollHeight > control.clientHeight,
          }));
          const stateBox = document.querySelector('#queue-state')?.getBoundingClientRect();
          return {
            viewport: {width: innerWidth, height: innerHeight},
            documentWidth: document.documentElement.scrollWidth,
            bodyWidth: document.body.scrollWidth,
            overflowX: document.documentElement.scrollWidth > innerWidth,
            ctaPresent: Boolean(cta),
            ctaBox: cta ? cta.getBoundingClientRect().toJSON() : null,
            submitPresent: Boolean(submit),
            submitBox: submit ? submit.getBoundingClientRect().toJSON() : null,
            panelOverlap: Boolean(overlap),
            labels,
            critical,
            stateVisible: Boolean(stateBox && stateBox.width > 0 && stateBox.height > 0),
            navigationUsable: [...document.querySelectorAll('.nav-link')].every(link => {
              const box = link.getBoundingClientRect();
              return box.width > 0 && box.height > 0;
            }),
            marker: document.body.dataset.phase81Composition || null,
          };
        }"""
        ),
    )


def new_page(browser: Browser, viewport: tuple[int, int]) -> tuple[Any, Page, list[dict[str, str]]]:
    context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
    page = context.new_page()
    messages: list[dict[str, str]] = []
    page.on("console", lambda msg: messages.append({"type": msg.type, "text": msg.text}))
    page.on("pageerror", lambda error: messages.append({"type": "pageerror", "text": str(error)}))
    return context, page, messages


def rgb(value: str) -> tuple[int, int, int]:
    channels = value.removeprefix("rgb(").removesuffix(")").split(",")
    return tuple(int(float(channel.strip())) for channel in channels[:3])  # type: ignore[return-value]


def luminance(color: tuple[int, int, int]) -> float:
    channels = []
    for channel in color:
        normalized = channel / 255
        channels.append(
            normalized / 12.92 if normalized <= 0.04045 else ((normalized + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def ratio(first: str, second: str) -> float:
    light, dark = sorted((luminance(rgb(first)), luminance(rgb(second))), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def main() -> int:
    if OUTPUT_ROOT.exists() or MANIFEST_PATH.exists():
        raise RuntimeError("fresh browser evidence paths already exist")
    if not CHROME.is_file():
        raise RuntimeError("pinned Chrome executable is unavailable")
    digest = artifact_digest()
    OUTPUT_ROOT.mkdir(parents=True)
    started_ns = time.time_ns()
    server = subprocess.Popen(
        [sys.executable, str(ARTIFACT_ROOT / "fixture_server.py"), "--port", str(PORT)],
        cwd=ARTIFACT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    checks: list[dict[str, object]] = []
    captures: list[dict[str, str]] = []
    observations: dict[str, str] = {}

    def record(check_id: str, passed: bool, evidence: str, detail: str) -> None:
        if any(check["id"] == check_id for check in checks):
            raise RuntimeError(f"duplicate browser check id: {check_id}")
        checks.append(
            {"id": check_id, "passed": bool(passed), "evidence": evidence, "detail": detail}
        )

    try:
        wait_for_server()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=str(CHROME),
                headless=True,
                args=["--disable-background-networking", "--disable-component-update"],
            )
            browser_version = browser.version

            # Default desktop, provenance, clean console, layout and performance.
            context, page, messages = new_page(browser, (1440, 900))
            response = page.goto(
                f"{BASE_URL}?scenario=default&capture=p81-013", wait_until="domcontentloaded"
            )
            wait_state(page, "success")
            page.locator(".page-intro a[href='#intake']").scroll_into_view_if_needed()
            layout = collect_layout(page)
            perf = page.evaluate(
                """() => ({
                  resources: performance.getEntriesByType('resource').map(e => e.name),
                  paints: performance.getEntriesByType('paint').map(e => ({name: e.name, startTime: e.startTime})),
                  domContentLoadedMs: performance.getEntriesByType('navigation')[0]?.domContentLoadedEventEnd || null,
                  loadMs: performance.getEntriesByType('navigation')[0]?.loadEventEnd || null,
                  state: window.__phase81.getState(),
                })"""
            )
            default_path = write_json(
                "default-runtime.json",
                observation(page, digest, layout=layout, performance=perf, console=messages),
            )
            observations["default"] = default_path
            screenshot = OUTPUT_ROOT / "desktop-success-1440x900.png"
            page.screenshot(path=str(screenshot), full_page=True)
            captures.append(
                {
                    "path": screenshot.relative_to(EVIDENCE_ROOT).as_posix(),
                    "sha256": sha256(screenshot),
                    "kind": "screenshot",
                }
            )
            binding = response.headers.get("x-phase81-artifact-digest") if response else None
            record(
                "P8-EVAL-012",
                perf["state"]["phase"] == "success" and len(perf["state"]["items"]) == 4,
                default_path,
                "default queue rendered four cases",
            )
            record(
                "P8-EVAL-021",
                not layout["overflowX"] and layout["ctaPresent"],
                default_path,
                "1440x900 has no horizontal overflow and CTA exists",
            )
            record(
                "provenance.dom_marker",
                layout["marker"] == COMPOSITION_RUN,
                default_path,
                "host-written body marker is present",
            )
            record(
                "provenance.server_header",
                binding == digest,
                default_path,
                "document response binds the canonical artifact digest",
            )
            same_origin = all(resource.startswith(BASE_URL) for resource in perf["resources"])
            record(
                "supplemental.local_resources",
                same_origin and len(perf["resources"]) <= 4,
                default_path,
                "all runtime resources are local and bounded",
            )
            record(
                "supplemental.clean_console",
                not messages,
                default_path,
                "default scenario emitted no console errors or warnings",
            )
            context.close()

            # Required intermediate and portrait widths.
            responsive_ids = {
                "intermediate": "P8-EVAL-022",
                "portrait": "P8-EVAL-023",
                "mobile": "P8-EVAL-024",
                "reflow": "P8-EVAL-027",
            }
            for label, viewport, query, screenshot_name in (
                (
                    "intermediate",
                    (1024, 768),
                    "?scenario=default&urgency=urgent",
                    "intermediate-urgent-1024x768.png",
                ),
                ("portrait", (768, 1024), "?scenario=empty", "portrait-empty-768x1024.png"),
                (
                    "mobile",
                    (390, 844),
                    "?scenario=default&urgency=critical",
                    "mobile-critical-390x844.png",
                ),
                ("reflow", (195, 844), "?scenario=default", "reflow-200-percent-195x844.png"),
            ):
                context, page, messages = new_page(browser, viewport)
                page.goto(BASE_URL + query, wait_until="domcontentloaded")
                wait_state(page, "success")
                page_scale = None
                if label == "reflow":
                    session = context.new_cdp_session(page)
                    session.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 2})
                    page_scale = page.evaluate("visualViewport.scale")
                page.locator("#submit-intake").scroll_into_view_if_needed()
                page.locator("#submit-intake").focus()
                measured = collect_layout(page)
                measured["focused"] = page.evaluate("document.activeElement?.id")
                measured["focusOutline"] = page.locator("#submit-intake").evaluate(
                    "e => getComputedStyle(e).outline"
                )
                measured["pageScaleFactor"] = page_scale
                if label == "reflow":
                    measured["queueValues"] = page.evaluate(
                        """() => [...document.querySelectorAll('#queue-body td')].map(cell => ({
                          label: cell.dataset.label,
                          text: cell.innerText.trim(),
                          clipped: cell.scrollWidth > cell.clientWidth || cell.scrollHeight > cell.clientHeight,
                        }))"""
                    )
                path = write_json(
                    f"{label}-runtime.json", observation(page, digest, **measured, console=messages)
                )
                observations[label] = path
                screenshot = OUTPUT_ROOT / screenshot_name
                if label == "reflow":
                    session.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 1})
                page.evaluate("document.activeElement?.blur()")
                page.evaluate("scrollTo(0, 0)")
                page.screenshot(path=str(screenshot), full_page=True)
                captures.append(
                    {
                        "path": screenshot.relative_to(EVIDENCE_ROOT).as_posix(),
                        "sha256": sha256(screenshot),
                        "kind": "screenshot",
                    }
                )
                record(
                    responsive_ids[label],
                    not measured["overflowX"]
                    and measured["submitPresent"]
                    and not measured["panelOverlap"]
                    and measured["stateVisible"]
                    and measured["navigationUsable"]
                    and all(item["text"] and item["width"] > 0 for item in measured["labels"])
                    and all(
                        item["width"] > 0 and item["height"] > 0 and not item["clipped"]
                        for item in measured["critical"]
                    )
                    and (
                        label != "reflow"
                        or (
                            measured["pageScaleFactor"] == 2
                            and not any(item["clipped"] for item in measured["queueValues"])
                            and all(item["text"] for item in measured["queueValues"])
                        )
                    ),
                    path,
                    f"{viewport[0]}x{viewport[1]} has no overflow and the submit action is reachable",
                )
                context.close()

            # Loading state.
            context, page, messages = new_page(browser, (1440, 900))
            page.goto(f"{BASE_URL}?scenario=loading", wait_until="domcontentloaded")
            loading = page.evaluate(
                """() => ({
                  state: __phase81.getState(),
                  busy: document.querySelector('.queue-panel').getAttribute('aria-busy'),
                  announced: document.querySelector('#queue-state').textContent,
                  skeletons: document.querySelectorAll('.loading-row').length,
                  panelHeight: document.querySelector('.queue-panel').getBoundingClientRect().height,
                })"""
            )
            wait_state(page, "success")
            loaded = page.evaluate(
                """() => ({
                  state: __phase81.getState(),
                  busy: document.querySelector('.queue-panel').getAttribute('aria-busy'),
                  announced: document.querySelector('#queue-state').textContent,
                  rows: document.querySelectorAll('#queue-body tr').length,
                  panelHeight: document.querySelector('.queue-panel').getBoundingClientRect().height,
                })"""
            )
            loading_path = write_json(
                "loading-runtime.json",
                observation(page, digest, initial=loading, replaced=loaded, console=messages),
            )
            observations["loading"] = loading_path
            record(
                "P8-EVAL-011",
                loading["state"]["phase"] == "loading"
                and loading["busy"] == "true"
                and loading["skeletons"] == 3
                and loading["announced"] == "Loading current queue…"
                and loaded["state"]["phase"] == "success"
                and loaded["busy"] == "false"
                and loaded["rows"] == 4
                and loaded["announced"].startswith("4 active cases")
                and loading["panelHeight"] > 0
                and loaded["panelHeight"] > 0,
                loading_path,
                "loading is announced with stable geometry and is replaced by four current rows",
            )
            context.close()

            # Empty state.
            context, page, messages = new_page(browser, (768, 1024))
            page.goto(f"{BASE_URL}?scenario=empty", wait_until="domcontentloaded")
            wait_state(page, "success")
            empty = page.evaluate(
                "() => ({state: __phase81.getState(), queueState: document.querySelector('#queue-state').textContent, card: document.querySelector('.state-card').innerText})"
            )
            empty_path = write_json(
                "empty-runtime.json", observation(page, digest, **empty, console=messages)
            )
            observations["empty"] = empty_path
            record(
                "P8-EVAL-013",
                not empty["state"]["items"] and empty["queueState"] == "No active cases",
                empty_path,
                "empty queue renders an actionable empty state",
            )
            context.close()

            # Server failure and keyboard recovery.
            context, page, messages = new_page(browser, (1440, 900))
            page.goto(f"{BASE_URL}?scenario=error", wait_until="domcontentloaded")
            wait_state(page, "error")
            failed = page.evaluate(
                "() => ({state: __phase81.getState(), alert: document.querySelector('[role=alert]').innerText, retry: document.querySelector('[data-recovery-action=true]').textContent})"
            )
            error_path = write_json(
                "queue-error-runtime.json", observation(page, digest, **failed, console=messages)
            )
            observations["queue_error"] = error_path
            record(
                "P8-EVAL-014",
                failed["state"]["phase"] == "error" and failed["retry"].strip() == "Try again",
                error_path,
                "queue failure exposes a recovery action",
            )
            page.locator("[data-recovery-action=true]").focus()
            page.keyboard.press("Enter")
            wait_state(page, "success")
            recovered = page.evaluate(
                "() => ({state: __phase81.getState(), focused: document.activeElement?.id, queueState: document.querySelector('#queue-state').textContent})"
            )
            recovered_path = write_json(
                "queue-recovery-runtime.json",
                observation(page, digest, **recovered, console=messages),
            )
            observations["queue_recovery"] = recovered_path
            record(
                "P8-EVAL-015",
                recovered["state"]["phase"] == "success"
                and recovered["focused"] == "refresh-queue",
                recovered_path,
                "keyboard retry recovers and moves focus predictably",
            )
            context.close()

            # Client validation.
            context, page, messages = new_page(browser, (1440, 900))
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            page.locator("#submit-intake").click()
            invalid = page.evaluate(
                "() => ({invalid: [...document.querySelectorAll('[aria-invalid=true]')].map(e => e.id), focused: document.activeElement?.id, feedback: document.querySelector('#intake-feedback').textContent})"
            )
            invalid_path = write_json(
                "validation-runtime.json", observation(page, digest, **invalid, console=messages)
            )
            observations["validation"] = invalid_path
            record(
                "supplemental.blank_submit",
                invalid["invalid"] == ["patient", "species", "urgency"]
                and invalid["focused"] == "patient",
                invalid_path,
                "blank submit marks required fields and focuses the first error",
            )
            context.close()

            # Valid submission: observe the in-flight and success states.
            context, page, messages = new_page(browser, (1440, 900))
            page.goto(f"{BASE_URL}?scenario=submit-loading", wait_until="domcontentloaded")
            wait_state(page, "success")
            page.locator("#patient").fill("Nova")
            page.locator("#species").select_option("dog")
            page.locator("#urgency").select_option("urgent")
            page.locator("#submit-intake").click()
            page.wait_for_function("() => __phase81.getState().submitting")
            submitting = page.evaluate(
                "() => ({state: __phase81.getState(), disabled: document.querySelector('#submit-intake').disabled, text: document.querySelector('#submit-intake').textContent, feedback: document.querySelector('#intake-feedback').textContent})"
            )
            submitting_path = write_json(
                "submission-loading-runtime.json",
                observation(page, digest, **submitting, console=messages),
            )
            observations["submission_loading"] = submitting_path
            record(
                "supplemental.submitting",
                submitting["state"]["submitting"] and submitting["disabled"],
                submitting_path,
                "submission disables the action and announces progress",
            )
            page.wait_for_function("() => __phase81.getState().requestNumber === 1")
            success = page.evaluate(
                "() => ({state: __phase81.getState(), values: Object.fromEntries(new FormData(document.querySelector('#intake-form'))), focused: document.activeElement?.id})"
            )
            success_path = write_json(
                "submission-success-runtime.json",
                observation(page, digest, **success, console=messages),
            )
            observations["submission_success"] = success_path
            record(
                "supplemental.submission_success",
                success["state"]["feedbackTone"] == "success"
                and success["focused"] == "patient"
                and not any(success["values"].values()),
                success_path,
                "successful intake resets the form, reports a reference and focuses the first field",
            )
            context.close()

            # Lost response followed by a safe retry of the same idempotency key.
            context, page, messages = new_page(browser, (1440, 900))
            intercepted: list[dict[str, Any]] = []

            def intercept(route: Route) -> None:
                response = route.fetch()
                body = response.json()
                intercepted.append(
                    {
                        "key": route.request.headers.get("idempotency-key"),
                        "status": response.status,
                        "body": body,
                    }
                )
                if len(intercepted) == 1:
                    route.abort("failed")
                else:
                    route.fulfill(response=response)

            page.route("**/api/intakes?*", intercept)
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            receipts_before_retry = page.evaluate(
                "async () => (await (await fetch('/api/receipts')).json())"
            )
            page.locator("#patient").fill("Echo")
            page.locator("#species").select_option("cat")
            page.locator("#urgency").select_option("critical")
            page.locator("#submit-intake").click()
            page.wait_for_function(
                "() => !__phase81.getState().submitting && __phase81.getState().feedbackTone === 'error'"
            )
            first_failure = page.evaluate("__phase81.getState().feedback")
            page.locator("#submit-intake").click()
            page.wait_for_function("() => __phase81.getState().requestNumber === 1")
            retry_state = page.evaluate("__phase81.getState()")
            receipts_after_retry = page.evaluate(
                "async () => (await (await fetch('/api/receipts')).json())"
            )
            idempotency: dict[str, Any] = {
                "firstFailure": first_failure,
                "requests": intercepted,
                "sameKey": len(intercepted) == 2 and intercepted[0]["key"] == intercepted[1]["key"],
                "sameIntake": len(intercepted) == 2
                and intercepted[0]["body"].get("intake_id")
                == intercepted[1]["body"].get("intake_id"),
                "receiptsBefore": receipts_before_retry,
                "receiptsAfter": receipts_after_retry,
                "finalState": retry_state,
            }
            idempotency_path = write_json(
                "idempotent-retry-runtime.json",
                observation(page, digest, **idempotency, console=messages),
            )
            observations["idempotency"] = idempotency_path
            record(
                "supplemental.submission_failure",
                "safely try again" in first_failure.casefold()
                and "failed to fetch" not in first_failure.casefold(),
                idempotency_path,
                "lost response produces actionable retry feedback",
            )
            record(
                "supplemental.idempotent_retry",
                idempotency["sameKey"]
                and idempotency["sameIntake"]
                and intercepted[1]["body"]["status"] == "duplicate"
                and receipts_after_retry["stored_creation_count"]
                == receipts_before_retry["stored_creation_count"] + 1
                and [
                    receipt["outcome"]
                    for receipt in receipts_after_retry["attempt_receipts"][
                        len(receipts_before_retry["attempt_receipts"]) :
                    ]
                ]
                == ["created", "duplicate"],
                idempotency_path,
                "retry reuses the key and server record instead of duplicating intake",
            )
            context.close()

            # An edited ambiguous draft gets a new key; forced key reuse is rejected.
            context, page, messages = new_page(browser, (1440, 900))
            changed_draft_requests: list[dict[str, Any]] = []

            def intercept_changed_draft(route: Route) -> None:
                response = route.fetch()
                changed_draft_requests.append(
                    {
                        "key": route.request.headers.get("idempotency-key"),
                        "request": json.loads(route.request.post_data or "{}"),
                        "status": response.status,
                        "response": response.json(),
                    }
                )
                if len(changed_draft_requests) == 1:
                    route.abort("failed")
                else:
                    route.fulfill(response=response)

            page.route("**/api/intakes?*", intercept_changed_draft)
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            changed_receipts_before = page.evaluate(
                "async () => (await (await fetch('/api/receipts')).json())"
            )
            page.locator("#patient").fill("Before edit")
            page.locator("#species").select_option("dog")
            page.locator("#urgency").select_option("urgent")
            page.locator("#submit-intake").click()
            page.wait_for_function(
                "() => !__phase81.getState().submitting && __phase81.getState().feedbackTone === 'error'"
            )
            page.locator("#patient").fill("After edit")
            page.locator("#submit-intake").click()
            page.wait_for_function("() => __phase81.getState().requestNumber === 1")
            first_key = changed_draft_requests[0]["key"]
            forced_conflict = page.evaluate(
                """async ({key}) => {
                  const response = await fetch('/api/intakes', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', 'Idempotency-Key': key},
                    body: JSON.stringify({patient: 'Forced conflict', species: 'dog', urgency: 'urgent', notes: ''}),
                  });
                  return {status: response.status, body: await response.json()};
                }""",
                {"key": first_key},
            )
            changed_receipts_after = page.evaluate(
                "async () => (await (await fetch('/api/receipts')).json())"
            )
            changed_draft = {
                "requests": changed_draft_requests,
                "receiptsBefore": changed_receipts_before,
                "receiptsAfter": changed_receipts_after,
                "forcedConflict": forced_conflict,
            }
            changed_draft_path = write_json(
                "idempotency-payload-binding-runtime.json",
                observation(page, digest, **changed_draft, console=messages),
            )
            observations["idempotency_payload"] = changed_draft_path
            record(
                "supplemental.idempotency_payload_binding",
                len(changed_draft_requests) == 2
                and changed_draft_requests[0]["key"] != changed_draft_requests[1]["key"]
                and changed_draft_requests[0]["response"]["intake_id"]
                != changed_draft_requests[1]["response"]["intake_id"]
                and forced_conflict["status"] == 409
                and changed_receipts_after["stored_creation_count"]
                == changed_receipts_before["stored_creation_count"] + 2
                and [
                    item["outcome"]
                    for item in changed_receipts_after["attempt_receipts"][
                        len(changed_receipts_before["attempt_receipts"]) :
                    ]
                ]
                == ["created", "created", "conflict"],
                changed_draft_path,
                "edited retry uses a new key; explicit same-key/different-payload reuse returns 409",
            )
            context.close()

            # URL-initialized state, refresh, history, and invalid parameter normalization.
            context, page, messages = new_page(browser, (1440, 900))
            page.goto(f"{BASE_URL}?urgency=critical", wait_until="domcontentloaded")
            wait_state(page, "success")
            initialized = page.evaluate(
                "() => ({selected: __phase81.getState().selectedUrgency, patients: [...document.querySelectorAll('.patient-copy strong')].map(e => e.textContent), search: location.search})"
            )
            page.reload(wait_until="domcontentloaded")
            wait_state(page, "success")
            refreshed = page.evaluate(
                "() => ({selected: __phase81.getState().selectedUrgency, search: location.search})"
            )
            page.locator("#urgency-filter").select_option("urgent")
            urgent = page.evaluate(
                "() => ({selected: __phase81.getState().selectedUrgency, search: location.search})"
            )
            page.go_back(wait_until="domcontentloaded")
            wait_state(page, "success")
            backed = page.evaluate(
                "() => ({selected: __phase81.getState().selectedUrgency, search: location.search})"
            )
            url_state = {
                "initialized": initialized,
                "refreshed": refreshed,
                "urgent": urgent,
                "backed": backed,
            }
            url_path = write_json(
                "url-state-runtime.json", observation(page, digest, **url_state, console=messages)
            )
            observations["url_state"] = url_path
            page.goto(f"{BASE_URL}?urgency=not-valid", wait_until="domcontentloaded")
            wait_state(page, "success")
            invalid_url = page.evaluate(
                "() => ({selected: __phase81.getState().selectedUrgency, search: location.search})"
            )
            invalid_url_path = write_json(
                "url-invalid-runtime.json",
                observation(page, digest, **invalid_url, console=messages),
            )
            observations["url_invalid"] = invalid_url_path
            url_complete_path = write_json(
                "url-complete-runtime.json",
                observation(
                    page,
                    digest,
                    **url_state,
                    invalid=invalid_url,
                    componentEvidence=[url_path, invalid_url_path],
                    console=messages,
                ),
            )
            observations["url_complete"] = url_complete_path
            record(
                "P8-EVAL-019",
                initialized["selected"] == "critical"
                and initialized["patients"] == ["Miso"]
                and refreshed["selected"] == "critical"
                and urgent["selected"] == "urgent"
                and backed["selected"] == "critical"
                and invalid_url["selected"] == "all"
                and "urgency" not in invalid_url["search"],
                url_complete_path,
                "URL filter initializes, survives refresh/history, and normalizes invalid state",
            )
            context.close()

            # Stale response suppression: slower A starts first, faster B wins.
            context, page, messages = new_page(browser, (1440, 900))
            requests: list[str] = []
            page.on(
                "request",
                lambda request: (
                    requests.append(request.url)
                    if "/api/queue?scenario=stale-response" in request.url
                    else None
                ),
            )
            page.goto(f"{BASE_URL}?scenario=stale-response", wait_until="domcontentloaded")
            page.evaluate("__phase81.reload()")
            page.wait_for_timeout(10)
            page.evaluate("__phase81.reload()")
            wait_state(page, "success")
            page.wait_for_timeout(300)
            stale = page.evaluate(
                "() => ({state: __phase81.getState(), patients: [...document.querySelectorAll('.patient-copy strong')].map(e => e.textContent)})"
            )
            stale_path = write_json(
                "stale-response-runtime.json",
                observation(page, digest, requests=requests, **stale, console=messages),
            )
            observations["stale"] = stale_path
            record(
                "P8-EVAL-016",
                stale["patients"] == ["Fresh B"] and len(requests) == 2,
                stale_path,
                "later request B remains visible after delayed response A completes",
            )
            context.close()

            # Rendered semantics, labels, headings, landmarks, non-color cues and contrast.
            context, page, messages = new_page(browser, (1440, 900))
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            semantics = page.evaluate(
                """() => ({
                  labels: ['patient','species','urgency','notes','urgency-filter'].map(id => {
                    const control = document.getElementById(id);
                    const label = document.querySelector(`label[for="${id}"]`) || control?.closest('label');
                    return {id, label: label?.innerText.trim() || null, associated: Boolean(label && control)};
                  }),
                  headings: [...document.querySelectorAll('h1,h2,h3')].map(e => ({level: e.tagName, text: e.innerText})),
                  landmarks: {
                    banner: [...document.querySelectorAll('header')].length,
                    navigation: [...document.querySelectorAll('nav')].map(e => e.getAttribute('aria-label')),
                    main: [...document.querySelectorAll('main')].length,
                    contentinfo: [...document.querySelectorAll('footer')].length,
                  },
                  urgencyCues: [...document.querySelectorAll('.triage-label')].map(e => ({
                    text: e.textContent.trim(),
                    level: e.dataset.level,
                    shape: getComputedStyle(e, '::before').borderRadius,
                    markerWidth: getComputedStyle(e, '::before').width,
                  })),
                  colors: {surface: getComputedStyle(document.querySelector('#patient')).backgroundColor, text: getComputedStyle(document.querySelector('#patient')).color, border: getComputedStyle(document.querySelector('#patient')).borderColor},
                })"""
            )
            semantics["contrast"] = {
                "text": ratio(semantics["colors"]["text"], semantics["colors"]["surface"]),
                "border": ratio(semantics["colors"]["border"], semantics["colors"]["surface"]),
            }
            accessibility_path = write_json(
                "accessibility-runtime.json",
                observation(page, digest, **semantics, console=messages),
            )
            observations["accessibility"] = accessibility_path
            record(
                "P8-EVAL-029",
                semantics["landmarks"]
                == {
                    "banner": 1,
                    "navigation": ["Clinic workspace"],
                    "main": 1,
                    "contentinfo": 1,
                },
                accessibility_path,
                "rendered route has one banner, named navigation, main and contentinfo",
            )
            record(
                "P8-EVAL-030",
                [item["level"] for item in semantics["headings"]] == ["H1", "H2", "H2", "H2"],
                accessibility_path,
                "rendered headings form one H1 followed by logical H2 sections",
            )
            record(
                "P8-EVAL-031",
                all(item["label"] and item["associated"] for item in semantics["labels"]),
                accessibility_path,
                "every intake/filter control has visible or programmatically associated label text",
            )
            record(
                "P8-EVAL-035",
                len(semantics["urgencyCues"]) == 4
                and all(item["text"] and item["level"] for item in semantics["urgencyCues"])
                and all(item["markerWidth"] == "6px" for item in semantics["urgencyCues"]),
                accessibility_path,
                "urgency is conveyed by explicit text plus a persistent circular marker",
            )
            record(
                "supplemental.contrast",
                semantics["contrast"]["text"] >= 4.5 and semantics["contrast"]["border"] >= 3,
                accessibility_path,
                "text and control boundary contrast pass bounded WCAG-oriented thresholds",
            )
            context.close()

            # Rapid double submit: one POST and one stored creation.
            context, page, messages = new_page(browser, (1440, 900))
            page.goto(f"{BASE_URL}?scenario=submit-loading", wait_until="domcontentloaded")
            wait_state(page, "success")
            before_receipts = page.evaluate(
                "async () => (await (await fetch('/api/receipts')).json())"
            )
            posts: list[str] = []
            page.on(
                "request",
                lambda request: (
                    posts.append(request.url)
                    if request.method == "POST" and "/api/intakes" in request.url
                    else None
                ),
            )
            page.locator("#patient").fill("Double")
            page.locator("#species").select_option("dog")
            page.locator("#urgency").select_option("urgent")
            page.evaluate(
                "() => { const b = document.querySelector('#submit-intake'); b.click(); b.click(); }"
            )
            page.wait_for_function("() => __phase81.getState().requestNumber === 1")
            after_receipts = page.evaluate(
                "async () => (await (await fetch('/api/receipts')).json())"
            )
            double_submit = {
                "postRequests": posts,
                "before": before_receipts,
                "after": after_receipts,
                "finalState": page.evaluate("__phase81.getState()"),
            }
            double_path = write_json(
                "double-submit-runtime.json",
                observation(page, digest, **double_submit, console=messages),
            )
            observations["double_submit"] = double_path
            record(
                "P8-EVAL-017",
                len(posts) == 1
                and after_receipts["stored_creation_count"]
                == before_receipts["stored_creation_count"] + 1
                and len(after_receipts["attempt_receipts"])
                == len(before_receipts["attempt_receipts"]) + 1
                and after_receipts["attempt_receipts"][-1]["outcome"] == "created",
                double_path,
                "two synchronous clicks produce one POST receipt and one stored creation",
            )
            context.close()

            # Local derived filtering preserves the immutable fetched source list.
            context, page, messages = new_page(browser, (1440, 900))
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            filter_before = page.evaluate(
                "() => ({items: __phase81.getState().items.map(x => ({...x})), frozen: Object.isFrozen(__phase81.getState().items)})"
            )
            page.locator("#urgency-filter").select_option("critical")
            filtered = page.evaluate(
                "() => ({source: __phase81.getState().items.map(x => ({...x})), visible: [...document.querySelectorAll('.patient-copy strong')].map(e => e.textContent)})"
            )
            page.locator("#urgency-filter").select_option("all")
            restored = page.evaluate(
                "() => [...document.querySelectorAll('.patient-copy strong')].map(e => e.textContent)"
            )
            filter_path = write_json(
                "local-filter-runtime.json",
                observation(
                    page,
                    digest,
                    before=filter_before,
                    filtered=filtered,
                    restored=restored,
                    console=messages,
                ),
            )
            observations["local_filter"] = filter_path
            record(
                "P8-EVAL-018",
                filter_before["frozen"]
                and filtered["source"] == filter_before["items"]
                and filtered["visible"] == ["Miso"]
                and len(restored) == 4,
                filter_path,
                "urgency filtering derives one visible row without mutating four source records",
            )
            context.close()

            # Server 422 mapping preserves the browser draft and names the patient field.
            context, page, messages = new_page(browser, (1440, 900))
            response_statuses: list[int] = []

            def force_server_patient_error(route: Route) -> None:
                body = json.loads(route.request.post_data or "{}")
                body["patient"] = "X"
                route.continue_(post_data=json.dumps(body))

            page.route("**/api/intakes?*", force_server_patient_error)
            page.on(
                "response",
                lambda response: (
                    response_statuses.append(response.status)
                    if "/api/intakes" in response.url
                    else None
                ),
            )
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            page.locator("#patient").fill("Miso")
            page.locator("#species").select_option("cat")
            page.locator("#urgency").select_option("critical")
            page.locator("#notes").fill("Draft remains in the form")
            page.locator("#submit-intake").click()
            page.wait_for_function(
                "() => document.querySelector('#patient').getAttribute('aria-invalid') === 'true'"
            )
            server_validation = page.evaluate(
                """() => ({
                  patient: document.querySelector('#patient').value,
                  species: document.querySelector('#species').value,
                  urgency: document.querySelector('#urgency').value,
                  notes: document.querySelector('#notes').value,
                  patientError: document.querySelector('#patient-error').textContent,
                  patientInvalid: document.querySelector('#patient').getAttribute('aria-invalid'),
                  feedback: document.querySelector('#intake-feedback').textContent,
                })"""
            )
            server_validation_path = write_json(
                "server-validation-runtime.json",
                observation(
                    page,
                    digest,
                    statuses=response_statuses,
                    state=server_validation,
                    console=messages,
                ),
            )
            observations["server_validation"] = server_validation_path
            record(
                "P8-EVAL-020",
                response_statuses == [422]
                and server_validation["patient"] == "Miso"
                and server_validation["species"] == "cat"
                and server_validation["urgency"] == "critical"
                and server_validation["notes"] == "Draft remains in the form"
                and server_validation["patientInvalid"] == "true"
                and "2–60" in server_validation["patientError"],
                server_validation_path,
                "fixture 422 maps to patient and preserves every browser draft value",
            )
            context.close()

            # Intermediate-width translated/copy-stress heading.
            context, page, messages = new_page(browser, (1024, 768))
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            long_heading_text = (
                "Prepare the emergency reception space for the next urgently arriving patient"
            )
            long_heading = page.evaluate(
                """text => {
                  const heading = document.querySelector('h1');
                  heading.textContent = text;
                  const box = heading.getBoundingClientRect();
                  return {
                    text: heading.textContent,
                    box: box.toJSON(),
                    scrollWidth: heading.scrollWidth,
                    clientWidth: heading.clientWidth,
                    scrollHeight: heading.scrollHeight,
                    clientHeight: heading.clientHeight,
                    overflow: getComputedStyle(heading).overflow,
                    documentWidth: document.documentElement.scrollWidth,
                    viewportWidth: innerWidth,
                  };
                }""",
                long_heading_text,
            )
            long_heading_shot = OUTPUT_ROOT / "intermediate-long-heading-1024x768.png"
            page.screenshot(path=str(long_heading_shot), full_page=True)
            captures.append(
                {
                    "path": long_heading_shot.relative_to(EVIDENCE_ROOT).as_posix(),
                    "sha256": sha256(long_heading_shot),
                    "kind": "screenshot",
                }
            )
            long_heading_path = write_json(
                "long-heading-runtime.json",
                observation(page, digest, **long_heading, console=messages),
            )
            observations["long_heading"] = long_heading_path
            record(
                "P8-EVAL-025",
                long_heading["text"] == long_heading_text
                and long_heading["documentWidth"] <= long_heading["viewportWidth"]
                and long_heading["scrollWidth"] <= long_heading["clientWidth"]
                and long_heading["overflow"] == "visible"
                and long_heading["scrollHeight"] - long_heading["clientHeight"] <= 4,
                long_heading_path,
                "translated-length heading wraps at 1024px without horizontal or internal clipping",
            )
            context.close()

            # Mobile table transformation retains every operational field in reading order.
            context, page, messages = new_page(browser, (390, 844))
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            mobile_rows = page.evaluate(
                """() => [...document.querySelectorAll('#queue-body tr')].map(row =>
                  [...row.querySelectorAll('td')].map(cell => ({
                    label: cell.dataset.label,
                    text: cell.innerText.trim(),
                    clipped: cell.scrollWidth > cell.clientWidth || cell.scrollHeight > cell.clientHeight,
                  })))"""
            )
            mobile_semantics_path = write_json(
                "mobile-table-semantics-runtime.json",
                observation(page, digest, rows=mobile_rows, console=messages),
            )
            observations["mobile_table_semantics"] = mobile_semantics_path
            expected_labels = ["Patient", "Species", "Triage", "Waiting", "Action"]
            record(
                "P8-EVAL-026",
                len(mobile_rows) == 4
                and all([cell["label"] for cell in row] == expected_labels for row in mobile_rows)
                and all(
                    cell["text"] and not cell["clipped"] for row in mobile_rows for cell in row
                ),
                mobile_semantics_path,
                "mobile rows retain full patient, species, urgency, wait and action values",
            )
            context.close()

            # Actual Tab focus path across critical controls and visible outlines.
            context, page, messages = new_page(browser, (1440, 900))
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            focus_path: list[dict[str, Any]] = []
            for _ in range(32):
                page.keyboard.press("Tab")
                focused = page.evaluate(
                    """() => {
                      const e = document.activeElement;
                      return {id: e?.id || null, tag: e?.tagName || null, href: e?.getAttribute?.('href') || null, outline: e ? getComputedStyle(e).outline : null};
                    }"""
                )
                focus_path.append(focused)
                if focused["id"] == "submit-intake":
                    break
            critical_focus_ids = [
                item["id"]
                for item in focus_path
                if item["id"] in {"patient", "species", "urgency", "notes", "submit-intake"}
            ]
            focus_runtime_path = write_json(
                "focus-keyboard-runtime.json",
                observation(page, digest, path=focus_path, console=messages),
            )
            observations["focus"] = focus_runtime_path
            record(
                "P8-EVAL-032",
                critical_focus_ids == ["patient", "species", "urgency", "notes", "submit-intake"]
                and all(
                    item["outline"] not in {None, "none"}
                    for item in focus_path
                    if item["id"] in critical_focus_ids
                ),
                focus_runtime_path,
                "real Tab traversal reaches form controls in order with a visible outline",
            )
            context.close()

            # Pointer-free validation, data entry and submission.
            context, page, messages = new_page(browser, (1440, 900))
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            for _ in range(40):
                if page.evaluate("document.activeElement?.id") == "submit-intake":
                    break
                page.keyboard.press("Tab")
            page.keyboard.press("Enter")
            page.wait_for_function("() => document.activeElement?.id === 'patient'")
            validation_focus = page.evaluate(
                "() => ({focused: document.activeElement?.id, invalid: [...document.querySelectorAll('[aria-invalid=true]')].map(e => e.id)})"
            )
            page.keyboard.type("Keyboard")
            page.keyboard.press("Tab")
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Tab")
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Tab")
            page.keyboard.type("Entered without a pointer")
            page.keyboard.press("Tab")
            before_enter = page.evaluate("document.activeElement?.id")
            page.keyboard.press("Enter")
            page.wait_for_function("() => __phase81.getState().requestNumber === 1")
            keyboard_result = page.evaluate(
                "() => ({state: __phase81.getState(), focused: document.activeElement?.id, feedback: document.querySelector('#intake-feedback').textContent})"
            )
            keyboard_path = write_json(
                "keyboard-submit-runtime.json",
                observation(
                    page,
                    digest,
                    validation=validation_focus,
                    beforeEnter=before_enter,
                    result=keyboard_result,
                    console=messages,
                ),
            )
            observations["keyboard"] = keyboard_path
            record(
                "P8-EVAL-033",
                validation_focus["focused"] == "patient"
                and validation_focus["invalid"] == ["patient", "species", "urgency"]
                and before_enter == "submit-intake"
                and keyboard_result["state"]["requestNumber"] == 1
                and keyboard_result["focused"] == "patient",
                keyboard_path,
                "keyboard-only path validates, enters every required value and submits with Enter",
            )
            context.close()

            # Live-region state changes are observed for loading, error and intake success.
            context, page, messages = new_page(browser, (1440, 900))
            page.goto(f"{BASE_URL}?scenario=loading", wait_until="domcontentloaded")
            live_loading = page.evaluate(
                "() => ({text: document.querySelector('#queue-state').textContent, live: document.querySelector('#queue-state').getAttribute('aria-live'), role: document.querySelector('#queue-state').getAttribute('role')})"
            )
            page.goto(f"{BASE_URL}?scenario=error", wait_until="domcontentloaded")
            wait_state(page, "error")
            live_error = page.evaluate(
                "() => ({text: document.querySelector('#queue-state').textContent, live: document.querySelector('#queue-state').getAttribute('aria-live'), role: document.querySelector('#queue-state').getAttribute('role')})"
            )
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            page.locator("#patient").fill("Live")
            page.locator("#species").select_option("rabbit")
            page.locator("#urgency").select_option("soon")
            page.locator("#submit-intake").click()
            page.wait_for_function("() => __phase81.getState().requestNumber === 1")
            live_success = page.evaluate(
                "() => ({text: document.querySelector('#intake-feedback').textContent, live: document.querySelector('#intake-feedback').getAttribute('aria-live'), role: document.querySelector('#intake-feedback').getAttribute('role')})"
            )
            live_path = write_json(
                "live-region-states-runtime.json",
                observation(
                    page,
                    digest,
                    loading=live_loading,
                    error=live_error,
                    success=live_success,
                    console=messages,
                ),
            )
            observations["live_regions"] = live_path
            record(
                "P8-EVAL-034",
                live_loading["text"] == "Loading current queue…"
                and live_error["text"] == "The queue could not be loaded. Try again."
                and live_success["text"].startswith("Intake accepted for triage. Reference")
                and all(
                    state["live"] == "polite" and state["role"] == "status"
                    for state in (live_loading, live_error, live_success)
                ),
                live_path,
                "polite status regions carry actual loading, error and intake-success text",
            )
            context.close()

            # Reduced-motion media emulation and computed behavior.
            context = browser.new_context(
                viewport={"width": 1440, "height": 900}, reduced_motion="reduce"
            )
            page = context.new_page()
            messages = []
            page.on("console", lambda msg: messages.append({"type": msg.type, "text": msg.text}))
            page.on(
                "pageerror",
                lambda error: messages.append({"type": "pageerror", "text": str(error)}),
            )
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            reduced = page.evaluate(
                """() => {
                  const durationMs = value => value.split(',').map(part => {
                    const text = part.trim();
                    return text.endsWith('ms') ? parseFloat(text) : parseFloat(text) * 1000;
                  });
                  const targets = ['.button', '.nav-link', '#patient'].map(selector => {
                    const style = getComputedStyle(document.querySelector(selector));
                    return {selector, transitionMs: durationMs(style.transitionDuration), animationMs: durationMs(style.animationDuration)};
                  });
                  return {matches: matchMedia('(prefers-reduced-motion: reduce)').matches, targets};
                }"""
            )
            reduced_path = write_json(
                "reduced-motion-runtime.json",
                observation(page, digest, **reduced, console=messages),
            )
            observations["reduced_motion"] = reduced_path
            record(
                "P8-EVAL-036",
                reduced["matches"]
                and all(
                    max(item["transitionMs"] + item["animationMs"]) <= 0.011
                    for item in reduced["targets"]
                ),
                reduced_path,
                "Chromium reduce emulation yields <=0.01ms computed motion durations",
            )
            context.close()

            # Primary mobile target bounds.
            context, page, messages = new_page(browser, (390, 844))
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            targets = page.evaluate(
                """() => [...document.querySelectorAll('.page-intro .button, #submit-intake, #refresh-queue, .nav-link')].map(e => ({
                  name: e.id || e.getAttribute('href'),
                  width: e.getBoundingClientRect().width,
                  height: e.getBoundingClientRect().height,
                }))"""
            )
            targets_path = write_json(
                "mobile-targets-runtime.json",
                observation(page, digest, targets=targets, console=messages),
            )
            observations["targets"] = targets_path
            record(
                "P8-EVAL-037",
                len(targets) >= 6
                and all(item["width"] >= 44 and item["height"] >= 44 for item in targets),
                targets_path,
                "measured primary mobile links and actions meet the declared 44px floor",
            )
            context.close()

            # Current-artifact LCP and CLS while the delayed queue replaces skeletons.
            context, page, messages = new_page(browser, (1440, 900))
            page.add_init_script(
                """window.__p81Perf = {lcp: [], shifts: []};
                  new PerformanceObserver(list => {
                    for (const entry of list.getEntries()) window.__p81Perf.lcp.push({startTime: entry.startTime, size: entry.size || 0, element: entry.element?.tagName || null});
                  }).observe({type: 'largest-contentful-paint', buffered: true});
                  new PerformanceObserver(list => {
                    for (const entry of list.getEntries()) window.__p81Perf.shifts.push({value: entry.value, hadRecentInput: entry.hadRecentInput});
                  }).observe({type: 'layout-shift', buffered: true});
                """
            )
            page.goto(f"{BASE_URL}?scenario=loading", wait_until="domcontentloaded")
            skeleton_geometry = page.locator(".queue-panel").bounding_box()
            wait_state(page, "success")
            page.wait_for_timeout(250)
            perf_observation = page.evaluate(
                """() => ({
                  navigation: performance.getEntriesByType('navigation').map(e => ({startTime: e.startTime, domContentLoaded: e.domContentLoadedEventEnd, load: e.loadEventEnd})),
                  lcp: window.__p81Perf.lcp,
                  shifts: window.__p81Perf.shifts,
                  cls: window.__p81Perf.shifts.filter(e => !e.hadRecentInput).reduce((sum, e) => sum + e.value, 0),
                })"""
            )
            perf_observation["skeletonGeometry"] = skeleton_geometry
            perf_observation["loadedGeometry"] = page.locator(".queue-panel").bounding_box()
            perf_path = write_json(
                "performance-runtime.json",
                observation(page, digest, **perf_observation, console=messages),
            )
            observations["performance"] = perf_path
            lcp_ms = max(
                (entry["startTime"] for entry in perf_observation["lcp"]), default=float("inf")
            )
            record(
                "P8-EVAL-039",
                bool(perf_observation["navigation"])
                and bool(perf_observation["lcp"])
                and lcp_ms <= 2500,
                perf_path,
                f"current-artifact Chromium LCP {lcp_ms:.2f}ms is within the 2500ms pilot budget",
            )
            record(
                "P8-EVAL-040",
                perf_observation["skeletonGeometry"] is not None
                and perf_observation["loadedGeometry"] is not None
                and perf_observation["cls"] <= 0.1,
                perf_path,
                f"buffered layout-shift observer records CLS {perf_observation['cls']:.6f}",
            )
            context.close()

            # Explicit local resource, media-payload and network-origin audit.
            context, page, messages = new_page(browser, (1440, 900))
            request_inventory: list[dict[str, str]] = []
            page.on(
                "request",
                lambda request: request_inventory.append(
                    {
                        "url": request.url,
                        "method": request.method,
                        "resourceType": request.resource_type,
                    }
                ),
            )
            page.goto(BASE_URL, wait_until="networkidle")
            wait_state(page, "success")
            resource_audit = page.evaluate(
                """() => ({
                  resources: performance.getEntriesByType('resource').map(e => ({name: e.name, transferSize: e.transferSize, decodedBodySize: e.decodedBodySize, initiatorType: e.initiatorType})),
                  mediaElements: [...document.querySelectorAll('img,video,audio,source,picture')].map(e => e.outerHTML),
                  scripts: [...document.scripts].map(e => e.src),
                  links: [...document.querySelectorAll('link[href]')].map(e => ({rel: e.rel, href: e.href})),
                })"""
            )
            resource_audit["requests"] = request_inventory
            resource_audit["sourceFiles"] = [
                {"name": name, "bytes": (ARTIFACT_ROOT / name).stat().st_size}
                for name in SOURCE_FILES
            ]
            resource_path = write_json(
                "resource-network-media-runtime.json",
                observation(page, digest, **resource_audit, console=messages),
            )
            observations["resources"] = resource_path
            local_requests = all(
                item["url"].startswith(BASE_URL) or item["url"].startswith("data:")
                for item in request_inventory
            )
            no_remote_assets = all(
                item["name"].startswith(BASE_URL) or item["name"].startswith("data:")
                for item in resource_audit["resources"]
            )
            record(
                "P8-EVAL-041",
                local_requests
                and no_remote_assets
                and all(
                    not item["url"].startswith(("http://", "https://"))
                    or item["url"].startswith(BASE_URL)
                    for item in request_inventory
                ),
                resource_path,
                "network inventory contains no remote fonts, images, scripts or analytics",
            )
            record(
                "P8-EVAL-043",
                not resource_audit["mediaElements"]
                and all(item["bytes"] < 256 * 1024 for item in resource_audit["sourceFiles"])
                and all(
                    item["decodedBodySize"] < 256 * 1024 for item in resource_audit["resources"]
                ),
                resource_path,
                "explicit DOM, source-file and transfer inventory contains no oversized media",
            )
            record(
                "P8-EVAL-053",
                local_requests
                and all(
                    not item["url"].startswith(("http://", "https://"))
                    or item["url"].startswith(BASE_URL)
                    for item in request_inventory
                ),
                resource_path,
                "all observed HTTP requests target the same 127.0.0.1 fixture origin",
            )
            context.close()

            # System-font fallback at wide and narrow widths.
            font_results: list[dict[str, Any]] = []
            font_console: list[dict[str, str]] = []
            for width, height in ((1440, 900), (390, 844)):
                context, page, messages = new_page(browser, (width, height))
                page.goto(BASE_URL, wait_until="domcontentloaded")
                wait_state(page, "success")
                result = page.evaluate(
                    """() => {
                      document.documentElement.style.fontFamily = 'Arial, sans-serif';
                      const form = document.querySelector('#intake');
                      const submit = document.querySelector('#submit-intake');
                      form.scrollIntoView();
                      return {
                        viewport: {width: innerWidth, height: innerHeight},
                        font: getComputedStyle(document.body).fontFamily,
                        overflowX: document.documentElement.scrollWidth > innerWidth,
                        formBox: form.getBoundingClientRect().toJSON(),
                        submitBox: submit.getBoundingClientRect().toJSON(),
                      };
                    }"""
                )
                font_results.append(result)
                font_console.extend(messages)
                context.close()
            font_path = write_json(
                "font-fallback-runtime.json",
                {
                    "capture_id": CAPTURE_ID,
                    "run_id": COMPOSITION_RUN,
                    "captured_at_ns": time.time_ns(),
                    "artifact_digest": digest,
                    "results": font_results,
                    "console": font_console,
                },
            )
            observations["font_fallback"] = font_path
            record(
                "P8-EVAL-042",
                len(font_results) == 2
                and all(not item["overflowX"] for item in font_results)
                and all(
                    item["submitBox"]["width"] > 0 and item["submitBox"]["height"] >= 44
                    for item in font_results
                )
                and all("Arial" in item["font"] for item in font_results),
                font_path,
                "forced system Arial fallback preserves form/action layout at 1440px and 390px",
            )

            # Client and fixture validation both fail closed with named errors.
            context, page, messages = new_page(browser, (1440, 900))
            client_posts: list[str] = []
            page.on(
                "request",
                lambda request: (
                    client_posts.append(request.url)
                    if request.method == "POST" and "/api/intakes" in request.url
                    else None
                ),
            )
            page.goto(BASE_URL, wait_until="domcontentloaded")
            wait_state(page, "success")
            page.locator("#submit-intake").click()
            client_invalid = page.evaluate(
                "() => ({invalid: [...document.querySelectorAll('[aria-invalid=true]')].map(e => e.id), errors: ['patient','species','urgency'].map(id => document.querySelector(`#${id}-error`).textContent)})"
            )
            blank_posts = list(client_posts)
            fixture_invalid = page.evaluate(
                """async () => {
                  const response = await fetch('/api/intakes', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', 'Idempotency-Key': 'invalid-boundary'},
                    body: JSON.stringify({patient: 'X', species: 'snake', urgency: 'unknown', notes: ''}),
                  });
                  return {status: response.status, body: await response.json()};
                }"""
            )
            validation_path = write_json(
                "input-boundary-validation-runtime.json",
                observation(
                    page,
                    digest,
                    client={"blankPosts": blank_posts, **client_invalid},
                    fixture=fixture_invalid,
                    console=messages,
                ),
            )
            observations["input_validation"] = validation_path
            record(
                "P8-EVAL-050",
                not blank_posts
                and client_invalid["invalid"] == ["patient", "species", "urgency"]
                and all(client_invalid["errors"])
                and fixture_invalid["status"] == 422
                and sorted(fixture_invalid["body"]["errors"]) == ["patient", "species", "urgency"],
                validation_path,
                "client blocks blank create; fixture rejects invalid patient/species/urgency with 422",
            )
            context.close()

            browser.close()

        completed_ns = time.time_ns()
        failed = [check for check in checks if not check["passed"]]
        server_receipt = write_json(
            "server-binding.json",
            {
                "schema_version": "P8.1-SERVER-BINDING-2",
                "run_id": SERVER_RUN,
                "composition_run": COMPOSITION_RUN,
                "artifact_root": ARTIFACT_ROOT.relative_to(PROJECT_ROOT).as_posix(),
                "artifact_digest": digest,
                "base_url": BASE_URL,
                "network": "LOOPBACK_ONLY",
                "started_at_ns": started_ns,
                "completed_at_ns": completed_ns,
                "binding_header": "X-Phase81-Artifact-Digest",
            },
        )
        observations["server"] = server_receipt
        for evidence_path in sorted(OUTPUT_ROOT.iterdir()):
            relative = evidence_path.relative_to(EVIDENCE_ROOT).as_posix()
            if relative not in {item["path"] for item in captures}:
                captures.append(
                    {
                        "path": relative,
                        "sha256": sha256(evidence_path),
                        "kind": "runtime-json",
                    }
                )
        manifest = {
            "schema_version": "P8.1-BROWSER-EVIDENCE-2",
            "task_id": "PHASE8.1-001",
            "status": "PASS" if not failed else "FAIL",
            "composition_run": COMPOSITION_RUN,
            "capture_id": CAPTURE_ID,
            "artifact_digest": digest,
            "browser": {
                "engine": "Chromium",
                "executable": str(CHROME),
                "version": browser_version,
                "executable_digest": sha256(CHROME),
            },
            "timeline": {"started_at_ns": started_ns, "completed_at_ns": completed_ns},
            "checks": checks,
            "summary": {
                "total": len(checks),
                "passed": len(checks) - len(failed),
                "failed": len(failed),
            },
            "observations": observations,
            "captures": captures,
            "limitations": [
                "Chromium-only runtime evidence is not a full assistive-technology certification.",
                "The local deterministic fixture does not establish production or release approval.",
            ],
        }
        MANIFEST_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        print(
            json.dumps(
                {
                    "status": manifest["status"],
                    "artifact_digest": digest,
                    "checks": manifest["summary"],
                    "manifest": str(MANIFEST_PATH.relative_to(PROJECT_ROOT)),
                }
            )
        )
        return 0 if not failed else 1
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        stderr = server.stderr.read() if server.stderr else ""
        if stderr:
            (OUTPUT_ROOT / "server-stderr.log").write_text(stderr)


if __name__ == "__main__":
    raise SystemExit(main())
