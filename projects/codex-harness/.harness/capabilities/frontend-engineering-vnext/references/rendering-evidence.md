# Rendering and evidence contract

Visual claims require a runnable artifact and native browser captures. A
source scan, mocked DOM or resized image is not a render. Each capture record
binds:

- artifact/source identity and final verification identity;
- route, viewport width/height, DPR, state and browser/runtime;
- capture timestamp and SHA-256 digest;
- semantic regions inspected;
- overflow/clipping, typography, controls, focus, console and network result;
- current render ID used by the inspection, ledger, score and critique.

Required high-value flow:

```text
run app → set viewport/state → interact → capture → inspect → ledger
→ independent read-only critique → one bounded repair → recapture → verify
```

Every relevant viewport/state/region tuple must be present or explicitly
`NOT_RUN`/`BLOCKED`. A material repair invalidates all downstream render,
verification and visual scores. Never call a screenshot pixel-perfect or
visually complete without a native reference and the evidence that claim
requires.

The visual ledger records expected, observed, severity, evidence, smallest
fix and status. `FIXED` requires a new observation after the change;
`ACCEPTED` records who accepted the residual risk. The critic receives a blind
packet and no builder rationale or desired score.
