# Coverage and quality report

## Harness

Command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/coverage run -m pytest -q -p no:cacheprovider
.venv/bin/coverage report -m
```

Result: `534 passed`; `18,503` statements, `3,529` missed, `81%` line
coverage. The required combined Harness floor is 80%. A separate branch-mode
diagnostic measured 77%; it is reported as diagnostic and is not substituted
for the configured line-coverage gate.

Static checks:

- `.venv/bin/ruff check src tests`: PASS
- `.venv/bin/mypy --strict src`: PASS, 65 source files
- `git diff --check`: PASS

## Pilot

Target: 90% line coverage, chosen as a rational floor for the small fixture.
Result: `20 passed`; `845` statements, `77` missed, `91%` line coverage.

Pilot checks:

- `../../.venv/bin/ruff format --check app tests`: PASS
- `../../.venv/bin/ruff check app tests`: PASS
- `../../.venv/bin/mypy --strict app`: PASS, 8 source files
- five repeated concurrent-test runs: each `2 passed, 12 deselected`
- real CLI subprocess smoke: PASS, clean SIGINT return

Coverage is not treated as proof of architecture, security, migration safety,
or production readiness; those claims are supported by the separate evidence
records.
