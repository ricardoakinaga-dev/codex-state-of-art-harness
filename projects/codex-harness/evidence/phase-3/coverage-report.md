# Coverage and verification report

The verification command is:

```text
PYTHONPATH=src .venv/bin/coverage run --branch -m pytest -q -p no:cacheprovider
PYTHONPATH=src .venv/bin/coverage report -m
PYTHONPATH=src .venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/ruff check src tests
PYTHONPATH=src .venv/bin/mypy src
```

Latest measured result: 308 tests passed in 84.20 seconds; 8,972 statements,
1,304 missed statements, 2,984 branches, 715 partial branches and 82% combined
coverage. The project gate remains at least 80%. Unit, integration,
adversarial, eval, golden, real-host, security/privacy, stale-fingerprint,
path-safety and bounded-performance checks are included; the frozen Phase 2
regression is run as part of the full suite.
