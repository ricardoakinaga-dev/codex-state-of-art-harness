# Execution contract report

O walking skeleton da Fase 2 está implementado em
`src/harness_kernel/execution.py`. A ordem executável é:

`classify → route → validate invocation/graph → authority → exact provider resolve → execute → artifact → verification → critique → assurance → summary/persistence`.

Authority é fornecida pelo caller ou pelo adapter explícito; o executor não
cria uma autorização implícita. A ausência de grant é um deny tipado e ocorre
antes de provider resolution, inclusive em dry-run e graph execution.

`CapabilityInvocation` carrega task/run/invocation identity, capability,
provider, operation, origin, scope, dependencies, permissions, budgets,
acceptance refs, trace context, authority snapshot e repair provenance.
Transições ilegais são rejeitadas por `transition_invocation`.

Os terminais de primeira classe são `SUCCEEDED`, `FAILED`, `PARTIAL`,
`BLOCKED`, `CANCELLED`, `TIMED_OUT`, `STOPPED` e `DRY_RUN`. Um provider
indisponível ou incompatível gera `CAPABILITY_UNAVAILABLE`/`PROVIDER_UNAVAILABLE`;
nenhum provider alternativo é escolhido implicitamente.

Limites aplicados: nodes, invocations, retries, duração, timeout, evidence,
telemetry e repairs. Stop-before, cancellation antes/durante provider,
timeout reportado pelo fixture ou pela duração observada e budget exhaustion
não são convertidos em sucesso. Duração observada usa o tempo reportado pelo
provider quando disponível e, caso contrário, o relógio monotônico local;
eventos sem medição não recebem duração fabricada. `RunSummary` preserva `passed`, `failed`,
`not_run`, `unknown`, blocked gates, delivery e limitations.

Artefatos têm digest SHA-256, locator project-relative e conteúdo gravado sob
`.harness/state/runs/<run_id>/`; evidence, lifecycle, summary e telemetry são
gravados em áreas project-local com writes atômicos. Replay idêntico é
idempotente; colisão ou corrupção não sobrescreve dados.

Verificação independente da execução: `ProviderExecutionResult` nunca contém
decisão de assurance. Somente evidence fresca, artifact digest e critique
podem produzir `QUALITY_ACCEPTED`.
