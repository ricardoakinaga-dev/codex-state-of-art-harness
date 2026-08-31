# Phase 7.3 Feature-Freeze Finding Map

Feature freeze: `P7_3_FEATURE_FREEZE`.

All implementation changes in this phase are evidence/control tooling or its
tests. No `src/` application module, pilot application module, migration, API
contract, installed package, global configuration, provider, MCP, shell,
network, or credential surface was changed.

| Path set | Finding / contract | Purpose |
| --- | --- | --- |
| `scripts/phase73_risk_semantics.py` | `P7.3-FINDING-RISK-SEMANTICS` / P73-03 | Canonical materiality, closure, actionable and promotion-blocking counts |
| `scripts/generate_phase73_inventory.py` | `P7.3-FINDING-INVENTORY` / P73-04/P73-05 | Convert the current residual set without dropping branch identity |
| `scripts/generate_phase73_decisions.py` | `P7.3-FINDING-MEDIUM-CLOSURE` / P73-05 | Supply explicit decisions for every current Medium |
| `scripts/validate_phase73_consistency.py` | `P7.3-FINDING-COUNT-CONSISTENCY` / P73-06 | Reject drift across inventory, readiness, ledger and final report |
| `scripts/generate_phase73_ledger.py` | `P7.3-FINDING-PROMOTION-LEDGER` / P73-07/P73-09 | Bind every High/Medium, host limitation and scanner limitation |
| `scripts/capture_phase73_environment.py` | `P7.3-FINDING-HOST-SCANNER-EVIDENCE` / P73-08/P73-09 | Capture pinned host resolution and scanner availability without installation |
| `scripts/run_phase73_real_cycle.py` | `P7.3-FINDING-REAL-CYCLE` / P73-08/P73-12 | Execute the bounded builder → repair → verifier receipt chain |
| `scripts/generate_phase73_manifest.py` | `P7.3-FINDING-EXACT-PACKET` / P73-10/P73-13 | Hash the exact current source, tests, control plane and evidence packet |
| `tests/unit/test_phase73_*.py` | P73-03 through P73-13 | TDD coverage for the Phase 7.3 evidence contracts |
| `tests/unit/test_phase2_execution_paths.py` | `P7.3-FINDING-TEST-STABILITY` / P73-11/P73-12 | Widen a scheduler-sensitive timeout fixture from 15ms to 100ms while retaining the timed-out outcome assertion |

The only formatter normalization observed during the real cycle occurred in
the disposable `artifact-v3`; it is not a repository source change and is
recorded in `real-cycle-report-005.json`.
