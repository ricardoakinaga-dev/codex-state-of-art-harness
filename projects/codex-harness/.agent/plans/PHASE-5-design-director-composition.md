# ExecPlan — PHASE5-001 Design Director Composition Pilot

## Purpose

Implement one bounded, evidence-driven composition slice from a visual task to
a real design-director host response, a project-local artifact, native desktop
and mobile renders, structural verification, blind visual critique, at most
one repair, final verification and assurance. Preserve the frozen Phase 2–4
packets and keep the installed capability read-only.

## Frozen inputs

- Requirements: `/home/ricardo/.codex/attachments/f79f3c31-7f73-4425-a491-262cc181d582/pasted-text-1.txt`
- Quality bar: `docs/implementation/phase-5-quality-bar.md` (`P5-QB-1`)
- Architecture decision: `../../architecture/docs/adr/ADR-014-phase-5-design-director-composition-pilot.md`
- Phase 2 freeze: `evidence/phase-2/PHASE2-FROZEN.md`
- Phase 3 freeze authority: `evidence/phase-3/readiness.json` and
  `.agent/gates/PHASE3-VERIFIED-0004.json` (the historical packet has no
  separate `PHASE3-FROZEN.md` marker)
- Phase 4 freeze: `evidence/phase-4/PHASE4-FROZEN.md`

## Scope boundary

Allowed: one fictional design-director landing-page task, exact package
precheck, one fixed graph, response-only HTML/SVG/CSS artifact materialization,
local browser capture, native structural verification, independent critique,
one justified repair and project-local evidence.

Forbidden: editing/copying/installing any external Skill, executing its
scripts, shell/network/MCP/provider/credential/subagent access, arbitrary graph
composition, unbounded retries, production deployment, global configuration,
backend/API work, game/research directors, or a claim that host-load causality
is proven.

## State and recovery

This plan supersedes the stale Phase 4 active pointer without rewriting
history. Every continuation begins by reading `.agent/state.json`, this plan,
the latest ledger tails and the actual worktree. Artifact/evidence digests are
the source of truth for the current run. A changed artifact invalidates all
earlier verification and requires a new render.

## Work sequence

1. Freeze P5-QB-1, ADR-014, this plan, the P5 scope gate, backlog and state
   transition; record the current Phase 2–4 baseline.
2. Write unit/eval/integration tests first for immutable contracts, exact
   eligibility, graph ownership, budgets, path confinement, stale lineage,
   blocked secondary and assurance.
3. Implement models, package precheck/policy, artifact materialization,
   structural verification and bounded composition orchestration.
4. Add the isolated design-pilot fixture and the explicit task/acceptance
   packet; do not add credentials or copy installed package files.
5. Run a real design-director response-only builder invocation through the
   official app-server only after dry-run and negative tests pass.
6. Render current artifact at 1440×900 and 390×844 through the browser
   boundary; capture console/network/accessibility and artifact digests.
7. Run the native verifier and fresh blind critic. Repair only when a material
   High/Medium gap is identifiable and the one repair budget remains; rerender
   and reverify.
8. Run the baseline/composition benchmark, Phase 2–4 regressions, security,
   coverage, Ruff and mypy. Do not execute installed Skill scripts.
9. Obtain fresh independent visual and engineering review of the exact packet,
   fix only accepted material findings, regenerate all stale evidence and
   close with the P5 report/freeze only if the bar is satisfied.

## Default budgets

```text
builder invocations: 2 maximum
structural verifications: 2 maximum
visual critiques: 2 maximum
repairs: 1 maximum
browser renders: 2 versions × 2 required viewports
host tools/shell/network/MCP/providers/credentials/scripts: 0
```

## Validation commands

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/coverage run --branch --source=src/harness_kernel -m pytest -q -p no:cacheprovider
.venv/bin/coverage report --fail-under=80
.venv/bin/ruff format --check src tests
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

## Expected evidence

The pilot packet is under `evidence/phase-5/pilots/design-director/`; root
reports are under `evidence/phase-5/`. The exact required filenames are frozen
by the user-supplied Phase 5 specification and are not replaced by prose-only
summaries.

## Exit

The strongest permitted result is `PASS_WITH_LIMITATIONS` at Level A, B or C
with explicit support evidence. If the primary package, browser, artifact or
required reviewer remains unavailable, report `FAIL` or `BLOCKED` with exact
limitations; never synthesize a visual result or call a native fallback a real
secondary capability.
