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
- Phase 2: `PASS_WITH_LIMITATIONS` e congelada dentro do kernel local bounded;
  veja [`evidence/phase-2/PHASE2-FROZEN.md`](evidence/phase-2/PHASE2-FROZEN.md).
- Phase 3: extensão read-only de host capability integration em execução sob
  `P3-QB-1`; o runtime completo do Codex continua `NOT PROVEN`.

A Phase 2 permite somente providers fixtures determinísticos e execução
project-local. A Phase 3 adiciona inspeção, inventário, parsing e planejamento
de carregamento declarativo; não executa Skill/subagent/MCP/provider, shell,
rede ou deploy, nem muta configuração global. O closeout da Phase 2 registra
232 testes, 85% de cobertura total, Ruff/mypy/CLI/benchmark/security PASS e
`check_state.py` 10/10; isso não é uma alegação de runtime completo do Codex.

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
PYTHONPATH=src .venv/bin/python -m harness_kernel.phase3_cli host inspect --json
PYTHONPATH=src .venv/bin/python -m harness_kernel.phase3_cli host list --json
PYTHONPATH=src .venv/bin/python -m harness_kernel.phase3_cli capabilities list --json
PYTHONPATH=src .venv/bin/python -m harness_kernel.phase3_cli capabilities inspect harness-kernel --explain --json
# Após instalar o projeto: harness host inspect --json
# Após instalar o projeto: harness capabilities list --json
```

A CLI lê dados project-local e metadados read-only do host, não carrega
módulos de input e não executa capacidades arbitrárias. `run` chama
exclusivamente providers determinísticos registrados e grava apenas sob
`.harness/`; `doctor`, `--dry-run` e os comandos Phase 3 de host não executam
provider nem afirmam que uma capability foi carregada.
