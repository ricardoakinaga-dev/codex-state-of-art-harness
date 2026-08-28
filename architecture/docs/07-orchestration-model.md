# 07 — Orchestration Model

## Tese

“Grande” não é sinônimo de “orquestrar”. Orchestration só é aplicada quando existe delegação concreta, lanes independentes, isolamento de ownership, ganho de latência/qualidade ou uma necessidade de crítica separada que o caminho direto não fornece. Caso contrário, um agente único com plan/verification é a rota correta.

## Delegation gate

`orchestrate=YES` exige todos:

- objetivo local de cada lane é independente e julgável;
- dependências e contratos compartilhados estão congelados;
- não há dois writers no mesmo arquivo, schema, lockfile, banco, porta ou recurso externo;
- cada lane tem procedimento de validação e output esperado;
- custo de contexto/coordenacão é menor que o benefício esperado, ou a independência acrescenta assurance material;
- o Lead consegue inspecionar e integrar todos os resultados;
- permissions, secrets e autoridade são herdados sem expansão.

Se uma condição falhar, marcar `orchestration: NO` ou `BLOCKED` e seguir serialmente quando seguro.

## Execution graph

O graph é um DAG de tasks, não uma lista de prompts. Cada node contém:

```yaml
task:
  id: T20
  objective: one observable local outcome
  owner: specialist/backend
  depends_on: [T10]
  inputs: [contract/api-v1]
  owns: [backend/**]
  forbidden: [frontend/**, shared-types]
  output: [artifact/API-implementation, evidence/report]
  validation: [integration-test/API-001]
  retry_budget: 1
  cancellation: safe
```

## Padrões de execução

| Padrão | Quando usar | Controle |
| --- | --- | --- |
| serial chain | dependência forte, shared file, migration, auth | um owner por passo |
| fan-out | lanes independentes com contrato estável | limite de concorrência e budget |
| fan-in | integrator precisa combinar outputs | validação de conflito e provenance |
| speculative branch | investigar alternativas reversíveis | sem external side effects; comparar evidence |
| independent review | critic não deve receber rationale do builder | read-only, fresh context |

## Ownership

Ownership inclui arquivos, diretórios, schemas, generated outputs, fixtures, bancos, queues, ports, providers e ledgers. Um worker não pode editar recurso compartilhado durante lane concorrente. Shared contract tem owner único (normalmente Lead/Integrator); mudanças invalidam dependentes e reabrem revisão.

## Merge e integração

O Integrator:

1. inspeciona cada artifact/diff, não apenas resumo;
2. confirma escopo e ownership;
3. alinha nomes, schemas, status, errors e state;
4. preserva divergências e provenance;
5. roda checks de cada lane e integração;
6. encaminha gaps para rework bounded;
7. entrega candidate ao Verification e Reviewer.

Não existe “merge” que converta outputs conflitantes em verdade. Conflito não resolvido é `BLOCKED`/`PARTIAL`.

## Retries

- Transporte idempotente: retry com backoff/jitter e limite declarado.
- Reasoning/task: retry apenas após hipótese diferente ou evidence nova.
- Tool não idempotente: não repetir sem estado externo confirmado.
- Validation failure: corrigir root cause, não aumentar tentativas cegamente.
- Critic disagreement: preservar ambos; pedir re-review com packet claro, não votar por maioria sem evidence.

Cada retry registra `attempt`, causa, mudança de hipótese, custo e resultado. Dois retries sem progresso material acionam `NO_PROGRESS`/replan.

## Cancelamento

Cancelamento deve ser cooperativo e seguro: não iniciar nova operação externa, fechar processos/locks, preservar artifacts parciais e emitir `CANCELLED`/`BLOCKED`. Uma task cancelada não pode ser reportada como `DONE`.

## Partial failure

O graph deve permitir continuar lanes não dependentes, mas integrator lista dependentes bloqueadas. Um output parcial recebe escopo explícito e não satisfaz acceptance global sem compensating evidence.

## Budget

Cada graph declara orçamento de:

- turns/calls por task;
- tokens/contexto por lane;
- tempo/latência;
- tool/provider calls;
- tentativas de repair;
- custo financeiro quando aplicável.

Quando budget acaba, o estado é `BUDGET_EXHAUSTION`, não `PASS`. O Lead pode entregar escopo parcial se autorizado e com limitations.

## Orchestration status ledger

Use a sequência:

```text
PENDING → READY → RUNNING → IMPLEMENTED → REVIEW → VERIFIED → DONE
                         ↘ BLOCKED / FAILED
REVIEW → REWORK → RUNNING
BLOCKED → READY (só após dependência mudar)
```

`IMPLEMENTED` significa artifact + evidence mínima do worker; só review/verification pode levar a `DONE`.

## Single-agent degradation

Quando subagents não existem ou são proibidos, o Lead mantém o mesmo graph lógico e executa lanes serialmente ou usa `SEPARATED_SELF` review. Deve registrar ausência de independência física; não atribuir benefício de paralelismo nem chamar self-review de independent.

## Métrica de benefício

Antes de orquestrar, registrar hipótese: “fan-out de A/B/C reduz tempo de wall-clock em X” ou “critic separado aumenta detecção de gaps em Y”. Após a execução, comparar com baseline equivalente. Se não houve ganho, reclassificar o padrão e não preservá-lo por hábito.
