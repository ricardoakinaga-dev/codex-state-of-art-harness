# Coverage and quality tools

The complete project suite passed `424` tests under branch coverage. Combined
coverage is exactly `80%` (`13,877` statements and `4,904` branches, with the
project gate set to `80`). The Phase 5 addition contains 55 tests: 49 unit,
3 integration, and 3 adversarial/eval tests.

The required quality commands passed:

- Ruff format check: `PASS`
- Ruff lint check: `PASS`
- strict mypy on `src`: `PASS`
- Phase 5 negative evals: `PASS`
- final structural/browser evidence checks: `PASS` (artifact-v2; distinct
  post-critique final-verification record)

The historical Phase 2, Phase 3, and Phase 4 packets remain available as
regression authorities. The exact command outputs and final rerun are recorded
in the append-only verification ledger and the phase-specific regression
reports in this directory.
