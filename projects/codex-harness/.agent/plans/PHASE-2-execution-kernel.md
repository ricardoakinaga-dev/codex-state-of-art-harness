# ExecPlan — PHASE2-001 Execution Kernel

## Purpose / Big Picture

Implementar a Fase 2 explicitamente autorizada: um execution kernel local,
determinístico, contract-first e bounded que transforma request em profile,
route, invocation ou graph, provider fixture, artifact, verification,
critique/assurance, bounded repair, RunSummary e telemetry. O resultado máximo
honesto é `PASS_WITH_LIMITATIONS` do kernel local; isso não prova o runtime
completo do Codex.

## Progress

- [x] (2026-08-28 13:05 BRT) Recuperar instruções, anexo, arquitetura, Phase 1, estado, testes e baseline de qualidade.
- [x] (2026-08-28 13:20 BRT) Congelar P2-QB-1, threat model, ADRs e entry gates técnicos.
- [x] (2026-08-28 18:30 BRT) Hardening TDD de registry, autoridade, serialização, state e telemetry.
- [x] (2026-08-28 18:30 BRT) Implementar walking skeleton direct/provider/invocation e persistence local.
- [x] (2026-08-28 18:30 BRT) Implementar graph bounded, limits, cancellation, timeout, artifacts e evidence.
- [x] (2026-08-28 18:30 BRT) Implementar verification, critique, assurance, repair, RunSummary e CLI.
- [ ] (2026-08-28 18:30 BRT) Fechar revisão independente e emitir gate VERIFIED; a implementação local, os testes e as evidências técnicas foram regenerados, mas o critic externo não retornou um relatório utilizável.

## Surprises & Discoveries

- A Fase 1 está realmente isolada e verde, mas seu modelo de invocation ainda
  não diferencia todos os estados de execução exigidos pela Fase 2.
- A CLI atual é deliberadamente read-only e o registry local possui somente um
  validator de metadata; provider fixtures precisam ser built-in e explícitos.
- O checker de estado exige ExecPlan, backlog, log, gates e verificação
  reconciliáveis; nenhum record histórico será reescrito.
- A disponibilidade de workers especializados não é garantida neste ambiente;
  o Lead mantém ownership final e registrará qualquer revisão degradada.

## Decision Log

- 2026-08-28 — `BROWNFIELD`, `FEATURE`, `BUILD`, `T3_SYSTEM`, risco `HIGH`,
  blast `SYSTEM`: há código Phase 1 mantido e novos limites de execução.
- 2026-08-28 — Python 3.12 stdlib em runtime; dev tools continuam somente no
  `.venv` local.
- 2026-08-28 — providers determinísticos locais serão os únicos executores;
  shell, rede, Skill, subagent, MCP, host adapter e import dinâmico permanecem
  fora da superfície.
- 2026-08-28 — models existentes recebem apenas extensões opcionais compatíveis;
  módulos novos concentram runtime para não duplicar regras de Phase 1.
- 2026-08-28 — graph executa sequencialmente em ordem topológica; concorrência
  só será considerada em fase posterior após prova de benefício e isolamento.

## Outcomes & Retrospective

Resultado da verificação integrada: 187 testes passaram, cobertura total 84%
(7.771 statements; 1.268 missed), Ruff format/check e mypy passaram, os 7
testes de integração CLI passaram, o benchmark `P2-BENCH-1` foi regenerado e
os scans de segurança não encontraram os padrões de execução proibidos. A
matriz de routing negativa obrigatória também passou, e o kernel não
self-authorize sem grant explícito.

O critic independente foi tentado com os workers disponíveis, mas nenhum
retornou uma revisão utilizável. Isso é registrado em
`evidence/phase-2/independent-review.md`; não é convertido em aprovação pelo
lead. O status final do plano é `VERIFY` / `CONDITIONAL PASS`, com o gate
`PHASE2-VERIFIED` pendente dessa revisão. Limitações residuais: providers
reais, host Codex, Skills, subagents, MCP, shell, rede, credenciais,
concorrência avançada, locking multi-processo e produção permanecem fora do
escopo.

## Context and Orientation

- Requisito primário: arquivo fornecido pelo usuário, preservado no attachment
  path e lido integralmente antes desta implementação.
- Arquitetura: `../../architecture/HARNESS-SPEC.md`,
  `../../architecture/docs/02-system-architecture.md`, `04-authority-model.md`,
  `06-routing-system.md`, `07-orchestration-model.md`, `13-verification-system.md`,
  `14-assurance-system.md`, `15-stop-conditions.md`, `18-telemetry.md`,
  `23-security-model.md`, `24-failure-model.md`, `25-degradation-model.md`,
  `26-artifact-model.md` e `27-state-model.md`.
- Phase 1: `docs/implementation/phase-1-quality-bar.md`,
  `docs/implementation/phase-1-deferred.md`, `src/harness_kernel/` e
  `evidence/phase-1/`.
- Controle: `.agent/`, `.gauntlet/`, `P2-QB-1`, gates e este ExecPlan.

## Scope and Constraints

Inclui hardening dos contratos existentes; invocation lifecycle; provider
protocol/registry; direct execution; graph DAG bounded; authority snapshot;
failure taxonomy; timeout/cancel/budgets; artifact/evidence integrity;
verification/critique/assurance/repair; RunSummary; telemetry; persistence
local; CLI run/dry-run/explain/json/quality/doctor; testes, benchmarks, docs e
evidence Phase 2.

Exclui adapter real do Codex, execução de Skills ou subagents, MCP, shell,
rede, providers reais, Directors, produção, sandbox hostil, cross-project
packages, deploy, daemon e concorrência avançada. `references/skill-audit/` é
somente leitura.

## Architecture and Interfaces

- `models.py` preserva os doze records e recebe campos opcionais para operação,
  origem, dependências, trace, graph budget e acceptance sem quebrar fixtures.
- `boundary.py` controla somente paths project-relative, symlinks, bytes e
  atomic writes.
- `providers.py` define `CapabilityProvider`, `ProviderRegistry`, availability
  e `ProviderExecutionResult`; providers não fazem routing/auth/assurance.
- `execution.py` orquestra request → profile → route → invocation/graph →
  provider → artifact/evidence → verification → critique → assurance → summary.
- `graph.py` valida e executa `ExecutionGraph` sequencialmente, preservando
  partials e bloqueando dependentes.
- `authority.py` mantém as APIs Phase 1 e adiciona snapshot/expiry/scope/
  operation/delegation sem duplicar ownership de routing.
- `verification.py` e `assurance.py` mantêm boundary separado da execução;
  `persistence.py` só grava dentro de `ProjectBoundary`.
- `cli.py` mantém comandos Phase 1, acrescenta run e ferramentas de inspeção;
  todo input é validado e erros não ecoam dados sensíveis.

## Milestones

### M0 — specification and entry gates

P2-QB-1, threat model, ADRs, plan, backlog, gates TECHNICALLY_SPECIFIED e
IMPLEMENTATION_READY existem, apontam para arquivos reais e reconciliam no
checker.

### M1 — Phase 1 hardening and invocation contract

Regressões cobrem registry admission/dependency/origin/integrity,
serialization malformed/roundtrip, lifecycle, authority expiry/scope e
telemetry bounds/redaction/order. Invocation states e failure taxonomy têm
transições determinísticas.

### M2 — providers, direct route and graph

Success/failure fixtures executam somente após route + authority; graph valida
bounded DAG e executa topologicamente; cancellation, timeout, budgets, stop e
partial results são observáveis.

### M3 — proof, assurance, repair and persistence

Artifacts/evidence têm digest/lineage/freshness; verification, critique,
assurance e bounded repair produzem RunSummary e telemetry; recovery local
separa finished, unfinished e corrupt.

### M4 — CLI, docs, evidence and benchmarks

`run`, `--dry-run`, `--json`, `explain`, `quality` e `doctor` têm smoke tests;
todos os relatórios Phase 2, readiness JSON e exemplos de configuração estão
atuais e ligados ao source state.

### M5 — independent gauntlet and closure

Reviewer fresco desafia security, authority, DAG, provider, proof, repair,
telemetry e CLI. Critical/High são corrigidos e a regressão completa roda de
novo antes do gate VERIFIED.

## Plan of Work

O Lead mantém ownership de `models.py`, `validation.py`, `cli.py`, controle,
evidências e integração. Workstreams de runtime são separados por módulo:
boundary/persistence; providers; graph; execution; verification/assurance.
Testes RED precedem cada implementação. Scouts podem somente inspecionar e
reviewers não recebem a justificativa do builder; toda integração é validada
pelo Lead com diff e comandos atuais.

## Concrete Steps

1. Validar que o baseline Phase 1 continua verde e registrar o contexto nos
   ledgers; não modificar `skill-audit`.
2. Criar extensões opcionais de models/enums e testes RED para invocation,
   failure categories e graph budgets; implementar e rodar regressões.
3. Criar `ProjectBoundary`, atomic local persistence e provider protocol com
   success/failure fixtures; testar unavailable, mismatch e no hidden fallback.
4. Criar authority snapshot com expiry/scope/operation/conditions/delegation;
   aplicar a checagem antes de qualquer provider e registrar evidence.
5. Criar graph builder/validator/executor; testar cycles, dangling refs,
   duplicate IDs, impossible deps, conflicts, merge, budgets e partials.
6. Criar verification procedures para file/hash/schema/expected/invariant e
   artifacts/evidence com digest/freshness; rejeitar forged/stale promotion.
7. Criar critique blind packet, assurance decisions e bounded repair com
   attempt provenance e stop engine existente antes/durante/depois.
8. Criar RunSummary, structured telemetry e atomic persistence; simular falha
   de telemetry sem perder o resultado e distinguir recovery corrupt.
9. Acrescentar CLI run/dry-run/explain/json/quality mantendo comandos Phase 1 e
   doctor sem execução; adicionar golden scenarios A–L e security tests.
10. Rodar format/lint/mypy/pytest/coverage, benchmarks e scans; gerar o pacote
    `evidence/phase-2/` e `readiness.json` com SHA/dirty state atual.
11. Obter revisão adversarial independente, corrigir Critical/High, rerodar
    testes e fechar somente com gate VERIFIED e final report honesto. Nesta
    rodada o passo ficou bloqueado por indisponibilidade do reviewer e foi
    mantido como limitação explícita.

## Validation and Acceptance

```text
./.venv/bin/ruff format --check src tests
./.venv/bin/ruff check src tests
./.venv/bin/mypy src
./.venv/bin/coverage run -m pytest -q
./.venv/bin/coverage report --fail-under=80
./.venv/bin/python -m harness_kernel doctor --json
./.venv/bin/python -m harness_kernel run --dry-run --json "..."
./.venv/bin/python -m harness_kernel run --json "..."
./.venv/bin/python -m harness_kernel quality --json
python3 /home/ricardo/.agents/skills/engineering-framework/scripts/check_state.py .
```

Além dos comandos, a matriz A–L deve provar direct success, denied authority,
graph success/failure, timeout/cancel, verification fail, partial, stop before
run, repair success/exhaustion e stale evidence. Security tests devem cobrir
manifest tampering/divergence, boundary/symlink escape, provider mismatch,
serialization limits, forged artifacts, oversized telemetry e replay state.

Resultado local registrado em `evidence/phase-2/readiness.json`; o status
`CONDITIONAL_PASS` não deve ser promovido sem a revisão independente exigida
por `P2-QB-1`.

## Risks and Human Decisions

- Risco principal: adicionar execução pode ser confundido com capacidade do
  Codex host; mitigação: providers locais explícitos e documentação de não-goals.
- Risco de autoridade: uma route válida não basta; mitigação: snapshot com
  expiry e operation/scope antes do provider.
- Risco de integridade: provider success pode não ser verification; mitigação:
  procedure/evidence/critique/assurance separados.
- Risco de persistência: crash pode produzir falso DONE; mitigação: atomic
  writes e recovery CORRUPT/UNFINISHED explícito.
- Decisão humana pendente: nenhum deploy, provider real, sandbox hostil ou
  threshold de produção é requerido/solicitado nesta fase; futura ativação
  exige novo gate e autoridade apropriada.

## Idempotence and Recovery

Pure records e registries retornam cópias novas. `ProjectBoundary` escreve
temporários nomeados sob o mesmo diretório e renomeia atomicamente; nenhum
output sai do projeto. Reexecutar `run --dry-run`, quality e benchmarks não
chama providers nem altera global state. Run persistence usa run_id e rejeita
collision; recovery lê version, status e integrity antes de continuar. Em
falha de worker, o Lead registra evento RECOVERY, preserva partial evidence e
retoma do milestone, sem reset destrutivo ou reescrita de histórico.

## Artifacts and Evidence

- `.agent/gates/PHASE2-TECHNICALLY-SPECIFIED-0001.json`
- `.agent/gates/PHASE2-IMPLEMENTATION-READY-0001.json`
- `.agent/backlog.json`, `.agent/state.json`, `.agent/execution-log.jsonl`,
  `.agent/verification.jsonl`
- `src/harness_kernel/` e `tests/`
- `.harness/state/`, `.harness/evidence/`, `.harness/telemetry/`
- `evidence/phase-2/README.md`, reports, `readiness.json` e `final-report.md`
- `docs/phase-2-threat-model.md`, `docs/implementation/phase-2-quality-bar.md`
  e ADRs P2-001…P2-004.

## Current status

`VERIFY` / `CONDITIONAL PASS`. Os entry gates continuam válidos, o código da
Phase 2 foi implementado e verificado localmente no escopo bounded, e o
checkpoint histórico permanece preservado. Não há claim de `PHASE2-VERIFIED`,
produção, runtime completo do Codex ou `AAA_VERIFIED` enquanto a revisão
independente não estiver disponível.
