# Codex Capability Harness Documentation ExecPlan

## Purpose / Big Picture

Create a self-contained reference architecture for a future Codex Capability Harness. The artifact replaces the mental model of a flat folder of Skills with an adaptive capability architecture while remaining explicitly documentation-only. A future engineer must be able to classify a task, select capabilities, understand authority, compose specialists, verify claims, run bounded assurance, manage context, observe cost/quality, create a capability package, modernize a Skill, and plan implementation without inferring hidden rules.

## Progress

- [x] 2026-08-28T08:33:42-03:00 — Read supplied specification, repository inventory, engineering/gauntlet/orchestration instructions, design-director, audit reports, local Codex research, and current official OpenAI pages.
- [x] 2026-08-28T08:42:00-03:00 — Draft foundation and canonical vocabulary.
- [x] 2026-08-28T08:58:00-03:00 — Draft execution, quality, security, observability, domain, and governance documents.
- [x] 2026-08-28T09:14:00-03:00 — Validate links, file coverage, examples, diagrams, contract references, and forbidden implementation leakage.
- [x] 2026-08-28T09:20:08-03:00 — Obtain independent review, repair, and issue final report.

## Surprises & Discoveries

- The workspace is not a Git repository and contains only `skill-audit/`; Git diff evidence is therefore unavailable.
- The local audit reports 41 Skill paths, 40 declared names, 39 visible names, and one byte-identical duplicate of `engineering-framework`.
- The current host-load/selection trace is not exposed in the audit; self-reported routing is explicitly non-causal evidence.
- Current official docs distinguish Skills (workflow/instructions/resources), MCP (live tools/context/actions), AGENTS.md (instruction chain), project config, and subagents. The future harness must compose these without claiming undocumented host internals.

## Decision Log

1. The canonical authority model will preserve system/developer/user/safety authority outside the harness and use an internal control-plane ordering only for responsibility, never for instruction override.
2. `engineering-framework` is the proposed Director authority; `orchestrate` is conditional execution mechanics; `verification` owns evidence; `gauntlet` owns independent quality challenge and bounded stopping.
3. A no-skill/direct route is a first-class route, not a failure case.
4. The design-director pattern is a golden reference for direction, deliberate medium/tool choice, evidence, critique, progressive disclosure, and bounded iteration; its visual-specific rules do not become universal rules.
5. All contracts in this phase are conceptual JSON Schema pseudocode. They do not create a runtime or imply implementation.

## Outcomes & Retrospective

Delivered 45 numbered docs, 10 ADRs, 12 diagrams, 12 conceptual contracts and a master spec. Five read-only review passes were used; the final pass approved with limitations. The main useful repair was forcing canonical parity between narrative and contracts rather than accepting merely plausible prose. The future implementation must prove host-load causality and Mermaid/runtime validation; those are intentionally not claimed here.

## Context and Orientation

Primary requirements: the supplied pasted text. Current-state evidence: `../../references/skill-audit/`. Current Codex facts: official links listed in `../../architecture/docs/README.md` and `../../architecture/docs/00-vision.md`. The master spec is `../../architecture/HARNESS-SPEC.md`; `../../architecture/docs/README.md` is the navigation index; `../../architecture/docs/41-glossary.md` is canonical vocabulary; `../../architecture/docs/contracts/` owns schema fragments.

## Scope and Constraints

In scope: architecture, contracts, roles, routing, evidence, assurance, state, telemetry, evals, security, modernization plan, examples, ADRs, Mermaid diagrams, repository proposal, and implementation roadmap.

Out of scope: runtime, production code, installed Skill changes, Skill replacement/installation, global Codex config, migration, deployment, push, and external state changes.

## Architecture and Interfaces

The proposed flow is `GOAL → CLASSIFY → ROUTE → DIRECT → ORCHESTRATE? → SPECIALIZE → INTEGRATE → VERIFY → REVIEW → ASSURE → DELIVER → EVAL/TELEMETRY`. The question mark is normative: orchestration requires a delegation gate. `../../architecture/docs/02-system-architecture.md`, `../../architecture/docs/04-authority-model.md`, `../../architecture/docs/06-routing-system.md`, and `../../architecture/docs/contracts/` own the interfaces.

## Milestones

### M1 — Foundation and control plane

Documents `00`–`04`, `README`, glossary seed, and source boundary. Exit: problem, scope, principles, architecture terms, and authority hierarchy are explicit.

### M2 — Adaptive execution

Documents `05`–`12`. Exit: task classification, routing, orchestration, Director/Specialist boundaries, package anatomy, and composition contracts are actionable.

### M3 — Proof and runtime semantics

Documents `13`–`27` and contracts. Exit: claims/evidence, assurance, stop states, context, tools, telemetry, failure/degradation, artifacts, and execution state are coherent.

### M4 — Domains, modernization, governance

Documents `28`–`44`, ADRs, diagrams, repository proposal, roadmap, priority/risk, index, and master spec. Exit: future implementation order, review surface, examples, and open decisions are explicit.

### M5 — Documentation gauntlet

Completed deterministic checks and five independent review passes, fixed the largest gaps, reran integrated checks, and issued `../../architecture/docs/44-final-documentation-report.md` with `YES — WITH PHASE-1 GATES`.

## Plan of Work

Keep terminology and contract names stable before writing dependent documents. Draft sequentially by milestone. Use local audit facts only when cited; label target design as `PROPOSED`. Use official OpenAI links for current Codex facts. Do not add production implementation.

## Concrete Steps

1. Integrate read-only scout evidence and reconcile contradictions.
2. Draft foundation and update the source index.
3. Draft adaptive execution documents and define the canonical route output.
4. Draft proof/quality/security/state documents and conceptual schemas.
5. Draft domain/modernization/governance artifacts, ADRs, diagrams, examples, index, and master spec.
6. Validate file inventory, internal links, cross-references, example count, diagram inventory, contract fields, and forbidden implementation leakage.
7. Ask a fresh read-only critic to inspect the integrated set against the frozen bar.
8. Fix the largest material gap, rerun focused and integrated checks, and issue the final report.

## Validation and Acceptance

The frozen bar is recorded in `.gauntlet/state.md`. Required evidence includes deterministic inventories, link checks, exact counts, cross-document inspections, current official-source links, a no-implementation scan, and independent review. No prose-only claim can pass a required criterion.

## Risks and Human Decisions

Main risks are overengineering, false current-Codex claims, inconsistent terminology, schema drift, unsupported AAA claims, and documentation that cannot guide a simple task. Human decisions still required in the future implementation phase include canonical duplicate handling, host telemetry availability, risk authority, and whether any proposed capability earns promotion.

## Idempotence and Recovery

All outputs are hand-authored Markdown/Mermaid/JSON-like conceptual artifacts. Rerunning validation is read-only and idempotent. On continuation, inspect the current filesystem, this plan, `.gauntlet/state.md`, and any existing docs before changing anything. Never erase prior review/audit history; repair by editing current design and record the new evidence in `../../architecture/docs/42`, `../../architecture/docs/43`, and the final report.

## Artifacts and Evidence

- Requirements: attachment path above.
- Baseline: `../../references/skill-audit/reports/99-final-audit.md` and linked reports/data.
- Current Codex baseline: `/home/ricardo/.codex/skills/engineering-framework/docs/codex-research.md`.
- Official docs: linked from `../../architecture/docs/README.md`.
- Final audit/review/report: `../../architecture/docs/42-documentation-audit.md`, `../../architecture/docs/43-independent-review.md`, `../../architecture/docs/44-final-documentation-report.md`.
