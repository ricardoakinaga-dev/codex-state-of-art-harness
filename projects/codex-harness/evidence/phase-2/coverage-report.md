# Coverage report

Comando:

```text
PYTHONPATH=src .venv/bin/coverage erase
PYTHONPATH=src .venv/bin/coverage run -m pytest -q
PYTHONPATH=src .venv/bin/coverage report --fail-under=80
```

O quality bar exige cobertura total mínima de 80% incluindo Fase 1, Fase 2 e
integração CLI. A porcentagem e a contagem exatas abaixo são atualizadas após
a execução final limpa, para não congelar um número de uma rodada intermediária.
