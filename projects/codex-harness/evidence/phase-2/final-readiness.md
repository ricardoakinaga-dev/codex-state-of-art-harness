# Final readiness

Este arquivo é o checklist de handoff da Fase 2. Ele deve ser lido junto de
`readiness.json` e `final-report.md`.

- [ ] fonte, testes e evidências apontam para o mesmo estado do worktree;
- [ ] testes, coverage, ruff, mypy e CLI foram executados após a última edição;
- [ ] benchmark `P2-BENCH-1` está fresco;
- [ ] independent review não deixou Critical/High aberto;
- [ ] limitações e non-goals continuam explícitos;
- [ ] nenhum commit/push ou mutação global é necessário para esta entrega.

O lead só marca o checklist como completo após a rodada final e registra o
SHA base, fingerprint do diff e contagens em `readiness.json`.
