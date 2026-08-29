# P5-QB-1 — Design Director Composition Pilot Quality Bar

This bar is frozen before Phase 5 implementation. It applies only to the
project-local pilot and does not authorize a production, AAA, arbitrary
execution or Skill-promotion claim.

| ID | Blocking criterion | Required evidence |
| --- | --- | --- |
| P5-01 | Phase 2, Phase 3 and Phase 4 frozen packets remain regression-green | `evidence/phase-5/phase2-regression.md`, `evidence/phase-5/phase3-regression.md`, `evidence/phase-5/phase4-regression.md` |
| P5-02 | The installed design-director package is inspected read-only and bound to an exact identity/fingerprint | `eligibility.json`, `fingerprints.json`, package inspection receipt |
| P5-03 | Ineligible capabilities are blocked without fallback impersonation | `eligibility.json`, negative evals, `EXTERNAL_VERIFIER_NOT_ELIGIBLE` evidence when applicable |
| P5-04 | Task, visual brief, criteria and role ownership are immutable across handoffs | `task.json`, `acceptance-criteria.json`, context and authorization manifests |
| P5-05 | The bounded graph is fixed, finite and rejects arbitrary nodes, cycles and budget bypasses | composition tests and `composition-receipt.json` |
| P5-06 | A real builder invocation produces a validated, response-derived artifact or records a truthful block | builder receipt, artifact lineage and artifact digest |
| P5-07 | Structural verification checks loadability, local assets, errors, overflow, semantics, a11y and confinement | `verification-v1.json` and `final-verification.json` |
| P5-08 | Desktop and mobile renders are native captures of the current artifact | `desktop.png`, `mobile.png`, render records and browser evidence |
| P5-09 | Visual review is blind, read-only, separated from builder rationale and uses anchored dimensions/severity | `critique-v1.json` and independent review packet |
| P5-10 | Repair is optional, finite (maximum one), attributable and followed by fresh render/verification | `repair-plan.json`, `artifact-v2/`, final verification when applicable |
| P5-11 | Assurance distinguishes PASS, PASS_WITH_LIMITATIONS, FAIL, STOP and BLOCK; no self-approval is accepted | `assurance.json`, readiness and final report |
| P5-12 | Artifact/evidence refs are immutable, stale after artifact change, bounded and path-safe | lineage/security tests and pilot evidence |
| P5-13 | Tool, shell, network, MCP, provider, credential, script, subagent, replay and workspace-escape negatives fail closed | evals, security report and policy evidence |
| P5-14 | Baseline versus composition is measured without causal overclaiming | `benchmark-report.json` labeled `PILOT_COMPOSITION_EVIDENCE` |
| P5-15 | Telemetry identifies task/run/capability/fingerprint/role/invocation/artifact/version and redacts secrets/host paths | `telemetry-report.json` and privacy tests |
| P5-16 | Combined project coverage is ≥80%, Ruff and strict mypy pass | coverage, Ruff and mypy reports |
| P5-17 | A fresh independent engineering and visual review receives the exact final packet | independent reviews, manifest and attestation |
| P5-18 | No unresolved Critical or High findings remain at closeout | readiness and final review |

## Quality dimensions

The visual critic scores only dimensions supported by current renders: art
direction, visual hierarchy, typography, composition, spacing, color system,
asset quality, product specificity, responsiveness, accessibility, polish and
generic-AI-slop avoidance. Each score has a 0–100 scale, evidence confidence,
region binding and direct observations. Missing screenshots or interaction
evidence are `BLOCKED`/`NOT_RUN`, never a pass by explanation.

## Support levels

- `A`: real design-director builder response plus Harness-native structural and
  browser verification.
- `B`: Level A plus a second eligible real verification capability.
- `C`: Level B plus an independent real critic/repair/final-verification path.

The preferred secondary is `verification-loop`. If it is not eligible, the
minimum honest result is Level A with `EXTERNAL_MULTI_CAPABILITY_COMPOSITION_PARTIAL`
and a separate independent critic. No result may claim that a native fallback
is an external second capability.

## Closeout rule

`PASS_WITH_LIMITATIONS` requires a real artifact or a documented official-host
limitation, current desktop and mobile evidence, structural verification,
independent exact-packet review, exact fingerprints, no global or installed
capability mutation, zero Critical/High findings and explicit limitations.
`AAA_CANDIDATE` is not a permitted Phase 5 claim.
