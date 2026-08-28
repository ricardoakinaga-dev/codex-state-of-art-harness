# ADR P2-002 — Graph bounded e execução sequencial

## Decisão

O graph é criado somente quando a coordenação tem benefício demonstrável ou é
explicitamente solicitado. A primeira implementação executa nodes
sequencialmente em ordem topológica determinística. Edges, `depends_on`, owners,
acceptance, merge policy, conflict policy e budgets são validados antes do
primeiro node. Falha de dependência bloqueia descendentes e preserva partials.

## Consequências

Não há fan-out concorrente nem corrida de merge nesta fase. A política é menos
ambiciosa, mas torna timeout, cancellation, replay e evidence causalmente
inspecionáveis.
