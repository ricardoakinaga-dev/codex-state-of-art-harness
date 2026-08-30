# Phase 6 Benchmark Report

The four baseline rows are explicitly marked fixture-only and make no causal
claim. The real vNext row is the bounded pilot below.

| Item | Result | Evidence |
| --- | --- | --- |
| current installed | BLOCKED fixture | `current snapshot` |
| upstream | REFERENCE fixture | `upstream-analysis.md` |
| native | PASS fixture | `benchmark-fixtures.json` |
| vNext real pilot | PASS_WITH_LIMITATIONS | `sha256:dc380396cdc489976b5d120a964321032907f0101431786cda060dae15c11a4b` |
| critical false PASS | 0 | `eval-execution.json` |
| negative-case block rate | 100.0% | `eval-execution.json` |
| criterion coverage | 100% required | `17/17` |
