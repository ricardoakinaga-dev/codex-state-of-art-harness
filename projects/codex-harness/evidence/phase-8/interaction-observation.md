# Phase 8 interaction and state observation

## Browser source of truth

The local fixture was served at `http://127.0.0.1:4173` with synthetic data.
Playwright MCP captured `P8-FINAL-REPAIR-002` at 390×844 for the state matrix
and at 1440×900, 1024×768, 768×1024 and 390×844 for the primary render matrix.

## Observed paths

- Loading: skeleton rows and `aria-busy` queue state.
- Success: four active cases, summary counts and queue rows.
- Empty: clear desk message with refresh action.
- Error/retry: visible error card, retry action and recovery to four items.
- Validation: first focus returns to patient; patient, species and urgency are
  marked invalid with named messages.
- Intake success: acceptance banner is now visible within the mobile viewport
  after the form resets.
- Filter/review: Critical filter leaves one row and Review focuses the patient
  field with a visible focus ring.
- Submit error: error feedback remains visible and the submit control is
  re-enabled for a safe retry.
- Concurrent replay: the current browser observation records one `201`, one
  `200 duplicate`, identical intake IDs and `exactly_one_created: true`.

## Evidence links

- Render/state binding: `pilots/frontend-engineering/browser-evidence.json`
- Performance/DOM: `pilots/frontend-engineering/browser-final-performance-and-dom.json`
- Contrast: `pilots/frontend-engineering/browser-contrast-observation.json`
- Idempotency: `pilots/frontend-engineering/browser-idempotency-observation.json`
- Static accessibility: `static-accessibility.json`

The packet does not claim complete keyboard, AT, reduced-motion, touch, zoom,
cross-browser or universal viewport coverage.
