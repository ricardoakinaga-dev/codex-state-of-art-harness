# 38 — Phased Implementation Roadmap

## Sequência proposta

| Phase | Outcome | Exit criteria |
| --- | --- | --- |
| `PHASE 0 — Documentation` | source-of-truth architecture, contracts, ADRs, eval plan | docs inventory/link/consistency gate; independent review; no Critical open |
| `PHASE 1 — Core contracts` | parse/validate TaskProfile, RouteDecision, Evidence/Artifact/RunSummary | known-bad schema tests; versioning/provenance; public API contract |
| `PHASE 2 — Router` | direct/no-skill + scale/risk/domain routing | adjudicated routing suite, precision/recall, overactivation/cost baseline |
| `PHASE 3 — Authority / state` | transitions, gates, blockers, recovery pointers | invalid transition tests, append-only ledger, no unauthorized bypass |
| `PHASE 4 — Verification` | procedure runner/report/evidence freshness | real boundary checks, stale invalidation, current report binding |
| `PHASE 5 — Director integration` | one engineering Director + handoff/quality bar | one vertical slice from goal to verification, no self-approval |
| `PHASE 6 — Capability registry` | manifests, versions, dependencies, conflicts | duplicate/unknown dependency validator, package provenance |
| `PHASE 7 — Telemetry` | event correlation, load/tool/cost/retry trace | event completeness/redaction; host-load causality test |
| `PHASE 8 — Modernization pilot` | one Skill vNext (recommend engineering-framework or verification) | current/upstream/vNext A/B, promotion decision, rollback |
| `PHASE 9 — Expanded specialists` | design/research/game/data/infrastructure Directors as earned | domain evals + route boundaries + independent review |
| `PHASE 10 — Full eval suite` | permanent regression, human eval, benchmarks, learning loop | release candidate passes required profiles and re-audit |

## Critical path

```text
documentation → contracts → router → state/authority → verification
              → one Director → registry → telemetry → modernization
              → expanded domains → full evals
```

Do not implement all specialists before router/verification can show whether they help. Do not modernize installed Skills before canonical authority and benchmark control exist.

## Phase gate discipline

Each phase has a written Quality Bar, known-bad fixture, evidence ledger, rollback/recovery plan where needed, and independent review proportional to risk. A phase can be `CONDITIONAL` only with non-blocking typed conditions and due date; unresolved high/critical risk blocks.

## Success measures

- simple tasks stay direct with low latency/context;
- route precision/recall improve against adjudicated minimum;
- loaded context/cost measured, not guessed;
- required claims have current evidence;
- no Critical security/authority/data gap;
- specialist promotion demonstrates domain quality delta, not just more text;
- failures degrade honestly and recoverably.

## Human decisions reserved

Canonical duplicate path, host-load instrumentation, security/privacy policy, release authority, provider contracts, data retention, and any production migration remain human/organizational decisions when material.
