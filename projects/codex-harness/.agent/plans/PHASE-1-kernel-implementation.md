# ExecPlan — PHASE1-001 Harness Kernel

## Purpose / Big Picture

Materializar somente a Fase 1 do Codex Capability Harness: um kernel local,
contract-first, tipado, determinístico, observável e testável. Ao final, um
engenheiro poderá validar records, manifests, profiles, decisões de rota,
estado e telemetria sem executar capabilities ou providers.

## Progress

- [x] (2026-08-28) Recuperar especificações anexadas, documentação-base, ADRs e limitações.
- [x] (2026-08-28) Confirmar repositório Git remoto e preservar `skill-audit` como submódulo
  independente e intocado.
- [x] (2026-08-28) Escolher e registrar stack de baixo risco (ADR-011).
- [x] (2026-08-28) Congelar quality bar P1-QB-1 e preparar gate `IMPLEMENTATION_READY`.
- [x] (2026-08-28) Implementar contracts, validation, serialization e error taxonomy.
- [x] (2026-08-28) Implementar registry, classification, routing e authority.
- [x] (2026-08-28) Implementar evidence, artifacts, state, stops e telemetry.
- [x] (2026-08-28) Integrar CLI, layout `.harness/`, fixtures, testes e evidências de execução.
- [ ] Rodar gates reais, revisão adversarial independente, corrigir e retestar.

## Surprises & Discoveries

- O workspace tinha documentação completa, mas nenhuma fonte executável do
  harness; o perfil é `GREENFIELD` apesar de o repositório ser agora Git.
- `../../references/skill-audit/` é um repositório independente e não deve ser absorvido nem
  alterado durante a implementação.
- O ambiente global não possui todos os validadores; as ferramentas de dev serão
  isoladas em `.venv/` e não serão dependências de runtime.
- A migração de isolamento foi concluída antes da retomada; runtime, estado,
  configuração, testes e evidências estão sob `projects/codex-harness/`.
- A primeira execução integrada encontrou 39 erros de `mypy --strict`; eles foram
  reduzidos a zero com tipagem explícita, sem silenciamento amplo, e a suíte
  passou a cobrir a CLI e os limites de entrada.
- O benchmark P1 registra apenas baseline local de latência; não mede qualidade,
  causalidade, providers ou SLO de produção.
- Os contratos documentais são a autoridade do domínio; detalhes internos do
  host Codex continuam `UNKNOWN` e não serão simulados como fatos.

## Decision Log

- 2026-08-28 — `GREENFIELD`, `FEATURE`, `BUILD`, `T3_SYSTEM`, risco `HIGH`,
  blast `SYSTEM`: muitos limites e dados não confiáveis justificam controle
  persistente e revisão adversarial.
- 2026-08-28 — Python 3.12+ stdlib runtime; `pytest`, `coverage`, `mypy` e
  `ruff` apenas para desenvolvimento. Ver ADR-011.
- 2026-08-28 — Records frozen e JSON determinístico; não usar `eval`, `pickle`,
  import de manifest ou execução de capability.
- 2026-08-28 — nenhuma modificação em `.codex`, Skills instaladas, MCP, Git
  remote ou submódulo; nenhuma operação de push nesta fase.

## Outcomes & Retrospective

Preencher somente após os gates finais com comandos, fingerprints e limitações
observadas. Não usar este documento para declarar sucesso antes da verificação.

## Context and Orientation

- Requisitos: anexos fornecidos pelo usuário e `../../architecture/HARNESS-SPEC.md`.
- Contratos: `../../architecture/docs/contracts/` e modelos normativos em
  `../../architecture/docs/05`, `../../architecture/docs/06`,
  `../../architecture/docs/13`, `../../architecture/docs/15`,
  `../../architecture/docs/18`, `../../architecture/docs/26`,
  `../../architecture/docs/27`.
- Autoridade: `../../architecture/docs/04-authority-model.md`,
  `../../architecture/docs/23-security-model.md`.
- Roadmap e limites: `../../architecture/docs/38-implementation-roadmap.md`,
  `docs/implementation/phase-1-deferred.md`.
- Controle de processo: `.agent/`, `.gauntlet/` e este ExecPlan.

## Scope and Constraints

Inclui os 12 contract models, envelope comum, validators, manifest/registry,
TaskProfile/classification primitives, RouteDecision/policy mínima, authority,
claim/procedure/evidence, ArtifactRecord/lineage, state machine/status,
StopEngine/budgets/progress, TelemetryEvent/log/redaction, CLI mínima, testes e
evidências.

Não inclui router runtime, execução, DAG de subagentes, Directors, verification
engine completo, assurance/Gauntlet runtime, provider/MCP, Skills, migração,
deploy ou `harness run`.

## Architecture and Interfaces

- `src/harness_kernel/models.py`: records e enums congelados.
- `src/harness_kernel/serialization.py`: conversão e JSON canônico.
- `src/harness_kernel/validation.py`: findings estruturadas e validação pura.
- `src/harness_kernel/registry.py`: manifests/indexes sem execução.
- `src/harness_kernel/classification.py`, `routing.py`, `authority.py`:
  decisões puras e explicáveis.
- `src/harness_kernel/evidence.py`, `artifacts.py`, `state.py`, `stops.py`,
  `telemetry.py`: prova, lineage, transições, parada e observabilidade.
- `src/harness_kernel/cli.py`: entrada local somente para validação/inspeção.
- `.harness/`: dados e configuração pertencentes ao projeto; nenhuma gravação
  global.

## Milestones

### M0 — gate de entrada e scaffolding local

Critério de saída: gate de entrada atual, isolamento de projeto e layout local
resolvem sem tocar o submódulo de referência.

### M1 — contratos e validação determinística

Critério de saída: os 12 records, JSON seguro/determinístico, erros e invariantes
passam por testes unitários e fixtures negativos.

### M2 — registry/classification/routing/authority

Critério de saída: decisões puras, explicáveis, versionadas e sem execução; as
políticas bloqueiam escopo, conflito e autoaprovação.

### M3 — evidence/artifacts/state/stops/telemetry

Critério de saída: lineage, freshness, transições, stop conditions e cadeia de
telemetria têm testes de falha e não mutam snapshots.

### M4 — CLI, fixtures, integration, security e evidence pack

Critério de saída: CLI read-only, gates locais, benchmarks e evidências atuais
estão presentes e reproduzíveis.

### M5 — gauntlet: inspect → critique → fix → retest → final report

Critério de saída: revisão independente sem Critical/High aberto e veredito
limitado honestamente à Phase 1.

## Plan of Work

O Lead congela interfaces e integra. Um worker de contracts implementa M1;
após inspeção, dois workers independentes implementam M2 e M3 em arquivos
disjuntos. O Lead implementa CLI/layout/fixtures/evidence e resolve conflitos.
Um reviewer fresco audita o artefato integrado sem aprovar o próprio código.

## Concrete Steps

1. Criar `pyproject.toml`, `.gitignore`, ADR-011, quality bar e deferred scope.
2. Registrar `IMPLEMENTATION_READY` e mudar o estado para BUILD/IMPLEMENT.
3. Escrever testes RED por workstream; implementar o mínimo para GREEN.
4. Integrar e executar format/lint/typecheck/test/coverage/schema/negative,
   incluindo a validação de caminhos e a CLI read-only.
5. Gerar `evidence/phase-1/` e `docs/implementation/phase-1-kernel-report.md`.
6. Obter revisão adversarial com perguntas sobre segurança, autoridade,
   determinismo, stale, stop, telemetria e isolamento.
7. Corrigir Critical/High, rerodar regressões e fechar o gate apenas com
   evidência atual.

## Validation and Acceptance

```text
ruff format --check src tests
ruff check src tests
mypy src
coverage run -m pytest
coverage report --fail-under=80
python -m harness_kernel --help
python -m harness_kernel validate .harness/config/kernel.json
```

Além dos comandos, os fixtures golden/negative devem cobrir contratos,
duplicate/cycle registry, classificação, rotas bloqueadas, autoaprovação,
transições inválidas, evidência stale, lineage e telemetria falsa.

## Risks and Human Decisions

- Risco: os documentos são proposta; mitigação: não afirmar fatos do host e
  manter integração Codex fora do escopo.
- Risco: JSON não confiável; mitigação: parser stdlib, schemas explícitos,
  limites de tamanho e sem execução dinâmica.
- Risco: alterações acidentais no sistema; mitigação: paths locais e scan de
  isolamento.
- Decisão humana pendente: threshold de performance/AAA para fases posteriores;
  Fase 1 registra baseline, não inventa SLO.

## Idempotence and Recovery

Cada workstream escreve somente seus arquivos. Reexecutar testes e geração de
evidências substitui apenas outputs derivados em `evidence/phase-1/`. Eventos e
verification records são append-only. Se um worker falhar, o Lead preserva o
estado, registra recovery em `.agent/execution-log.jsonl` e retoma pelo último
milestone sem resetar ou alterar o submódulo.

## Artifacts and Evidence

- `.agent/gates/PHASE1-IMPLEMENTATION-READY-0002.json`
- `.agent/backlog.json`, `.agent/state.json`, `.agent/execution-log.jsonl`,
  `.agent/verification.jsonl`
- `src/harness_kernel/`, `tests/`, `.harness/`
- `evidence/phase-1/`
- `docs/implementation/phase-1-kernel-report.md`

## Current status

`IN_PROGRESS` — repository isolation was validated and the user continuation
authorization resumed the bounded Phase 1 implementation. Source/tests/CLI are
integrated and green; evidence pack, control-plane reconciliation and the final
independent gauntlet review remain open.
