# Projeto isolado — `codex-harness`

Este diretório é a fronteira do projeto Python da Fase 1. Seu `src/`, `tests/`,
`.harness/`, `.agent/`, `.gauntlet/`, `evidence/`, configuração e ambiente de
desenvolvimento pertencem somente a ele.

Arquitetura compartilhada fica em [`../../architecture/`](../../architecture/).
O audit de referência fica em [`../../references/skill-audit/`](../../references/skill-audit/)
e permanece fora do runtime.

## Estado

A implementação bounded da Phase 1 foi verificada com PASS dentro desta
fronteira. Não há comando `harness run`, provider dispatch ou mutação de
Skills/configuração global.

## Verificação local

Com o ambiente virtual local disponível:

```text
PYTHONPATH=src .venv/bin/ruff format --check src tests
PYTHONPATH=src .venv/bin/ruff check src tests
PYTHONPATH=src .venv/bin/mypy src
PYTHONPATH=src .venv/bin/pytest -q
```

## CLI read-only

```text
PYTHONPATH=src .venv/bin/python -m harness_kernel --help
PYTHONPATH=src .venv/bin/python -m harness_kernel validate .harness/config/kernel.json
PYTHONPATH=src .venv/bin/python -m harness_kernel registry list
PYTHONPATH=src .venv/bin/python -m harness_kernel doctor
```

A CLI só valida/inspeciona dados declarativos locais; não carrega módulos,
executa capabilities ou escreve fora do projeto.
