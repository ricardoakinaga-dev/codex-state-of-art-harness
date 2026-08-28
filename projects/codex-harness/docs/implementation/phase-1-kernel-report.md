# Phase 1 — Harness Kernel implementation report

**Data:** 2026-08-28 12:10 BRT
**Status máximo permitido:** `Phase 1 Kernel implementation PASS`
**Scope:** somente `projects/codex-harness/`

## Architecture implemented

A implementação materializa a fatia contract-first da arquitetura: records
imutáveis, validação, serialização, control plane de registry, classificação,
minimum route, autoridade, evidence/claims, artifacts/lineage, state/stops e
telemetria privacy-aware. O pacote não possui executor, loader de capability,
provider dispatch ou mutação de Skill/configuração global.

## Language and runtime

- Python 3.12;
- biblioteca padrão no runtime;
- pytest, mypy, Ruff e coverage somente como dependências de desenvolvimento;
- `pyproject.toml` e `.venv/` pertencem a este projeto isolado.

## Files and contracts

Código em `src/harness_kernel/`:

- `models.py`: os 12 records e enums typed/frozen;
- `validation.py`, `serialization.py`, `errors.py`: invariantes, JSON seguro e
  taxonomy de erros;
- `registry.py`: semver, snapshots imutáveis, dependencies, conflicts, stale e
  provenance metadata-only;
- `classification.py`, `routing.py`: TaskProfile, seis dimensões, route e
  política mínima;
- `authority.py`, `evidence.py`, `artifacts.py`: poderes, claims/procedures/
  evidence e lineage;
- `state.py`, `stops.py`, `telemetry.py`: lifecycle, status multidimensional,
  bounded progress/stops e eventos append-only/redacted;
- `benchmarks.py`, `cli.py`, `__main__.py`: baseline local e CLI read-only.

O manifest local preserva origem/precedência explícita, source repository,
hash SHA-256 canônico, installation scope, project ownership e `forked_from`. O
mesmo ID+versão não pode ser registrado novamente de outra origem sem resolução
explícita; a CLI compara as cópias canônica/registry, respeita os diretórios do
config e valida referências de contrato.

## Invariants and safety boundary

- records são profundamente normalizados para tuplas e frozen;
- schema versions são verificadas contra o tipo;
- semver e dependências são determinísticos;
- alta confiança/sucesso/entrega exigem evidence compatível;
- `CAPABILITY_LOADED` exige evidence de observação;
- transições inválidas, authority escalation, self-approval e budgets sem
  limite são rejeitados;
- JSON não avalia strings e a CLI impõe limites de bytes, profundidade e path;
- nenhum módulo dentro de `.harness/capabilities/` é importado pelo kernel.

## Tests and validation

O resultado final reproduzível está em
[`../../evidence/phase-1/README.md`](../../evidence/phase-1/README.md):

- 99 testes unit/integration/golden/negative passaram;
- mypy strict passou em 17 arquivos;
- Ruff format/check passaram em 31 arquivos;
- coverage total: 81%, gate `--fail-under=80` passou;
- path/link/isolation/provenance validation passou no escopo entregue;
- o ledger canônico passou em `check_state.py` (`10` checks, `0` warnings,
  `0` failures);
- microbenchmarks cobrem manifest validation, registry loading, route
  validation, state transition e telemetry append.

## Documentation and ADRs

A arquitetura permanece separada em `architecture/`. A realização Python é
registrada aqui e no contrato conceitual de `CapabilityManifest`; a extensão de
provenance não reescreve a arquitetura inteira. A decisão de runtime stdlib
está em
[`../../../../architecture/docs/adr/ADR-011-python-stdlib-kernel.md`](../../../../architecture/docs/adr/ADR-011-python-stdlib-kernel.md).

## Deviations

- A CLI é chamada `harness-kernel` e deliberadamente não oferece `run`.
- `origin`/`precedence` e ownership foram tipados na realização do manifest
  para satisfazer a regra de project isolation; a precedência é uma política
  local do registry, não uma afirmação sobre precedência interna do Codex.
- O hash local autentica a representação canônica do manifest e suas
  referências locais declaradas; não autentica conteúdo remoto nem substitui
  uma verificação completa do código da capability.
- O benchmark é um baseline de processo local; não é benchmark causal nem SLO.

## Limitations and deferred scope

Ficam adiados: Directors, orquestração DAG/subagents, runtime de retry/cancel,
verification/assurance engine completo, providers/MCP/Codex host integration,
Skill modernization/install/replacement, deployment, persistência de produção,
causal AAA e medição de qualidade de output. O detalhe está em
[`phase-1-deferred.md`](./phase-1-deferred.md).

Os registros históricos da fase documental foram preservados em
`.agent/history/`; o ledger ativo do projeto está canônico e passa o checker de
estado. O checker completo do workspace ainda encontra 50 links históricos nos
fixtures brutos de `references/skill-audit`, que permanecem intocados.

## Next phase readiness

`CONDITIONAL`: os contracts e boundaries permitem iniciar desenho da Phase 2,
mas somente após definir o adapter de execução, authority real, persistence,
host-load observation e reconciliação do ledger. Esta entrega não autoriza
declarar harness completo, production ready, AAA verified, autonomous
orchestration complete, Skill modernization complete ou Codex integration
complete.
