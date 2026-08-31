# Test Report

- Full suite: `.venv/bin/pytest -q` — `1781 passed in 151.15s`.
- Full branch-coverage run: `.venv/bin/coverage run --branch -m pytest -q` — `1781 passed in 199.04s`.
- Phase 8.1 focused contracts after the concurrent stale-request repair: `9 passed`.
- Type checking: `mypy src` — PASS.
- Static lint: `ruff check src tests scripts` — PASS.

The browser captures are an additional bounded runtime check and are not substituted by the structural suite.
