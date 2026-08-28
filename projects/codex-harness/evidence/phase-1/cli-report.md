# Phase 1 CLI report

Smoke tests e integração passaram dentro do projeto isolado:

```text
$ PYTHONPATH=src .venv/bin/python -m harness_kernel --help
PASS — surface contains validate, doctor, health, registry, profile, route,
state and telemetry; no run command.

$ PYTHONPATH=src .venv/bin/python -m harness_kernel doctor
status=PASS; capabilities_executed=false; CAPABILITY_EXECUTION=NOT_RUN

$ PYTHONPATH=src .venv/bin/python -m harness_kernel registry list
status=PASS; valid=true; count=1
```

Além dos smoke tests acima, a integração verifica root/path boundaries,
configuração de diretórios do registry, divergência entre manifestos, hashes e
ownership de projeto, limites de registry/objetivo/telemetria, identificadores
inválidos e ausência de import/execução de capabilities. O conjunto combinado
CLI + benchmarks + golden registra 32 testes. A CLI é read-only,
project-local e não inicia executor, provider dispatch ou loop de agentes.
