# 36 — Anti-patterns

## Catálogo de rejeição

| Anti-pattern | Sinal | Dano | Controle |
| --- | --- | --- | --- |
| `SKILL SOUP` | dezenas de Skills sem owner/route | contexto caro, instructions collision | minimum route + do-not list |
| `OVER-ORCHESTRATION` | fan-out sem lanes independentes | latency, merge risk, token waste | delegation gate |
| `REVIEW LOOP HELL` | review/gauntlet repetidos sem progress | custo infinito, indecisão | stop conditions + largest-gap |
| `CONTEXT FLOODING` | carregar todas references/logs | context rot, misses | progressive disclosure/budget |
| `PROMPT BLOAT` | SKILL.md vira manual inteiro | trigger ruim, manutenção | kernel + references split |
| `EVERYTHING-AS-DIRECTOR` | cada capability decide produto/qualidade global | authority collision | primary type + scope |
| `SELF-APPROVAL` | builder assina o próprio PASS | false confidence | fresh reviewer/verification |
| `TOOL AVOIDANCE` | reasoning substitui browser/test/parser | claims não observáveis | deliberate tool rule |
| `PREMATURE DONE` | “done” antes de boundary/evidence | bugs e gaps ocultos | required gates + freshness |
| `AAA LABEL WITHOUT EVIDENCE` | AAA usado como marketing | falsa segurança | AAA gate/limitation |
| `GENERIC AI OUTPUT` | resultado intercambiável | baixa utilidade/specificity | domain content + rubric |
| `PORTABILITY COPY-PASTE` | Claude/Cursor paths tratados como Codex | execução quebrada | adapter/UNKNOWN + native-first |
| `ONE-SIZE-FITS-ALL` | mesmo processo para typo e migration | custo/risco mal calibrados | adaptive depth |
| `PROVIDER COMPETITION` | todos providers chamados | custo e conflicting facts | one-provider hypothesis |
| `LEXICAL ROUTING` | ativar por palavra “API/design/security” | false positive | boundary + deliverable classifier |
| `DUPLICATE AUTHORITY` | duas cópias/owners sem precedence | shadowing/drift | canonical registry/hash check |
| `SCORE AVERAGING` | score alto compensa security fail | gate bypass | mandatory gates separate |
| `KNOWN-UNKNOWN ERASURE` | unavailable vira successful fallback | claim scope falsificado | explicit degradation |
| `EVIDENCE THEATER` | logs/metrics sem public boundary | proxy enganoso | measurement validity |
| `BENCHMARK GAMING` | threshold/dataset muda após falha | false improvement | freeze control/known-bad |
| `ORPHAN ARTIFACT` | output sem producer/source/evidence | não auditável | ArtifactRecord/provenance |
| `DAG DECORATION` | graph sem dependencies/ownership | parallel conflicts | executable task graph |
| `STATE COLLAPSE` | task/gate/verification no mesmo status | transitions ambíguas | separate vocabularies |
| `DIRECTOR MONOPOLY` | Director implementa/revisa/aprova tudo | bottleneck/self-review | role boundaries |
| `CRITIC BIAS` | critic recebe rationale/score esperado | confirmation bias | blind packet |
| `UNBOUNDED RETRY` | retry igual esperando sorte | token runaway | hypothesis/progress budget |
| `TOOL NAME FICTION` | reference diz tool disponível sem preflight | runtime failure | observed availability |
| `RUNTIME LEAKAGE` | docs proposta descrita como installed | decisões falsas | CURRENT/PROPOSED labels |
| `FAKE PROVENANCE` | owner/fork assume autoria/licença | legal/reputation risk | source/status/confidence |

## Teste de diagnóstico

Para cada anti-pattern, o eval precisa de um known-bad scenario que o revele. Uma lista textual sem detector, critério ou finding não é quality gate.

## Reparação

Corrija primeiro truth, authority, scope, boundary, evidence e state; depois custo/ergonomia; por último polish. Não adicione uma nova Skill para mascarar uma responsibility boundary mal definida.
