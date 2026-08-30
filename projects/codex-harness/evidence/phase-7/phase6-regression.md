# Phase 6 regression

Command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/pytest -q -p no:cacheprovider tests/unit/test_phase6_*.py tests/evals/phase6 tests/integration/test_phase6_*.py
```

Observed against the current worktree on 2026-08-30:

Result: `81 passed in 13.45s`. The Phase 6 frozen packet remains unchanged.
