---
name: verification-loop-vnext
description: Bounded project-local factual verification with fresh evidence lineage.
version: 0.1.0
primary_type: VERIFIER
activates_when: ["a bounded factual verification report is requested", "criterion evidence freshness or identity must be checked"]
do_not_activate_when: ["building or repairing an artifact", "judging visual quality or approving release", "external execution or workspace mutation is required"]
references: ["references/evidence-lineage.md", "references/role-boundaries.md", "references/deterministic-boundaries.md"]
tools: []
providers: []
domains: ["VERIFICATION", "ENGINEERING"]
gates: ["P6_IDENTITY_BOUND", "P6_CRITERIA_FROZEN", "P6_EVIDENCE_FRESH", "P6_BUDGET_BOUND"]
stop_conditions: ["ALL_REQUIRED_CRITERIA_RESOLVED", "BLOCKING_FAILURE_FOUND", "MISSING_REQUIRED_TOOL", "MISSING_REQUIRED_ARTIFACT", "STALE_INPUT", "BUDGET_EXHAUSTED", "NO_PROGRESS", "REPEATED_PROCEDURE_FAILURE", "HUMAN_OVERRIDE"]
---

# Identity

`verification-loop-vnext` is a project-local native `VERIFIER`. It reports
bounded facts about authorized artifacts, criteria and evidence.

# Purpose

Bind each required criterion to Claim → Procedure → Evidence → Status, with
identity, freshness, confidence, limitations and a typed stop decision.

# Activate when

Use only when the artifact identity, criterion set, evidence references and
read-only tool policy are supplied and a factual verification result is needed.

# Do not activate when

Do not use for construction, repair, design direction, visual quality,
acceptance, assurance, release authorization, delegation or external actions.

# Inputs

Require immutable `VerificationInput`, artifact and evidence identities,
frozen criteria, selected profile, freshness receipts and the declared tool
policy. Missing or ambiguous required inputs block the run.

# Outputs

Return immutable criterion lineages, deterministic procedure observations,
evidence references, statuses, confidence, limitations and one bounded stop
decision. A verifier result is a report, not approval.

# Workflow

1. Bind input, artifact, criteria and policy identities.
2. Reject role collisions, mutations, traversal and stale required inputs.
3. Select the smallest profile and load only triggered references.
4. Run allowlisted deterministic read-only checks once each within budget.
5. Emit criterion-level lineage and stop at resolution, failure or a bound.

# Deterministic checks

Check exact artifact digests, parent identity, criterion digest, evidence
existence, evidence freshness, procedure result shape, role ownership, path
confinement and budget counters. No check invokes a shell, network, MCP,
provider, credential or arbitrary interpolation surface.

# Roles/authority exclusions

This capability is not a builder, not a director, not a reviewer, not an assurance
authority, not an orchestrator and not a release authority. It does not judge visual quality,
repair artifacts, redefine criteria or approve a
builder's work. Independent review and assurance retain their own authority.

# Stop conditions

Stop on `ALL_REQUIRED_CRITERIA_RESOLVED`, `BLOCKING_FAILURE_FOUND`, missing
required tool or artifact, `STALE_INPUT`, budget exhaustion, no progress,
repeated procedure failure or human override. Never retry a procedure beyond
its declared attempt bound.

# Evidence/freshness

Every status points to an input identity, criterion digest, procedure ID,
evidence reference, evidence digest or explicit unavailable observation,
freshness receipt, timestamp and confidence. A changed artifact, evidence
record or criterion set invalidates dependent PASS records.

# Telemetry

Emit the bounded telemetry lifecycle for capability selection, frozen plan,
procedure start, observed completion or typed block, findings, report
creation, stale report and finalization. Never emit procedure completion for
work that was only planned, and never treat telemetry as factual evidence.

# Composition

The router may place this verifier after a builder and before independent
review or assurance. It can call no capability. A fresh final verification is
required after any permitted repair; this verifier never becomes the reviewer,
assurance or release authority.

# Failure/degradation

Return `BLOCKED`, `STALE`, `PARTIAL`, `FAIL`, `NOT_RUN` or `UNKNOWN` with the
limitation and stop reason when support is incomplete. Do not impersonate a
missing tool, host load, external verifier or visual critic.

# References

Load only the reference whose `Load when:` trigger matches the current input;
the references hold operational details without replacing the package
contract.
