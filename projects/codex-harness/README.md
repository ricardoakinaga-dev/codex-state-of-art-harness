# Projeto isolado — `codex-harness`

Este diretório é a fronteira do projeto Python da Fase 1. Seu `src/`, `tests/`,
`.harness/`, `.agent/`, `.gauntlet/`, `evidence/`, configuração e ambiente de
desenvolvimento pertencem somente a ele.

Arquitetura compartilhada fica em [`../../architecture/`](../../architecture/).
O audit de referência fica em [`../../references/skill-audit/`](../../references/skill-audit/)
e permanece fora do runtime.

## Estado e escopo

- Arquitetura do sistema: `PROPOSED`.
- Phase 1: `IMPLEMENTED/VERIFIED` dentro desta fronteira.
- Phase 2: `CURRENT IMPLEMENTATION TARGET`, com kernel local em construção.
- Runtime completo do Codex: `NOT PROVEN`.

A Phase 2 permite somente providers fixtures determinísticos e execução
project-local. Não há Skill/subagent/MCP/host adapter, shell, rede, deploy ou
mutação de configuração global.

## Verificação local

Com o ambiente virtual local disponível:

```text
PYTHONPATH=src .venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/ruff check src tests
PYTHONPATH=src .venv/bin/mypy src
PYTHONPATH=src .venv/bin/pytest -q
```

## CLI local

```text
PYTHONPATH=src .venv/bin/python -m harness_kernel --help
PYTHONPATH=src .venv/bin/python -m harness_kernel validate .harness/config/kernel.json
PYTHONPATH=src .venv/bin/python -m harness_kernel registry list
PYTHONPATH=src .venv/bin/python -m harness_kernel doctor
PYTHONPATH=src .venv/bin/python -m harness_kernel run --dry-run --json "Change one local label"
```

A CLI lê somente dados project-local, não carrega módulos de input e não
executa capacidades arbitrárias. `run` chama exclusivamente providers
determinísticos registrados e grava apenas sob `.harness/`; `doctor` e
`--dry-run` não executam provider.
