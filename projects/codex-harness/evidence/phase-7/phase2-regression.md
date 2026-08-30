# Phase 2 regression

Command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/pytest -q -p no:cacheprovider tests/unit/test_phase2_*.py tests/integration/test_phase2_*.py
```

Observed against the current worktree on 2026-08-30:

Result: `112 passed in 18.60s`. The Phase 2 frozen packet remains unchanged.
