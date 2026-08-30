# Phase 3 regression

Command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/pytest -q -p no:cacheprovider tests/unit/test_phase3_*.py tests/evals/phase3 tests/integration/test_phase3_*.py
```

Observed against the current worktree on 2026-08-30:

Result: `84 passed in 13.01s`. The Phase 3 frozen packet remains unchanged.
