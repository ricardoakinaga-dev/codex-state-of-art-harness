# Phase 4 regression

Command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/pytest -q -p no:cacheprovider tests/unit/test_phase4_*.py tests/evals/phase4 tests/integration/test_phase4_*.py
```

Observed against the current worktree on 2026-08-30:

Result: `67 passed in 7.11s`. The Phase 4 frozen packet remains unchanged; the
Phase 7 change to the Phase 4 preflight policy is covered by the current Phase
4 unit suite.
