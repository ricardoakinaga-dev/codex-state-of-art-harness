# Phase 7.3 Static Security Report

Result: `PASS_WITH_LIMITATIONS`.

Fresh deterministic controls:

    $ .venv/bin/ruff check src tests scripts
    All checks passed!

    $ .venv/bin/ruff format --check src tests scripts
    218 files already formatted

    $ .venv/bin/mypy --strict src
    Success: no issues found in 65 source files

The bounded secret-pattern scan covered `src`, `scripts`, `tests`, `pilots`,
`.harness`, `config` and `pyproject.toml`, excluding historical evidence
content. It found no private-key/API-key/token pattern and no `.env` or
private-key filename. No secret content was persisted.

The complete fresh suite passed `1758` tests with branch-aware coverage; the
result is recorded in `test-report.json` and `coverage-final.json`.

These are the available local controls only. They are not a substitute for
the unavailable third-party scanner results, which remain `UNAVAILABLE` and
are governed by the formal scanner waiver. This report does not grant
security approval.
