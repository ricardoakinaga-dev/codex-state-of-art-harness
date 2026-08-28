# Phase 1 state and stop validation

```text
$ .venv/bin/pytest -q tests/unit/test_state.py tests/unit/test_stops.py tests/unit/test_telemetry.py
10 passed in 0.21s
```

O state machine rejeita transições inválidas e mantém lifecycle, task, gate,
verification, freshness e delivery como dimensões separadas. O stop engine
cobre no-progress, repeated failure, oscillation, budget, dependency,
authority, safety, invalid evidence e completion.

O arquivo `.harness/config/kernel.json` mantém limites locais para iterações,
falhas, paralelismo, contexto e telemetria; nenhuma política cria loop de
execução nesta fase.

O ledger de controle também foi validado pelo checker canônico:

```text
$ python3 engineering-framework/scripts/check_state.py .
RESULT PASS (pass=10 warn=0 fail=0)
```
