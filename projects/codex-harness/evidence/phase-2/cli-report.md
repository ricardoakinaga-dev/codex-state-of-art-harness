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

A CLI só instancia `ProviderRegistry.local_defaults`, grava sob `.harness/` e
nunca importa ou executa módulos fornecidos na entrada. Flags não ampliam
timeout acima da configuração, não habilitam shell/rede e não removem
verification/authority/boundary.
