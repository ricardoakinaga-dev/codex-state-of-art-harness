# Current Phase 2–6 regression packet

The five phase-specific suites were rerun against the current worktree on
2026-08-30. The frozen packets remain historical authorities; this packet only
records current regression observations.

| Phase | Current result | Frozen packet status |
| --- | --- | --- |
| 2 | `112 passed in 18.60s` | preserved |
| 3 | `84 passed in 13.01s` | preserved |
| 4 | `67 passed in 7.11s` | preserved; current preflight policy tests included |
| 5 | `55 passed in 8.56s` | preserved |
| 6 | `81 passed in 13.45s` | preserved |

The combined Harness run is recorded separately in `harness-quality-run.json`:
`549 passed`, 81% line coverage, Ruff PASS and strict mypy PASS.
