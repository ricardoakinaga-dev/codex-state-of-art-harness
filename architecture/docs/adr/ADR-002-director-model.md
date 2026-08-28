# ADR-002 — Domain Director como dono de estratégia

**Status:** `PROPOSED` · **Data:** 2026-08-28 · **Escopo:** capability composition

## Contexto

A execução especializada precisa de uma decisão de escopo, acceptance e composição; specialists e tools não devem redefinir o objetivo no meio do run. O `design-director` existente oferece um modelo visual forte, mas não prova um Director universal.

## Decisão

Um Director é uma capability opcional, ativada apenas quando o domínio e a complexidade justificarem. Ele interpreta brief, define quality profile, cria handoffs/graph e mantém acceptance. Não executa indiscriminadamente, não owns toda a tarefa e não autoriza sozinho release.

## Alternativas consideradas

- Sempre usar Director: over-orchestration e latência em tarefas simples.
- Deixar cada specialist decidir produto: conflito de boundary e acceptance inconsistente.
- Usar o modelo visual como universal: generalização não comprovada.

## Consequências

Complexidade fica concentrada em tarefas que precisam de coordenação; rotas diretas continuam possíveis. Cada Director deve provar valor por eval antes de promoção.

## Evidência

`docs/08-director-model.md`, `docs/28-domain-directors.md`, `docs/30-design-director-integration.md` e a auditoria independente do pacote `design-director`.

## Revalidação

Medir activation precision, quality delta, context cost e latency por task family; despromover se o Director não produzir ganho causal.
