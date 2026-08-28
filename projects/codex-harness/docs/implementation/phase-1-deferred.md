# Fase 1 — Escopo explicitamente deferido

Este registro evita que a implementação do kernel seja interpretada como o
harness completo. Itens abaixo não podem ser ativados por inferência a partir
dos contratos da Fase 1.

| Item | Motivo do deferimento | Fase alvo | Dependência | Risco se antecipado |
| --- | --- | --- | --- | --- |
| Router runtime e execução de capabilities | Fase 1 só valida `RouteDecision`; não há executor ou provider dispatch | 2 | contratos, registry e autoridade estáveis | execução não autorizada |
| Orquestração DAG/subagentes | exige runtime de tarefas, retry, cancelamento e merge | 2 | route model e state machine | concorrência sem prova |
| Verification/assurance engine completo | Fase 1 possui links e records, não a prova completa nem seus adapters | 3 | evidência, artifacts e telemetria | falso sinal de qualidade |
| Engineering/Design/Game/Research Directors | são donos de estratégia e runtime de domínio | 4 | router, assurance e autoridade | ativação indevida de capabilities |
| Modernização, instalação ou substituição de Skills | fora do isolamento `.harness/` e proibido nesta fase | 5 | governança e adapters Codex | mutação global / shadowing |
| Integração com Codex, MCP e providers reais | fatos de host são externos ao kernel local | 2+ | contratos de integração e aprovação | dependência de internals não comprovados |
| Deploy, serviço persistente e operação de produção | nenhum runtime de produção é criado | posterior | threat model, SLOs e rollback | blast radius não controlado |
| Otimização causal/AAA | microbenchmarks locais não medem qualidade causal ou AAA | posterior | dados reais e assurance | claim de perfeição sem evidência |

## Limites operacionais

- Não existe comando `harness run` nesta fase.
- O registry apenas lê, valida, lista e inspeciona manifests locais.
- Arquivos externos são dados não confiáveis; nenhum JSON pode executar código.
- O submódulo `skill-audit` é somente leitura e não participa do build.
- A configuração válida é `.harness/config/kernel.json`; nada em `~/.codex`,
  Skills instaladas ou servidores MCP é alterado.
