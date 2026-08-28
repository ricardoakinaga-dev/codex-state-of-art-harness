# 40 — Risk Register

| ID | Risk | Probability | Impact | Mitigation | Monitoring |
| --- | --- | --- | --- | --- | --- |
| R-01 | overengineering / too many layers | high | high | no-skill route, delegation gate, first vertical slice | activation rate, simple-task latency, context cost |
| R-02 | token inflation/context explosion | high | high | progressive disclosure, budgets, loaded trace | tokens, references, cache/compaction, quality delta |
| R-03 | latency from fan-out/review | medium | medium/high | parallelize only independent lanes, bounded critic | p50/p95 wall time, retry/queue trace |
| R-04 | routing error/miss | medium | high | adjudicated scenarios, negative routing, fallback | precision/recall, miss/overactivation |
| R-05 | skill collision/duplicate authority | high | high | registry owner/conflict contracts, canonical paths | route trace, duplicate validator, drift audit |
| R-06 | tool misuse/provider mismatch | medium | high | deliberate tool matrix, preflight, type-specific provider | tool errors, fallback, artifact provenance |
| R-07 | security/secret exposure | low/medium | critical | least privilege, redaction, sandbox, human stops | denied events, secret scanner, security review |
| R-08 | complexity explosion/maintenance burden | medium | high | reason-to-exist test, modular package, ADR supersession | change surface, dependency cycles, stale refs |
| R-09 | eval gaming/invalid oracle | medium | high | known-bad, frozen controls, blind graders, audit harness | control failures, score drift, revalidation |
| R-10 | false confidence / premature done | high | critical | verification evidence, freshness, required gates, limitations | unrun claims, stale evidence, reopened gates |
| R-11 | critic bias or unavailable independent reviewer | medium | high | blind packet, independence field, stronger deterministic checks | reviewer overlap, missing review evidence |
| R-12 | infinite/repeated loops | medium | high | max attempts, no-progress, oscillation, budget stops | retry/stop traces, repeated fingerprints |
| R-13 | upstream/provider drift | high | medium/high | version/provenance, compatibility, modernization template | source revalidation, schema errors |
| R-14 | dependency/provider lock-in | medium | medium/high | adapters, fallback, native-first, compare providers | fallback success, migration cost |
| R-15 | documentation drift from implementation | medium | high | traceability, audit/reopen gates, integration review | orphan requirements/artifacts, stale refs |
| R-16 | wrong human authority/residual risk acceptance | low/medium | critical | exact scoped authority records, expiry, no inferred approval | authority ledger, overrides, revalidation |
| R-17 | generic AI output / low specificity | medium | medium/high | domain profile, product-specificity test, human/domain eval | critique findings, quality dimensions |

## Risk treatment

Probability/impact are qualitative and must be revised with evidence. A high/critical residual risk cannot be hidden by average score or conditional pass. Security, irreversible action, data deletion, credential handling, financial/regulatory and material architecture decisions cross a human boundary.

## Top critical risks

R-07, R-10, R-12 and R-16 are release-blocking when exposed. R-01, R-02 and R-05 threaten the premise of the Harness itself and must be measured from P0.

## Review trigger

Reopen the register when scope, host capability, provider, data, threat, architecture, metric validity or authority changes. A risk without owner, mitigation, monitoring and trigger is not managed.
