# Phase 8 Quality Bar — P8-QB-1

This bar is frozen before Phase 8 implementation. It is additive to the
authoritative Phase 2–7.3 packets and is not lowered to fit the pilot result.

## Required gates

| ID | Gate | Pass evidence |
| --- | --- | --- |
| P8-01 | Authority and preservation | Current skill and prior frozen packets are read-only; global/current-skill mutation checks are zero. |
| P8-02 | Forensic comparison | Current installed snapshot, upstream snapshot, Codex-native gap analysis and portability debt are exact and cited. |
| P8-03 | Package identity | `frontend-engineering-vnext` has a valid native manifest, version, specialist role, `FRONTEND_ENGINEERING` domain, explicit conflicts and bounded references. |
| P8-04 | Package quality | `SKILL.md` stays concise; every selected reference is relevant; deterministic procedures are bounded; 50–75 meaningful eval scenarios exist with negative routing and false-pass cases. |
| P8-05 | Architecture preservation | The pilot uses the existing project web stack and documents why no framework/dependency was introduced. |
| P8-06 | Real pilot | A fictional Veterinary Emergency Intake Dashboard is real code with a local deterministic API fixture and tested loading/success/empty/error/retry/double-submit behavior. |
| P8-07 | Build and static quality | Build, syntax/type analogue, lint, tests and source/token checks run against the final artifact; failures are explicit. |
| P8-08 | Browser and responsive evidence | Fresh native captures exist at 1440×900, 1024×768, 768×1024 and 390×844, each bound to source/artifact digests; no overflow/clipping or stale substitution. |
| P8-09 | Interaction and accessibility | Keyboard/focus, labels/names, heading order, status/error semantics, non-color cues, reduced motion, touch targets and basic automated a11y are observed. |
| P8-10 | Visual quality | A blind read-only visual critic reviews the current render matrix, applies the rubric, checks anti-slop/product specificity and identifies the largest gap. |
| P8-11 | Verification composition | Real Phase 3 discovery, Phase 4 preflight, frontend specialist and final verification invocations are recorded; verifier remains read-only and fresh after repair. |
| P8-12 | Security/performance handoff | Input validation, no external sink, no secret leakage, browser console/network and bounded performance observations are recorded; no broad security approval is claimed. |
| P8-13 | Regression and integrity | Prior phase regressions, package/pilot tests, manifest, attestation and independent capability/frontend reviews reconcile exactly. |

## Support-level decision

`PASS_WITH_LIMITATIONS` requires zero Critical, zero High, zero actionable
Medium findings, a real frontend artifact, current responsive/render/a11y
evidence, final factual verification and an exact-packet review. Level A means
the package contracts and pilot are bounded but composition evidence is
partial; Level B requires the full rendered/browser/verification packet;
Level C is not targeted. This phase must never report `STABLE`.

## Explicit exclusions

The following labels are prohibited regardless of score: `PRODUCTION_READY`,
`AAA_VERIFIED`, `STABLE`, `SECURITY_APPROVED`, `ACCESSIBILITY_CERTIFIED`,
`WCAG_CERTIFIED`, `PIXEL_PERFECT`, `ALL_BROWSERS_VERIFIED`,
`ALL_VIEWPORTS_VERIFIED`, `UNIVERSAL_FRONTEND_SUPERIORITY`,
`CAUSAL_SUPERIORITY`, and `FULL_HOST_CAUSALITY`.

## Iteration budget

The high-value visual pilot has a maximum of two render/critique cycles:
initial implementation plus one repair. Every material repair invalidates
prior artifact-bound verification and requires fresh screenshots, interaction
checks, visual critique and final verification.
