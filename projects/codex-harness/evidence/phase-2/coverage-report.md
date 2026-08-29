# Coverage report

Comando:

```text
PYTHONPATH=src .venv/bin/coverage erase
PYTHONPATH=src .venv/bin/coverage run -m pytest -q
PYTHONPATH=src .venv/bin/coverage report --fail-under=80
```

Regressão pré-review limpa capturada em `2026-08-28`, com `232 passed` em
`49,19s` de pytest; total de `6.591` statements, `969` missed e cobertura
total de `85%`. O quality bar
exige cobertura total mínima de 80% incluindo Fase 1, Fase 2 e integração CLI;
o limite foi atingido.
