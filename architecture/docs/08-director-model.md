# 08 — Director Model

## Definição

Um Domain Director é o responsável por transformar um objetivo em uma estratégia de domínio verificável. Ele é uma função de decisão e coordenação; pode ser uma Skill, módulo ou papel lógico, mas o nome “Director” não implica subagente físico.

## Responsabilidades

- entender objetivo, usuário, contexto e constraints;
- separar problem, requirement, assumption, hypothesis e unknown;
- decidir strategy e depth adequadas;
- definir Quality Bar e acceptance criteria;
- criar task graph quando necessário;
- selecionar capabilities e tool boundary;
- resolver ambiguidades de domínio dentro da autoridade;
- coordenar integração e preservar product truth;
- definir failure modes, recovery e stop conditions;
- escolher quais evidências comprovam cada claim;
- entregar handoff completo ao Orchestrator/Specialist/Verification.

## Não responsabilidades

- implementar toda a solução;
- chamar agents sem delegation gate;
- substituir specialist expertise;
- produzir evidência de um trabalho que não observou;
- aprovar seu próprio artifact material;
- reescrever user intent ou safety policy;
- aceitar residual high/critical risk sem autoridade;
- manter loop indefinidamente;
- converter uma proposta arquitetural em fato atual.

## Director brief/output

```yaml
director_decision:
  director_id: engineering-director
  goal: "..."
  product_truth: ["...preserve..." ]
  scope: ["..." ]
  non_goals: ["..." ]
  strategy: "..."
  quality_bar_ref: QUALITY-0001
  task_graph_ref: GRAPH-0001
  selected_capabilities: ["..."]
  excluded_capabilities: [{name: "...", reason: "..."}]
  acceptance_refs: ["..." ]
  risks: ["..." ]
  unknowns: ["..." ]
  escalation: []
  confidence: MEDIUM
  status: PROPOSED
```

## Quando ativar

Ativar para cross-domain, arquitetura, multi-milestone, high-risk, high-fidelity, requirement ambiguity material ou pedido explícito de direção. Para typo, lookup único, check local e mudança reversível, o router deve preferir caminho direto.

## Director único por decisão

Pode haver um `engineering-director` e um `design-director` na mesma tarefa, mas cada um precisa de boundary. Um Director de produto/integração resolve conflitos entre outputs; não se devem criar Directors concorrentes para a mesma acceptance sem owner de integração.

## Quality bar ownership

Director define o que seria sucesso e como medir. Verification executa os procedimentos. Reviewer desafia o resultado. Assurance decide se os gaps/risco permitem parar. Essa separação evita que “o autor da meta” também declare sua prova.

## Ambiguity handling

O Director pode assumir somente o que é low-risk, reversível e explicitamente marcado `ASSUMPTION`. Se a decisão muda produto, segurança, dados, custo material ou arquitetura, deve pedir autoridade ou manter `BLOCKED`. A palavra “premium”, “production-ready” ou “AAA” deve ser traduzida em critérios observáveis.

## Director como composição

```text
engineering-director
 ├─ classification + acceptance
 ├─ backend/api/security specialists (quando boundaries aparecem)
 ├─ orchestrator? (graph gate)
 ├─ integrator
 └─ verification → domain review → assurance
```

Design Director conserva o mesmo formato de direção, mas owns visual thesis, medium, assets, viewport/state matrix e visual QA; não assume backend ou data. Ver [`30-design-director-integration.md`](./30-design-director-integration.md).
