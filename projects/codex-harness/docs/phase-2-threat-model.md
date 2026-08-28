# Threat model — Phase 2 Execution Kernel

## Boundary and assets

O único domínio de escrita e execução permitido é
`projects/codex-harness/`. Entradas de request, JSON, manifests, providers,
fixtures, artifacts e evidence são não confiáveis. Ativos protegidos incluem
arquivos fora do projeto, `~/.codex`, `.agents`, Skills instaladas, configuração
MCP, credenciais, rede, integridade dos records, autoridade e o significado de
`PASS`.

## Threats and controls

| Ameaça | Controle obrigatório |
| --- | --- |
| Path traversal, absolute path ou symlink escape | `ProjectBoundary` resolve o caminho e exige `relative_to(project_root)` antes de ler/escrever; links são rejeitados se escaparem |
| Manifest tampering ou registry divergence | hash SHA-256, provenance, origin/precedence, duplicate detection e divergência falham antes de seleção |
| Capability/provider não autorizado | registry metadata não equivale a admission, availability ou authorization; authority snapshot é verificado antes da invocação |
| Provider mismatch, hidden fallback ou shell arbitrário | provider protocol explícito; somente providers registrados no runtime são chamados; nenhum subprocess, import dinâmico ou rede |
| Authority replay, expiry ou scope confusion | subject, operation, scope, conditions, delegation e expiry são avaliados no instante da execução e preservados no evidence |
| Graph cycle, dangling dependency ou orçamento impossível | validação completa do DAG e dos budgets antes de iniciar qualquer node; dependente bloqueia após falha |
| Forged artifact/evidence ou stale promotion | digest recomputado, owner/lineage verificados, freshness invalidada por mudança e verification não aceita evidence stale |
| Serialization bomb ou payload excessivo | parser sem `eval`/`pickle`, duplicate keys rejeitadas, limites de bytes/profundidade/campos e unknown fields controlados |
| Telemetry leak, oversized event ou failure | redaction recursiva, payload fixo e bounded, hash chain, append-only local log; telemetry failure vira limitação observável |
| Replay de state corrompido ou repair inválido | state versionado, atomic write, recovery distingue finished/unfinished/corrupt; repair só com causa, acceptance e budget |

## Explicit non-goals

Esta fase não oferece sandbox hostil para código de terceiros. Não há rede,
shell, subprocesso, importação de módulos vindos de input, adapter real do
Codex, execução de Skills, subagents, MCP, Directors ou concorrência avançada.
Esses limites são parte do controle, não capacidades ausentes a serem inferidas.

## Configuration and precedence

A configuração é somente a de `.harness/config/kernel.json`, com paths
project-relative e limites máximos. CLI flags explícitas podem escolher apenas
providers registrados e budgets menores que os limites configurados; elas não
podem ampliar escopo, habilitar rede/shell ou desabilitar autoridade,
telemetria, verification ou boundary. Manifest provenance e registry admission
precedem route selection; route precede authority; authority precede provider.

## Migration and recovery

Records `CI-1` e `EG-1` ganham campos opcionais compatíveis com os snapshots da
Fase 1; defaults preservam leitura de fixtures antigas. Novas persistências usam
format version explícito, unknown fields são rejeitados no contrato e writes são
temporários + rename atômico dentro do projeto. Um state incompleto não é
reportado como concluído; um state ilegível é `CORRUPT` e bloqueia recovery
automático.
