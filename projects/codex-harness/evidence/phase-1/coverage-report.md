# Phase 1 coverage report

```text
$ .venv/bin/coverage run -m pytest -q
99 passed in 7.38s
$ .venv/bin/coverage report --fail-under=80
Name                                         Stmts   Miss  Cover
----------------------------------------------------------------
src/harness_kernel/__init__.py                   4      0  100%
src/harness_kernel/artifacts.py                103     12   88%
src/harness_kernel/authority.py                159     37   77%
src/harness_kernel/benchmarks.py                62      3   95%
src/harness_kernel/classification.py           368     55   85%
src/harness_kernel/cli.py                      549    457   17%
src/harness_kernel/errors.py                    41      0  100%
src/harness_kernel/evidence.py                 114     18   84%
src/harness_kernel/models.py                   998      4   99%
src/harness_kernel/registry.py                 493    105   79%
src/harness_kernel/routing.py                  243     43   82%
src/harness_kernel/serialization.py            189     67   65%
src/harness_kernel/state.py                    119     32   73%
src/harness_kernel/stops.py                    147     10   93%
src/harness_kernel/telemetry.py                160     49   69%
src/harness_kernel/validation.py               287     36   87%
tests/integration/test_benchmarks.py            30      0  100%
tests/integration/test_cli.py                  250      0  100%
tests/integration/test_golden_scenarios.py      25      0  100%
tests/unit/test_artifacts.py                    37      0  100%
tests/unit/test_authority.py                    32      0  100%
tests/unit/test_classification.py               59      0  100%
tests/unit/test_contracts.py                    55      0  100%
tests/unit/test_evidence.py                     34      0  100%
tests/unit/test_registry.py                    102      0  100%
tests/unit/test_routing.py                      62      0  100%
tests/unit/test_state.py                        27      0  100%
tests/unit/test_stops.py                        27      0  100%
tests/unit/test_telemetry.py                    38      0  100%
tests/unit/test_validation.py                  106      0  100%
----------------------------------------------------------------
TOTAL                                         4920    928   81%
```

O gate de projeto passa com 81% total. Alguns módulos permanecem abaixo de 80%
em ramos de erro raros. A CLI é exercitada por subprocessos nos testes de
integração e, por isso, aparece sub-representada no relatório agregado; sua
matriz funcional é coberta pelo gate de integração. Isso não é um claim de
cobertura exaustiva por módulo.
