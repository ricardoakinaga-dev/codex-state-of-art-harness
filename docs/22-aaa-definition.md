# 22 — AAA Definition

## O que AAA significa

AAA é uma designação de qualidade operacional para uma tarefa e seu perfil, nunca uma propriedade abstrata de uma Skill. Significa high quality, reliability adequada, specialization, tool use correto, strong verification, bounded assurance, evidence confidence e output polido/específico, sem finding crítico.

## Estados

| Estado | Critério | Pode ser entregue como AAA? |
| --- | --- | --- |
| `AAA_CANDIDATE` | Quality Bar definida, artifact candidate e evidence parcial; ainda aguardando gates/critic | não; apenas hipótese |
| `AAA_VERIFIED` | required criteria PASS, evidence current, no Critical/unaccepted High, reviewer/assurance proporcional, residual risk autorizado | sim, somente no scope observado |
| `NOT_AAA` | resultado útil pode existir, mas um required gate falha ou output genérico/insuficiente | não |
| `BLOCKED` | evidence/tool/authority/dependency missing impede conclusão | não; não atribuir score compensatório |

## Gate `AAA_VERIFIED`

Todos os seguintes devem ser verdade:

1. scope e quality profile estão fechados;
2. correctness e acceptance têm evidence current;
3. security/data/authorization gates expostos passaram;
4. artifact funciona na boundary relevante;
5. verification lista claims, procedures, passed, failed, not-run e unknown;
6. domain specialist/reviewer foi usado quando aplicável;
7. assurance/critic independente foi usado quando exigido, com independence real;
8. ferramenta/provider correto foi usado ou fallback foi aprovado com limitation;
9. loops pararam por success/acceptable residual risk, não só budget;
10. provenance e traceability estão completos;
11. não há generic AI slop, fake claims, placeholders escondidos ou output sem product specificity quando isso é parte do profile;
12. o residual risk está dentro do authority decision.

## “High quality” sem marketing

“High quality” só pode ser usado acompanhado de profile, criterion, artifact, observation, confidence e limitations. Não existe threshold universal AAA; cada domain profile define gates e anchors. `90/100` sem evidence não é AAA.

## Critical blockers

Qualquer security/data/correctness/authorization failure, fake claim, identity violation, missing required artifact, unsupported production-ready claim, self-approval material ou evidence impossível bloqueia AAA. A nomenclatura fica `NOT_AAA` ou `BLOCKED`.

## Overrides

User/human authority pode aceitar trade-off e entregar, mas o record precisa de scope, reason, affected criteria, residual risk, compensating controls, due/revalidation e actor. O resultado permanece “accepted below AAA” se o gate não passou.
