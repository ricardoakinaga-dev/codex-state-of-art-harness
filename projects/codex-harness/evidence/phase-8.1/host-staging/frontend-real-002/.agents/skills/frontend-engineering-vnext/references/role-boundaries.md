# Role and handoff boundaries

| Role | Owns | Does not own |
| --- | --- | --- |
| Router/director | task classification, strategy, bar and graph | implementation or proof |
| `frontend-engineering-vnext` | frontend implementation and domain handoff | visual approval, factual verification, security approval or release |
| `design-director` | visual thesis, art direction, design system and visual critique | backend/API authority or factual verification |
| `verification-loop-vnext` | criterion/evidence identity, freshness and deterministic facts | building, repairing or judging visual quality |
| visual critic | read-only comparison and findings | editing, score laundering or self-approval |
| `security-review` | security assessment and escalation | product/design acceptance or release |
| assurance/gauntlet | challenge, stop and residual-risk decision | silently lowering the bar |

The builder's output is an implementation handoff, not a release decision.
Every role records what it observed, what it inferred and what remains
unknown. The final packet keeps builder, verifier, critic and assurance
identities separate.
