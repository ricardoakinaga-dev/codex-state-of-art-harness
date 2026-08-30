# Phase 7.1 Branch Inventory

Generated from the exact `coverage json` output recorded in the JSON
inventory. No branch is excluded by this generator.

- statements: `19447`; line coverage: `89.12942870365609%`
- branches: `7408`; covered: `6031`; missing: `1377`
- partial branches: `1233`; branch coverage: `81.41198704103672%`
- files with uncovered branches: `61`

## Classification counts

| Category | Count | Rule |
| --- | ---: | --- |
| `HIGH_VALUE_FAILURE_PATH` | 509 | authorization, security, dependency, retry, timeout, cancellation, evidence freshness, artifact, scope or progress vocabulary |
| `LOW_VALUE_DEFENSIVE_BRANCH` | 665 | remaining branch requiring qualitative review before exclusion |
| `MEDIUM_VALUE_BRANCH` | 203 | parser, validation or defensive branch without a higher-risk boundary keyword |

## Highest-risk files

| File | Missing branches | High/critical branches |
| --- | ---: | ---: |
| `src/harness_kernel/phase4_execution.py` | 99 | 26 |
| `src/harness_kernel/phase4_host.py` | 93 | 39 |
| `src/harness_kernel/phase6_models.py` | 89 | 24 |
| `src/harness_kernel/phase7_host.py` | 88 | 34 |
| `src/harness_kernel/execution.py` | 71 | 37 |
| `src/harness_kernel/phase4_models.py` | 66 | 30 |
| `src/harness_kernel/cli.py` | 63 | 25 |
| `src/harness_kernel/phase5_cli.py` | 53 | 26 |
| `src/harness_kernel/phase5_models.py` | 51 | 10 |
| `src/harness_kernel/persistence.py` | 48 | 19 |
| `src/harness_kernel/phase7_backend.py` | 34 | 16 |
| `src/harness_kernel/classification.py` | 34 | 0 |
| `src/harness_kernel/phase3_paths.py` | 34 | 34 |
| `src/harness_kernel/graph.py` | 32 | 4 |
| `src/harness_kernel/phase6_composition.py` | 30 | 6 |
| `src/harness_kernel/validation.py` | 29 | 7 |
| `src/harness_kernel/phase3_discovery.py` | 27 | 9 |
| `src/harness_kernel/phase4_policy.py` | 27 | 6 |
| `src/harness_kernel/phase6_checks.py` | 26 | 7 |
| `src/harness_kernel/phase3_parser.py` | 23 | 0 |
| `src/harness_kernel/phase5_pilot.py` | 22 | 3 |
| `src/harness_kernel/phase4_evidence.py` | 22 | 22 |
| `src/harness_kernel/phase4_verification.py` | 20 | 14 |
| `src/harness_kernel/registry.py` | 20 | 4 |
| `src/harness_kernel/phase3_cli.py` | 18 | 1 |

## Review protocol

The Lead reviewed every classified branch against the failure-path
matrix. A branch is treated as `TESTED` only when a test asserts
externally visible state, error, side effect, rollback, telemetry or
evidence. A branch may be
marked `EXCLUDED_WITH_REASON` only with an exact contract and platform
justification; this inventory contains no exclusions.
