# Phase 1 schema and contract validation

Os 12 records conceituais têm model dataclass frozen, `schema_version`,
envelope comum, serialização JSON e validação estrutural/invariante.

```text
$ .venv/bin/pytest -q tests/unit/test_contracts.py tests/unit/test_validation.py
16 passed in 0.46s
```

Cobertura negativa inclui versão inválida, enum inválido, IDs/referências,
evidence ausente, ciclo de graph, autorização sem scope/budget, sucesso sem
evidence, freshness, review independente sem blind packet e status
incompatível.

Os cenários golden S1–S5 cobrem edição local trivial, endpoint autenticado,
landing page visual, ajuste CSS estreito e refactor de auth multi-service; os
oráculos preservam fallback/conditional quando não existe capability registrada.

O deserializador rejeita chaves duplicadas, constantes não-finito, JSON acima
de 4 MiB, raízes não-objeto para contracts e tipos que não sejam dataclass
contract; não usa `eval`, import dinâmico ou execução de payload.
