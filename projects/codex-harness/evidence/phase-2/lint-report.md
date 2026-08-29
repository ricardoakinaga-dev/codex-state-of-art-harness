# Lint and format report

Comandos:

```text
PYTHONPATH=src .venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/ruff check src tests
```

Resultado da rodada final: `ruff format --check src tests` → `PASS` (45 files
already formatted); `ruff check src tests` → `PASS`.
