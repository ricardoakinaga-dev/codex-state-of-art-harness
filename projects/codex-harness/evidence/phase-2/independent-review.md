# Independent adversarial review — Phase 2

## Review status

`FINAL_REVIEW_PENDING`. A pre-final independent review was executed by three
read-only peer agents. Each returned `REJECT` against the then-current
candidate and produced findings; the lead implemented and regression-tested
the remediations below. A post-hardening spot review then found three further
findings, which were also fixed and regression-tested. The final critic found
two Medium follow-ups; those are now fixed and the full regression is green.
Independent confirmation against the final packet is still required before any
`PASS_WITH_LIMITATIONS` or `PHASE2-VERIFIED` gate.

## Reviewer mode and independence

- reviewers: `Epicurus` (global contract), `Gauss` (security/authority) and
  `Harvey` (execution/state/evidence/CLI);
- mode: separate read-only peer agents, model `gpt-5.6-sol`,
  `fork_context=false`, no edit permission used;
- result: all three returned `REJECT` before remediation; none changed source,
  tests, configuration or evidence;
- final critic: `Carver`, read-only, model `gpt-5.6-luna`,
  `fork_context=false`, returned `CONDITIONAL_PASS` before the last two fixes;
- final confirmation attempt: `Noether`, read-only, model `gpt-5.6-luna`,
  `fork_context=false`, returned `CONDITIONAL_PASS` after the Carver fixes;
- current candidate source fingerprint after the last fixes:
  `sha256:6d6cd917acf2db16649e66140fa300e2704aea9a900c7f21e10ee0658654ce47`;
  source/test and file-content fingerprints are recorded in `readiness.json`.
  No reviewer approved the exact final evidence bytes after the ledger and
  readiness reconciliation below.

## Scope and methodology

The review packet covered the requested domains A–AE: authority and replay;
provider, reviewer, verification and assurance privilege boundaries; invalid
states; stale evidence; failed DAG dependencies; cancellation, timeout, retry,
repair, no-progress and oscillation; telemetry and fixture honesty; path,
symlink, persistence and recovery; malformed and oversized input; secret
redaction; invalid routes; scope/provenance/source changes; CLI and benchmark
surfaces. Reviewers inspected source, tests, project-local configuration and
evidence, then returned severity, evidence and remediation findings. The lead
reran focused tests, full coverage, lint, typecheck, CLI integration and the
control-state checker after the fixes.

## Findings, root causes and remediation

| ID | Severity | Root cause and evidence | Fix, regression and residual |
| --- | --- | --- | --- |
| `P2-IR-001` | Critical | Provider output/artifact shape could be promoted without an exact typed contract check. | `verification.py` now checks exact output and artifact identity, keys, contract, digest and lineage. Covered by `test_wrong_output_contract_cannot_promote_quality`, forged digest tests and the 100-test focused regression. |
| `P2-IR-002` | High | Registry accepted an arbitrary custom provider implementation at the Phase 2 boundary. | `providers.py` admits only the exact built-in deterministic provider types; registration and constructor tests reject untrusted implementations. Residual hostile-code execution remains outside P2. |
| `P2-IR-003` | High | Provider readiness/resolution could precede authority denial or dry-run checks. | `execution.py` authorizes and snapshots before resolve/call; expired authority, dry-run and subject tests verify no provider execution. |
| `P2-IR-004` | Critical | Retry and graph paths did not share a real global deadline or count started attempts consistently. | Shared monotonic deadlines, attempt accounting and graph budget propagation were added. Direct and graph retry-duration tests verify timeout, actual calls and no artifact. |
| `P2-IR-005` | High | Graph provider admission and terminal/active replay validation were incomplete. | All graph providers are preflighted before scheduling; active/terminal graphs are rejected before calls. Covered by graph preflight and replay tests. |
| `P2-IR-006` | High | Route selected/unavailable provider state could diverge and permit ambiguous execution. | Route reconciliation moves unavailable providers to `omitted`, removes overlap, records `PROVIDER_UNAVAILABLE`, and keeps material uncertainty conditional. Covered by unavailable-provider, manifest mismatch and material-conditional tests. |
| `P2-IR-007` | High | Recovery and assurance could accept stale, unrelated or incomplete evidence/artifact packets. | `persistence.py`, `evidence.py`, `verification.py` and `assurance.py` now bind task/run/report/artifact identities, content digests, producer refs, full packet digests and typed dependent bundles. Covered by tamper, stale, forged-packet, link and incomplete-bundle tests. |
| `P2-IR-008` | High | Repair exhaustion could continue through repeated failure, no progress or oscillation. | Repair history and `StopBudget` now terminate bounded repair with explicit limitations and provenance. Covered by repair success/exhaustion and stop tests. |
| `P2-IR-009` | High | Telemetry limitation text and provenance source refs were not comprehensively redacted/bounded. | `telemetry.py` validates timestamps, bounds limitations and redacts key/value, bearer and record source refs. Covered by limitation and sensitive-source tests. |
| `P2-IR-010` | High | Persisted artifact locators were not fully tied to the owning run and canonical project boundary. | `RunStore` requires the canonical project-local run locator and validates typed artifact/evidence/telemetry/lifecycle bundles on recovery. Covered by locator and persistence tamper tests. |
| `P2-IR-011` | Medium | Graph authority identity, direct mapping size/non-finite values and timestamp validation had weak boundaries. | Graph uses `INV-{run_id}-{node_id}`, deserialization rejects oversized/non-finite data, and telemetry timestamps require a timezone and time component. Covered by the corresponding adversarial tests. |
| `P2-IR-012` | High | Source-only coverage was below the P2 threshold because coverage configuration and subprocess CLI paths were not bound consistently. | `pyproject.toml` defines `src/harness_kernel` as the coverage source; clean run now records 85%. |
| `P2-IR-013` | High | Public assurance retained a report-only compatibility path that could bypass the current evidence/artifact packet. | `assure_quality` now blocks unless both current evidence and artifact collections are supplied; a RED→GREEN test (`test_assurance_requires_the_current_packet_even_for_typed_reports`) and the focused regression prove the boundary. |
| `P2-IR-014` | Medium | Full pytest collection depended on incidental import order for `phase2_support`. | `pyproject.toml` adds `tests/unit` to pytest's explicit `pythonpath`; the clean 232-test collection now passes. This is a test-harness correction, not a runtime capability. |
| `P2-IR-015` | High | The post-hardening spot review found that artifact verification checked content and invocation identity but did not bind `artifact.provenance.tool_or_process` to the provider result identity. A forged artifact from another provider could therefore pass the local contract. | `verification.py` now requires provider/artifact provenance identity equality. `test_artifact_provider_lineage_must_match_the_provider_result` was written RED, then passes in the 232-test full regression. |
| `P2-IR-016` | Medium | The post-hardening spot review found that verification could label an observation `FRESH` using a caller/kernel timestamp without proving observed provider start/end timestamps and invocation correlation. | `verification.py` now derives and validates an observed timestamp packet, marks missing/mismatched observations `STALE`, and records explicit freshness reasons. `test_verification_rejects_stale_or_missing_observed_timestamps` was written RED, then passes in the 232-test full regression. This is packet consistency, not a production wall-clock guarantee. |
| `P2-IR-017` | Medium | The post-hardening spot review found that a raising cancellation callback escaped as an untyped runtime error in direct and graph execution. | `execution.py` and `graph.py` now fail closed through `_cancel_requested`, converting callback errors into typed cancellation. `test_raising_cancellation_callback_is_normalized_to_terminal_cancel` and `test_raising_graph_cancellation_callback_is_normalized` were written RED, then pass in the 232-test full regression. |
| `P2-IR-018` | Medium | Carver found that `execution.py` replaced missing provider `started_at`/`ended_at` values with the kernel timestamp before verification, allowing a malformed success result to look fresh. | The executor no longer normalizes absent provider observations. Built-in fixtures explicitly emit their deterministic observation envelope, success without timestamps fails before artifact creation, and aggregate reports inherit `STALE`. `test_execution_does_not_promote_success_without_observed_timestamps` was written RED, then passes in the 232-test full regression. |
| `P2-IR-019` | Medium | Carver compared the direct `pyproject.toml` content hash with the readiness manifest hash and reported an apparent fingerprint mismatch. The packet did not make the two hash semantics explicit. | `readiness.json` now records both the sorted-file manifest digest and the direct content digest (`0f06746386a89b03dcca9009662b405b86856d44dc101fe041885f29c4297485`) for `pyproject.toml`; current source/test hashes and the final benchmark are regenerated. |
| `P2-IR-020` | Medium | Noether found that the final ledger and evidence fingerprints were stale after the last reconciliation, even though the source, tests, configuration and pyproject content agreed. | The lead recomputes the current `.agent` fingerprint and the self-excluding `evidence/phase-2` packet fingerprint after all ledger changes, records both in `readiness.json`, and reruns the control-state and packet checks. |

No Critical/High finding from the pre-final or post-hardening review remains
intentionally open in the implementation. Findings `P2-IR-015` through
`P2-IR-020` are fixed or reconciled and covered by the current regression where
applicable. Carver and Noether returned `CONDITIONAL_PASS`; their reviews are
not represented as approval of the exact final packet because the lead's
fingerprint reconciliation necessarily changed the evidence bytes afterward.

## Post-hardening spot review

Reviewer `Sartre` performed a read-only adversarial spot review after the
pre-final remediations. The reviewer used model `gpt-5.6-luna`, made no edits,
and returned `INDEPENDENCE_BLOCKED`: one High artifact-lineage issue and two
Medium freshness/cancellation issues were identified. The reviewer also found
no other actionable Critical/High/Medium issue in authority, provider, retry,
deadline or graph scheduling. At review time the source fingerprint was the
pre-fix value `sha256:b8a00f0598488cbf6d2268162ee5bc733b47349911e9214da1605902f344d318`
and readiness still said final review was pending; this report therefore does
not treat that result as approval of the current source fingerprint.

## Final critic review

Carver inspected the post-hardening source, tests, readiness packet and
independent-review report in read-only mode. The verdict was
`CONDITIONAL_PASS`: no Critical or High issue remained, but the reviewer
identified `P2-IR-018` (timestamp normalization at the execution boundary) and
`P2-IR-019` (ambiguous direct-file versus manifest fingerprint semantics).
Those findings were addressed with the current 232-test regression and the
dual fingerprint recording above. Because the final source/evidence packet
changed after Carver's inspection, this is not treated as a final approval of
the current fingerprint.

## Final confirmation attempt

Noether performed a fresh read-only confirmation after Carver's report and the
source fixes. The reviewer ran focused timestamp/lineage and cancellation
checks plus Ruff and mypy, found no actionable Critical, High or Medium
implementation defect, and returned `CONDITIONAL_PASS`. The only actionable
follow-up was `P2-IR-020`: the `.agent` and evidence fingerprints in the
readiness packet were stale after the final ledger append. The lead reconciled
those fingerprints and reran the packet/control checks. Because that
reconciliation changed the final evidence bytes, Noether's result is recorded
as independent confirmation of the reviewed implementation, not approval of
the exact post-reconciliation packet.

## Bounded route rationale

The classifier may retain low-impact classification/evidence uncertainty for a
fixture task. The kernel permits an explicit built-in local fixture route only
when the remaining unresolved items are non-material; material risk, scope,
security, data, complexity or fallback uncertainty remains `CONDITIONAL` and
cannot execute. `test_materially_conditional_route_cannot_execute` is the
blocking proof. This nuanced local-fixture exception is a declared Phase 2
limitation, not permission to execute arbitrary conditional routes.

## Residual limitations

- A timed-out provider runs in a daemon thread that the coordinator cannot
  forcibly stop. Phase 2 admits only deterministic built-in fixtures and does
  not claim hostile-code sandboxing or production isolation.
- The project has no real Codex host/provider/Skills/subagents/MCP/shell/network
  integration, advanced concurrency, multi-process locking, production SLO or
  causal/AAA quality proof.
- `pip-audit` is unavailable in the local environment; the static runtime scan
  passes, but no unavailable scanner is represented as a pass.
- The worktree is intentionally dirty after closeout hardening; `HEAD` and
  per-tree fingerprints are recorded in `readiness.json`. Historical ledger
  entries remain append-only and are not rewritten.
- Deterministic fixture timestamps establish packet consistency, not wall-clock
  freshness or production observability.

## Verdict

`CONDITIONAL_PASS_PENDING_FINAL_REVIEW`. The independent reviews found material
issues and the lead fixed them with focused regressions. A final independent
read-only confirmation must inspect the current source fingerprint, tests,
evidence and this report. Until it returns a usable verdict against the final
packet, no `PASS_WITH_LIMITATIONS`, `PHASE2-VERIFIED` or `AAA_VERIFIED` claim is
made.
