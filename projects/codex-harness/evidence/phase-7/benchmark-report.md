# P7-BENCH-1 benchmark report

Comparison label: `PILOT_MODERNIZATION_EVIDENCE`.

All four records use the same normalized fictional task,
`P7_TASK_VET_APPOINTMENT_001`. The comparison is intentionally non-causal: the
current and upstream packages were inspected but not executed, the native path
is a general-surface observation, and the vNext path includes one real bounded
pilot. Scores are evidence summaries for this pilot, not SLOs or proof of
universal superiority.

| Path | Outcome | Functional | Architecture | Verification | Coverage | Findings | Repairs |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| installed current `backend-patterns` | `BLOCKED` / not executed | n/a | n/a | n/a | n/a | n/a | 0 |
| upstream `backend-patterns` | `BLOCKED` / not executed | n/a | n/a | n/a | n/a | n/a | 0 |
| native/minimal Codex surface | `PARTIAL` | 0 | 35 | 0 | n/a | 0 | 0 |
| project-local vNext | `PASS_WITH_LIMITATIONS` | 100 | 88 | 100 | 91 | 1 lead finding | 1 |

The vNext scores mean that the pilot acceptance criteria were evidenced, that
the bounded layered design fit the declared pilot, and that the verifier
receipt resolved the four required procedures. The architecture score is below
100 because this is a disposable pilot with intentionally limited identity/read
authorization and no external dependency boundary.

Measured context/latency facts are in `benchmark-summary.json` and
`context-cost-report.md`. Missing values are reported as unavailable rather
than inferred. Critical false PASS is zero. This packet makes no causal claim.
