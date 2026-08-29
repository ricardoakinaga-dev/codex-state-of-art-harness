# Phase 5 evidence

This directory is the bounded `PHASE5-001` design-director composition pilot.
It covers one fictional Northline Veterinary Emergency Center hero, one exact
builder capability, Harness-native browser verification, two blind visual
reviews, one bounded repair, and the final assurance packet.

Status: `PASS_WITH_LIMITATIONS` at support level `A`.

The required pilot packet is under
[`pilots/design-director/`](pilots/design-director/). The quality bar is
[`P5-QB-1.md`](P5-QB-1.md), and the project policy is
[`composition-policy.json`](composition-policy.json).

The honest support boundary is:

- `design-director` was eligible only for exact, response-only artifact
  materialization. Its installed package was inspected read-only and was not
  edited, copied, installed, or executed through its scripts.
- `verification-loop` was inspected and blocked as
  `EXTERNAL_VERIFIER_NOT_ELIGIBLE`; it is not represented by a native fallback
  or promoted as a second capability.
- The fixed graph ran through builder, structural verification, blind visual
  critique, one optional repair, final verification, and assurance.
- The artifact is a project-local HTML/CSS/SVG response. No production site,
  arbitrary Skill execution, provider, MCP, shell, network, credential,
  subagent, or global configuration change was authorized.

The root reports contain the exact fingerprints, routing decision, composition
telemetry, visual findings, baseline comparison, context cost, security,
coverage, Phase 2–4 regression, independent review, readiness, manifest,
attestation, final report, and freeze. `review-manifest.json` intentionally
excludes control pointers that would create recursive hashing; the attestation
and readiness records bind that manifest explicitly.
