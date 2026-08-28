# State machine report

## Invocation

O caminho normal é `CREATED → VALIDATED → AUTHORIZED → READY → RUNNING →
SUCCEEDED|PARTIAL|FAILED|BLOCKED|CANCELLED|TIMED_OUT`. Dry-run e stop-before
usam terminais truthful sem marcar provider como executado. Um salto direto de
`CREATED` para `SUCCEEDED` levanta `InvocationStateError`.

## Graph

O scheduler usa ordem topológica estável, bloqueia dependentes de falhas,
preserva nodes independentes e retorna estados sintéticos para cancelamento,
timeout e budgets que impedem chamada. O graph atualizado contém status,
invocation refs e artifact refs de cada node.

## Stops e repair

`StopBudget` é avaliado antes e depois do trabalho. Repair exige ação
`REPLAN`, escopo explícito e budget `max_repairs`; cada tentativa recebe uma
invocation própria, `repair_of`, trigger refs e `RepairRecord`. Exhaustion
termina sem fallback oculto.

## Evidência executada

Os testes cobrem transições ilegais, direct/graph success, dependency block,
timeout, cancellation, stop-before, retries bounded, partial, repair success,
repair exhaustion e preservação de estados não executados.
