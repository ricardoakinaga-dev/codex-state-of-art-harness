# Phase 1 test report

**Data:** 2026-08-28 12:10 BRT
**Escopo:** `projects/codex-harness`

## Resultado

```text
$ .venv/bin/pytest -q
99 passed
```

Gates direcionados observados:

```text
$ .venv/bin/pytest -q tests/unit/test_contracts.py tests/unit/test_validation.py
16 passed

$ .venv/bin/pytest -q tests/unit/test_registry.py tests/unit/test_routing.py tests/unit/test_authority.py
26 passed

$ .venv/bin/pytest -q tests/unit/test_state.py tests/unit/test_stops.py tests/unit/test_telemetry.py
10 passed

$ .venv/bin/pytest -q tests/integration/test_cli.py tests/integration/test_benchmarks.py tests/integration/test_golden_scenarios.py
32 passed
```

A suíte inclui unitários para os contratos, validação, registry, classificação,
authority, evidência, artifacts, estado, stops e telemetria; integração para
CLI, microbenchmarks e os cinco cenários golden S1–S5; além de fixtures
negative e regressões de isolamento, proveniência, limites de entrada e
ausência de execução.
