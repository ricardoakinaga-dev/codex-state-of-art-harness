# Lint and format report

Comandos:

```text
PYTHONPATH=src .venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/ruff check src tests
```

Resultado da rodada final: ambos devem permanecer `PASS` sobre a fonte atual;
o relatório é regenerado junto do `final-readiness.md`.
