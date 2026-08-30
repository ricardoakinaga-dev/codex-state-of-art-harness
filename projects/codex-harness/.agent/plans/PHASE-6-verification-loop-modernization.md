# ExecPlan — PHASE6-001 Verification Loop vNext Modernization

## Purpose

Modernize the installed `verification-loop` as an additive, project-local
Codex-native capability package. The vNext package owns factual verification
claims, procedures, evidence bindings, freshness and bounded stop decisions.
It does not own implementation, visual/art direction, orchestration,
assurance or release authority.

The original installed package is an immutable forensic input. This plan never
edits, copies, installs, symlinks or rewrites files under
`/home/ricardo/.agents/skills/verification-loop` or any other global skill
root.

## Frozen inputs and authorities

- User requirements: `/home/ricardo/.codex/attachments/390d0fa4-98eb-4c6b-81cd-00ad122172b0/pasted-text-1.txt`
- Quality bar: `evidence/phase-6/P6-QB-1.md`
- Architecture decision: `../../architecture/docs/adr/ADR-015-verification-loop-vnext-modernization.md`
- Current snapshot: `evidence/phase-6/current-verification-loop-snapshot.json`
- Ineligibility analysis: `evidence/phase-6/current-ineligibility-analysis.md`
- Upstream analysis: `evidence/phase-6/upstream-analysis.md`
- Phase 2 freeze: `evidence/phase-2/PHASE2-FROZEN.md`
- Phase 3 authority: `evidence/phase-3/readiness.json` and `.agent/gates/PHASE3-VERIFIED-0004.json`
- Phase 4 freeze: `evidence/phase-4/PHASE4-FROZEN.md`
- Phase 5 freeze: `evidence/phase-5/PHASE5-FROZEN.md`

## Scope

In scope:

- one project-local package at `.harness/capabilities/verification-loop-vnext`;
- native manifest, concise router `SKILL.md`, references, deterministic
  read-only checks, eval scenarios, benchmark fixtures and package validation;
- immutable typed input/output contracts with criterion-level
  Claim → Procedure → Evidence → Status lineage;
- explicit profiles: `FOCUSED`, `DOMAIN`, `FULL`, `VISUAL`, `STRUCTURAL`,
  `SECURITY_AWARE` and `COMPOSITION`;
- Phase 3 discovery/load proof, Phase 4 preflight and one bounded real
  composition integration when the host can observe the route honestly;
- fresh independent capability and composition reviews and exact evidence
  closure.

Out of scope:

- global installation or migration;
- modification of the installed current package or upstream repositories;
- arbitrary shell, network, MCP, provider, credential, subagent or script
  execution;
- visual/art-direction ownership, implementation, repair, orchestration,
  assurance or release approval;
- production, AAA, causal quality or universal host-load claims.

## Roles and fixed composition boundary

`VERIFIER` may inspect authorized artifacts and evidence, execute declared
deterministic procedures, and report facts. `REVIEWER` independently compares
those facts with the quality bar. `ASSURANCE` owns stop/continue risk
decisions. `DESIGN_DIRECTOR` owns visual strategy and `BUILDER` owns artifact
creation. `ORCHESTRATOR` owns delegation only. No vNext output can approve a
builder's work or redefine acceptance criteria.

The preferred composition target is Level C when the host supports it:

```text
ROUTER
  → real design-director builder
  → artifact v1
  → real verification-loop-vnext verifier
  → report v1
  → independent visual critic
  → bounded repair decision
  → optional artifact v2
  → fresh vNext final verifier
  → assurance
  → delivery
```

If an exact host boundary is unavailable, the run must stop at the highest
honest support level and record `BLOCKED`, `NOT_RUN` or `UNKNOWN`; a native
fallback is not impersonated as an external capability.

## Work sequence

1. Freeze this plan, P6-QB-1, ADR-015, snapshot, ineligibility and upstream
   analysis; reconcile `.agent` state and record the current baseline.
2. Write RED unit, integration, security and eval tests for immutable models,
   package policy, path confinement, stale lineage, role separation, criteria
   mutation and bounded stops.
3. Implement the core typed contracts, policy, deterministic procedures,
   report generation and project-local package validator.
4. Add the vNext package, references, fixtures and at least 30 meaningful
   scenario evals without duplicating architecture contracts.
5. Prove Phase 3 discovery, safe loading and Phase 4 preflight with exact
   package and manifest fingerprints. Run a real host verifier only after
   `PILOT_EXECUTABLE` is green.
6. Run native/current/upstream/vNext benchmarks, security checks and full
   Phase 2–5 regressions. Record context cost and latency as observations, not
   causal claims.
7. Execute the bounded design-director composition, obtain fresh independent
   reviews, repair only within the declared one-repair budget, and regenerate
   all artifact-bound evidence after any change.
8. Recompute the exact review manifest, readiness, attestation and freeze
   packet. Promote at most to `VERIFIED`/candidate; never claim migration or
   production readiness.

## Budgets and stop conditions

- package context: 16 KiB maximum for the kernel and 64 KiB total selected
  references;
- deterministic procedures: 32 per run, 120 seconds total, 1 attempt per
  procedure unless the procedure explicitly declares a smaller bound;
- verifier invocations: 2 per composition run (v1 and one fresh final pass);
- composition repairs: 1 maximum;
- evidence records: 256 per run and 128 KiB per serialized report;
- no-network/default read-only mode; no arbitrary command interpolation;
- stop on `ALL_REQUIRED_CRITERIA_RESOLVED`,
  `BLOCKING_FAILURE_FOUND`, `MISSING_REQUIRED_TOOL`,
  `MISSING_REQUIRED_ARTIFACT`, `STALE_INPUT`, `BUDGET_EXHAUSTED`,
  `NO_PROGRESS`, `REPEATED_PROCEDURE_FAILURE` or `HUMAN_OVERRIDE`.

## Verification commands

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/coverage run --source=src/harness_kernel -m pytest -q -p no:cacheprovider
.venv/bin/coverage report --fail-under=80
.venv/bin/ruff format --check src tests
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

Additional package/eval commands are recorded in the Phase 6 evidence packet
and must remain bounded, deterministic, local and reproducible.

## Exit rule

The strongest allowed result is `PASS_WITH_LIMITATIONS` with explicit support
level and current evidence. `PROMOTE` is not implied by passing tests. Any
Critical/High finding, stale required evidence, missing required artifact,
unknown identity or unproven host causality keeps the package at candidate or
blocked status. The old package remains discoverable and read-only.
