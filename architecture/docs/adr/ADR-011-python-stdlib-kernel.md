# ADR-011 — Python stdlib para o kernel da Fase 1

- **Status:** ACCEPTED FOR PHASE 1
- **Date:** 2026-08-28
- **Decision owners:** Lead de engenharia; autoridade externa do Codex permanece fora deste repositório

## Context

A Fase 1 precisa materializar contratos tipados, validação determinística,
serialização JSON, registry sem execução, classificação, autoridade, evidência,
estado, stop engine e telemetria. O kernel deve ser local ao projeto, auditável,
fácil de testar e não pode alterar Skills, configuração global ou ferramentas do
host.

## Decision

Usaremos Python 3.12 ou superior e somente a biblioteca padrão no runtime. Os
artefatos de desenvolvimento usam `pytest`, `coverage`, `mypy` e `ruff`,
instalados apenas no ambiente virtual do projeto para verificação. A CLI será
invocada por `python -m harness_kernel` com `PYTHONPATH=src` durante a Fase 1.

Todos os records de domínio serão imutáveis (`dataclass(frozen=True)`), terão
versão explícita e serão convertidos para JSON por uma camada própria com
ordenação estável de chaves. Nenhum loader executa código, importa módulos de
manifests ou chama providers.

## Alternatives considered

- **Pydantic:** reduziria código de validação, mas adicionaria uma dependência
  de runtime e esconderia parte das invariantes que precisam de evidência
  explícita nesta fase.
- **TypeScript/Node:** oferece bom ecossistema de schemas, mas aumentaria a
  superfície de toolchain e não é necessário para o kernel local e sem runtime
  de execução.
- **YAML/TOML como formato canônico:** ambos são úteis para configuração humana,
  porém JSON determinístico é suficiente para contratos, fixtures e auditoria;
  formatos adicionais podem ser introduzidos depois com parser isolado.

## Consequences

Positivas: baixa superfície de ataque, reprodutibilidade, dependências de
produção nulas, testes rápidos e compatibilidade com ambientes Python atuais.
Negativas: teremos mais código explícito de validação e a CLI ainda não será um
pacote distribuível. Packaging, router runtime e integração com providers ficam
para fases posteriores.

## Verification

O gate da Fase 1 exige `ruff format --check`, `ruff check`, `mypy`, testes,
coverage mínima de 80% para o núcleo, fixtures negativas, verificação de
schemas/registry/state/authority/telemetria e revisão adversarial independente.
