# Coverage report

Comando reproduzível:

```text
.venv/bin/coverage erase
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/coverage run --branch -m pytest -q -p no:cacheprovider
.venv/bin/coverage json -o evidence/phase-7.1/coverage-final.json
```

Observado em 2026-08-30 com Python 3.12.3, pytest 8.4.2 e coverage 7.15.4:

- testes: 1.283 passados;
- linhas: 17.333/19.447, 89,1294%;
- branches: 6.031/7.408, 81,4120%;
- branches ausentes: 1.377; parciais: 1.233.

O JSON bruto contém a cobertura por arquivo e os arcos ausentes. O inventário
foi regenerado desse JSON após a última alteração de teste; nenhum ignore
amplo foi adicionado. O hardening isolado coleta 720 testes.
