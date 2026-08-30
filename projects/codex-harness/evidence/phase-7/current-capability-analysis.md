# Current `backend-patterns` capability analysis

## Evidence basis

The immutable package at `/home/ricardo/.agents/skills/backend-patterns` was
inspected at the timestamp in `current-backend-patterns-snapshot.json`. It
contains only `SKILL.md` and `agents/openai.yaml`; the exact file hashes and
package fingerprint are recorded there. No installed file was copied, edited,
moved, replaced or installed.

## Findings

| Weakness | Severity | Impact | vNext requirement |
| --- | --- | --- | --- |
| Legacy package lacks native manifest, typed contracts and provenance fields | High | Phase 3 can only synthesize bounded metadata; Phase 4 cannot bind a native execution policy | Native manifest, input/output contract, identity and exact provenance |
| Activation list is broad and no explicit non-activation/stop model is declared | Medium | Trivial or documentation work can be over-routed and unsafe escalation has no package-level stop | Narrow positive/negative routing plus explicit finite stops |
| Architecture guidance presents repository/service/controller patterns without a preservation decision | Medium | Codex may add layers or a framework without proving the problem | Inspect existing architecture, state smallest-change decision and reject ceremony |
| API, validation, error, auth and persistence concerns are described as patterns rather than a bound contract | High | Breaking API/data behavior can pass by explanation | Typed route/data/error/authorization contract and tests |
| Transaction, idempotency and concurrency guidance is incomplete as an implementation obligation | High | Retries/races can duplicate writes or violate invariants | Declare atomicity/retry/idempotency and use database constraints |
| Migration and rollback safety is not an executable evidence boundary | High | Destructive or partially applied schema changes may be proposed | Apply/verify/compatibility/rollback evidence and unsafe-migration stop |
| Generic reliability/performance/caching advice is not risk- or budget-shaped | Medium | Blind retries, stale cache or premature optimization can be introduced | Evidence-based budgets, explicit retry/timeout/degradation policies |
| Security guidance is adjacent to `security-review` but no formal handoff contract exists | High | Builder can imply security approval or skip a material handoff | Security trigger matrix and separate read-only/final security authority |
| Testing and verification are recommendations, not immutable handoff evidence | High | A builder can report success without current artifact/test identity | Risk-shaped tests, builder receipt and verifier handoff with fresh digests |
| No scripts/evals/benchmarks/references package exists | Medium | Capability quality cannot be measured or progressively disclosed | Bounded deterministic checks, serious eval catalog and honest benchmark |

The installed package remains valuable as a compact pattern vocabulary and
benchmark baseline. These findings justify a specialist modernization; they do
not justify editing or deprecating the current package.
