# Branch risk map

O inventário definitivo é `branch-inventory.json`, gerado diretamente de
`coverage-final.json` sem exclusões. Ele analisa 65 arquivos; 61 deles têm
branches ausentes. No total são 7.408 branches, 6.031 cobertos e 1.377
ausentes.

| Classificação | Ausentes | Tratamento |
| --- | ---: | --- |
| `CRITICAL_PATH` | 0 | Fechados por teste ou reclassificados após inspeção do ramo |
| `HIGH_VALUE_FAILURE_PATH` | 509 | Revisados contra a matriz; resíduos são guards compostos, plataforma/host ou falhas defensivas não necessárias ao piloto |
| `MEDIUM_VALUE_BRANCH` | 203 | Validação/parser/defesa residual, sem exclusão ampla |
| `LOW_VALUE_DEFENSIVE_BRANCH` | 665 | Defesa de baixo risco, mantida no inventário para próximo ciclo |

Prioridade material verificada:

- transação, rollback, constraints, concorrência e idempotência: piloto real
  e suítes de persistência/Phase 4;
- migração e recuperação: piloto real com falha injetada, checksum, trigger e
  inicialização concorrente;
- autorização e handoff: suítes core/Phase 4–6 e verifier real read-only;
- timeout, cancelamento, retry, partial e dependência ausente: suítes Phase 4–7;
- staleness, substituição, escopo, no-progress e separação de revisão:
  catálogo determinístico Phase 7 e suítes de identidade.

Nenhum ramo foi marcado `UNREACHABLE_BY_CONTRACT`, `DEAD_CODE`,
`PLATFORM_SPECIFIC` ou `EXCLUDED_WITH_REASON` no inventário. A classificação é
regra + revisão do lead; o inventário permanece completo para os resíduos e
não usa `# pragma: no cover`, configuração de ignore ampla ou remoção de
branches para elevar o número.
