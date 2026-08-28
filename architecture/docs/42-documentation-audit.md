# 42 — Documentation Audit

**Status:** `FINAL_PASS_WITH_LIMITATIONS` · **Audit scope:** documentação e artefatos de especificação · **Data:** 2026-08-28

Este gate verifica se a fase documental atende ao brief, não se o futuro harness funciona. A classificação distingue `PASS`, `PASS_WITH_LIMITATION`, `PARTIAL`, `FAIL` e `NOT_RUN`; uma limitation não é escondida para obter um AAA artificial. O round-4 de sign-off independente foi concluído e está registrado em [`43-independent-review.md`](./43-independent-review.md).

## Inventory gate

| Artefato | Esperado | Observado nesta rodada | Estado |
| --- | ---: | ---: | --- |
| `architecture/HARNESS-SPEC.md` | 1 | 1 | PASS |
| `architecture/docs/README.md` | 1 | 1 | PASS |
| numbered docs `architecture/docs/00`–`architecture/docs/44` | 45 | 45 | PASS |
| ADRs in `architecture/docs/adr/` | 11 | 11 | PASS |
| Mermaid diagrams in `architecture/docs/diagrams/` | 12 | 12 | PASS |
| conceptual contracts in `architecture/docs/contracts/` | 12 | 12 | PASS |
| routing examples | ≥30 | 40 | PASS |

## Quality-bar results

| ID | Gate | Resultado | Evidência |
| --- | --- | --- | --- |
| DOC-01 | completude e indexação | PASS | inventory acima; [`README.md`](./README.md); [`HARNESS-SPEC.md`](../HARNESS-SPEC.md) |
| DOC-02 | arquitetura por componente | PASS | [`02-system-architecture.md`](./02-system-architecture.md): matrix operacional + decision/activation matrix para 21 componentes |
| DOC-03 | autoridade, routing e no-skill fallback | PASS | [`04-authority-model.md`](./04-authority-model.md), [`06-routing-system.md`](./06-routing-system.md), [`35-routing-examples.md`](./35-routing-examples.md) |
| DOC-04 | fonte, provenance e current/proposed/unknown | PASS_WITH_LIMITATION | [`README.md`](./README.md), ADR-009, source register abaixo; host-load causal permanece UNKNOWN |
| DOC-05 | 12 contracts com semântica comum | PASS | `contracts/` contém `schema_version`, ID primário, `record.status`, `record.provenance`, `record.evidence_refs` e invariantes por tipo |
| DOC-06 | ≥30 casos de routing | PASS | 40 linhas numeradas em [`35-routing-examples.md`](./35-routing-examples.md) |
| DOC-07 | verification, critique, assurance, AAA e stops | PASS | [`13-verification-system.md`](./13-verification-system.md), [`14-assurance-system.md`](./14-assurance-system.md), [`15-stop-conditions.md`](./15-stop-conditions.md), [`22-aaa-definition.md`](./22-aaa-definition.md) |
| DOC-08 | boundary nativa do Codex | PASS_WITH_LIMITATION | [`HARNESS-SPEC.md`](../HARNESS-SPEC.md), ADR-009; internals de matching/load/compaction continuam UNKNOWN |
| DOC-09 | documentação-only / sem leakage | PASS | scan de source/config/deploy abaixo; [`00-vision.md`](./00-vision.md) declara escopo |
| DOC-10 | usability, glossary, links, diagrams | PASS_WITH_LIMITATION | index/glossary/12 diagrams; Mermaid parser não disponível localmente |
| DOC-11 | crítica adversarial independente | PASS | rounds 1–4 registraram reparos; round 5 confirmou independentemente os gates substantivos e `APPROVE_WITH_LIMITATIONS` em `architecture/docs/43` |

## Deterministic command ledger

Os comandos abaixo são checks de leitura, não implementação. O audit final deverá preservar output/exit state no processo ledger em `.agent/verification.jsonl`.

| Check | Procedure | Resultado da rodada |
| --- | --- | --- |
| inventory | `find architecture/docs -maxdepth 1 -type f`, `find architecture/docs/adr`, `find architecture/docs/diagrams`, `find architecture/docs/contracts` | PASS: 45 / 10 / 12 / 12 |
| routing count | contar linhas `^\| [0-9]+ \|` em `architecture/docs/35-routing-examples.md` | PASS: 40 |
| common contract envelope | procurar `schema_version`, `record.status`, `record.provenance`, `record.evidence_refs` nos 12 files | PASS |
| local Markdown links (deliverable scope) | `python3 .../engineering-framework/scripts/check_links.py --path architecture/HARNESS-SPEC.md --path architecture/docs/<each .md> .` | PASS: 215 internal links; 14 external links skipped offline |
| local Markdown links (whole workspace) | same checker at repository root | FAIL only in pre-existing `references/skill-audit/data/provenance-evidence/raw/` fixtures: 50 findings (48 stale/missing targets plus 2 root-escaping links); no failures under `architecture/docs`/`architecture/HARNESS-SPEC.md` |
| Mermaid availability | `command -v mmdc` | NOT RUN: executable não instalado |
| Mermaid structural sanity | first-line diagram grammar, node/edge delimiters, state names and embedded/file edge parity | PASS: 12 files inspected; state graph has 33 unique edges in both surfaces (30 state-to-state plus 3 terminal) |
| implementation leakage | source/config/deploy scan fora de `references/skill-audit/`, `projects/codex-harness/.agent/`, `projects/codex-harness/.gauntlet/` | PASS: nenhum source/config/runtime novo |
| Git history | `git rev-parse --show-toplevel` | NOT RUN: workspace não é Git repository |

## Source register

| Source ID | Class | Retrieved/observed | Claims permitted | Limitation |
| --- | --- | --- | --- | --- |
| `LOCAL-AUDIT-01` | LOCAL / OBSERVED | 2026-08-28 | inventory, overlap, duplicate paths, routing probe, P0 gaps | audit static; routing n=5 e sem host-load trace |
| `LOCAL-AUDIT-02` | LOCAL / OBSERVED | 2026-08-28 | `design-director` visual boundary, evidence/critic/iteration patterns | não prova Director universal nem specialists callable |
| `LOCAL-AUDIT-03` | LOCAL / PROPOSED | 2026-08-28 | contracts/authority/roadmap recommendations | recomendação, não runtime |
| `OFFICIAL-SKILLS` | OFFICIAL / CURRENT | 2026-08-28 | Skill package shape, `SKILL.md`, optional resources, metadata-first matching language | comportamento interno além da página não inferido |
| `OFFICIAL-AGENTS` | OFFICIAL / CURRENT | 2026-08-28 | discovery/merge de `AGENTS.md` conforme documentação pública | não prova precedence universal entre skills duplicadas |
| `OFFICIAL-SUBAGENTS` | OFFICIAL / CURRENT | 2026-08-28 | subagents como delegação/paralelismo e custo adicional | schema/concurrency exatos não assumidos |
| `OFFICIAL-CONFIG` | OFFICIAL / CURRENT | 2026-08-28 | project/user config layers, trust, approval/sandbox concepts | não autoriza mudança global |
| `OFFICIAL-MCP` | OFFICIAL / CURRENT | 2026-08-28 | MCP como tools/contexto externo e server configuration | provider availability remains runtime fact |

URLs oficiais: [Skills](https://learn.chatgpt.com/docs/build-skills), [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Config](https://learn.chatgpt.com/docs/config-file/config-basic), [MCP](https://learn.chatgpt.com/docs/extend/mcp). O source register não transforma página externa em evidence de runtime local.

## Findings and dispositions

| Severity | Finding | Disposition |
| --- | --- | --- |
| CRITICAL | nenhum finding crítico aberto após a criação dos gates finais | PASS por ausência; qualquer novo authority/contract blocker reabre a fase |
| HIGH | nenhum finding alto substantivo aberto; o High procedural do round 4 foi fechado ao registrar o resultado real | PASS após disposição em [`43-independent-review.md`](./43-independent-review.md) |
| MEDIUM | Mermaid não pode ser parseado/renderizado porque `mmdc` não está instalado | manter limitation; static sanity é a evidência disponível; validar parser na Phase 1 |
| MEDIUM | host-load trace e causal benchmark não estão expostos | manter `UNKNOWN`; tratar como P0 de implementação, não como claim de qualidade atual |
| LOW | não há histórico Git neste workspace | registrar impossibilidade de atribuir preexistência; não executar operação destrutiva para compensar |
| LOW | source register oficial é retrieval log documental, não digest arquivado da página | usar URL + data + claim mapping; arquivar snapshot/digest somente se a futura governance exigir |

Nenhum finding histórico foi removido. Não há Critical/High aberto; as limitações e os 50 achados de fixtures fora do escopo (48 alvos stale/missing e 2 links root-escaping) permanecem explícitos em `architecture/docs/43` e `architecture/docs/44`.

## Final audit criterion

`PASS` final exige link check sem target local ausente, inventory completo, enum/terminology consistency revisada, review fresh separada e nenhuma implementação fora do escopo documental. Todos passaram nesta fase; o status é `FINAL_PASS_WITH_LIMITATIONS` porque parser Mermaid, host-load trace, causal benchmark, Git history e revalidação web não fazem parte do estado observado. A implementação posterior permanece isolada em `projects/codex-harness/` e não é coberta por este gate histórico.
