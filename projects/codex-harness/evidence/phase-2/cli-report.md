# CLI report

Comandos verificados:

- `validate .harness/config/kernel.json --format json` → `PASS`;
- `doctor` e `health` → `PASS`, `capabilities_executed=false`;
- `quality` → metadata-only, `provider_execution=NOT_RUN`;
- `run --dry-run --json` → `DRY_RUN`, `executed=false`;
- `run --explain --json` → plano de classification/route/provider/authority/
  budgets sem execução;
- `run --json` → provider `local.success`, artifact/evidence/summary persistidos;
- `run --provider missing.provider --json` → exit 1 e
  `CAPABILITY_UNAVAILABLE`/`PROVIDER_UNAVAILABLE`;
- paths, IDs, JSON depth/size, duplicate keys e config sandbox são validados.

A CLI cria uma autoridade explícita e limitada para a execução local, só
instancia `ProviderRegistry.local_defaults`, grava sob `.harness/` e
nunca importa ou executa módulos fornecidos na entrada. Flags não ampliam
timeout acima da configuração, não habilitam shell/rede e não removem
verification/authority/boundary.

Regressão pré-review: `tests/integration/test_phase2_cli.py`,
`tests/integration/test_cli.py` e `tests/unit/test_cli_in_process.py` —
`45 passed` em `24,29s`. A execução manual de `doctor --json`, `quality --json`,
`run --dry-run --json` e `run --explain --json` também foi observada; dry-run e
explain produziram `executed=false` e não chamaram provider. Doctor, quality,
success, unknown provider, root boundary e manifest admission permanecem
cobertos.
