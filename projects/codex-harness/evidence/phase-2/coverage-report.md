# Coverage report

Comando:

```text
PYTHONPATH=src .venv/bin/coverage erase
PYTHONPATH=src .venv/bin/coverage run -m pytest -q
PYTHONPATH=src .venv/bin/coverage report --fail-under=80
```

Resultado da rodada limpa: `187 passed`; total de 7.771 statements,
1.268 missed e cobertura total de `84%`. O quality bar exige cobertura total
mínima de 80% incluindo Fase 1, Fase 2 e integração CLI; o limite foi
atingido.
