# P4-QB-1 — Real Capability Invocation Quality Bar

This is the blocking acceptance bar for `PHASE4-001`. It applies only to the
bounded pilot and never authorizes an `AAA_VERIFIED` claim for the Harness.

| ID | Blocking criterion | Required evidence |
| --- | --- | --- |
| P4-01 | Phase 2 regression remains green | `phase2-regression.md` |
| P4-02 | Phase 3 regression remains green | `phase3-regression.md` |
| P4-03 | Official host semantics are classified | host matrix + source/observation labels |
| P4-04 | Authorization binds ID/version/scope/fingerprint | authorization tests + receipt |
| P4-05 | No authorization, stale bytes or divergent duplicate can invoke | negative tests/evals |
| P4-06 | Explicit pilot allowlist is separate from routability/loadability | policy and allowlist JSON |
| P4-07 | Dry-run and prepare-only perform no host request | invocation tests + telemetry |
| P4-08 | Controlled-real requires explicit opt-in and fingerprint confirmation | CLI tests |
| P4-09 | Workspace, symlink and host-reported artifact paths are confined | boundary tests |
| P4-10 | Shell/scripts/network/MCP/providers/credentials/tools are denied by default | policy tests + security scan |
| P4-11 | Context size, host events, tools, artifacts and evidence are bounded | budget tests + receipt |
| P4-12 | Lifecycle forbids invalid transitions and replay | state-machine tests |
| P4-13 | Timeout and cancellation are truthful and cannot become PASS | adapter/eval tests |
| P4-14 | Host invocation and Skill-load causality are distinguished | causality report |
| P4-15 | Results bind acceptance criteria, artifact, evidence and verification | verification report |
| P4-16 | Real pilot or official-host limitation is recorded | pilot report |
| P4-17 | No global mutation occurs | before/after fingerprints + security report |
| P4-18 | Combined coverage is at least 80% | coverage report |
| P4-19 | Ruff and strict mypy pass | lint/type reports |
| P4-20 | P4-BENCH-1 is reproducible and separates Harness/host latency | benchmark JSON |
| P4-21 | Exact packet receives independent read-only review | manifest + attestation |
| P4-22 | No Critical or High findings remain open | independent review |

## Support levels

- `P4_LEVEL_A`: safe invocation infrastructure is verified, but the official
  host cannot perform a supported real invocation.
- `P4_LEVEL_B`: a real host invocation occurs, but Skill-load or execution
  causality is not fully observable.
- `P4_LEVEL_C`: a real invocation and the relevant host load/execution
  causality are both directly observable.

Level C is not a default target. The packet must use the level supported by
fresh evidence.

## Allowed closeout statuses

`PASS_WITH_LIMITATIONS`, `CONDITIONAL_PASS` and `FAIL` are the only valid final
statuses. `PASS_WITH_LIMITATIONS` requires all blocking criteria to pass, a
valid controlled pilot or documented official-host limitation, exact-packet
independent review and zero Critical/High findings.
