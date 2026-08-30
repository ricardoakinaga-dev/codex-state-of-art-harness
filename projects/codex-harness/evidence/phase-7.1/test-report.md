# Test report

Resultados observados no worktree atual:

| Escopo | Comando/resultado |
| --- | --- |
| suíte completa | `1283 passed` com branch coverage |
| hardening Phase 7.1 | `720 passed` em `tests/unit/test_phase71*.py` |
| Phase 2 | `112 passed` |
| Phase 3 | `84 passed` |
| Phase 4 | `69 passed` |
| Phase 5 | `55 passed` |
| Phase 6 | `82 passed` |
| Phase 7 | `41 passed` |
| piloto real | `28 passed` |
| Ruff check/format | PASS; 179 arquivos formatados |
| mypy | PASS; 65 source files |
| compileall | PASS |

O comando válido de Phase 7 usa `tests/unit/test_phase7_*.py` e
`tests/evals/phase7`; não existe diretório `tests/integration/test_phase7_*`.
Os testes de hardening verificam estado, efeitos, rollback, identidade,
telemetria e evidência, não apenas execução de linhas.
