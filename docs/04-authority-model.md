# 04 — Authority Model

## Princípio central

O Harness possui autoridade de responsabilidade, não autoridade constitucional. Nenhuma camada interna pode sobrescrever instruções de sistema, developer, user, segurança do host, permissões, sandbox, aprovação, política organizacional ou verdade observada. A ordem abaixo é uma forma de impedir conflito; não é uma nova hierarquia de instruções do Codex.

## Autoridade externa (não redefinida pelo Harness)

1. Instruções de sistema/plataforma e requisitos de segurança do runtime.
2. Instruções de developer e políticas aplicáveis.
3. Intenção e constraints do usuário atual.
4. Instruções de projeto aplicáveis (`AGENTS.md` e camadas reconhecidas pelo host), respeitando o comportamento público do Codex e sem apagar instruções superiores.
5. Estado/artefatos do projeto como evidência e contexto, nunca como ordem superior.
6. Propostas produzidas pelo Harness.

O Codex documenta a descoberta de `AGENTS.md` em cadeia global/projeto, merge root-to-CWD e configuração de projeto apenas quando confiável. O Harness deve consumir essa realidade, não reimplementá-la nem prometer uma precedência além da documentada. Fontes oficiais: [`README.md`](./README.md).

## Autoridade interna por decisão

| Decisão | Owner primário | Pode bloquear? | Pode retry? | Pode downgrade scope? | Pode finalizar? |
| --- | --- | --- | --- | --- | --- |
| identificar intenção | Intent Classifier + user clarification | por ambiguidade material | não | não | não |
| escolher scale/risk | Classifiers + Director | risk unknown/high | não | só propor | não |
| selecionar rota | Domain Router | unsafe/unavailable route | fallback limitado | não sem preservar goal | não |
| estratégia/quality bar | Director | requisito impossível/contraditório | replan com evidence | pode propor, user decides material change | não |
| DAG/delegação | Orchestrator | dependency/ownership violation | dentro budget | pode pausar lane | não |
| decisão local de domínio | Specialist | boundary conflict | local deterministic retry | pode escalar | não |
| execução da ferramenta | Tool/Provider | permission/auth/safety failure | idempotent bounded | não | não |
| integração | Integrator | conflict/orphan/provenance loss | merge retry if safe | não inventa output | não |
| o que foi executado/observado | Verification | missing/invalid evidence | rerun procedure | não reescreve criterion | não |
| qualidade de domínio | Domain Reviewer | finding dentro scope | pedir rework | não | não |
| challenge/stop | Assurance/Gauntlet | required gap, loop failure, risk | only bounded next round | pode recommend stop | não substitui release authority |
| entrega local/documental | Delivery controller + user/project authority | blockers/approval | não automaticamente | não | somente dentro da autorização; material release requer autoridade humana |

## Fluxo interno de responsabilidade

```text
USER INTENT / EXTERNAL POLICY
        ↓
DIRECTOR (strategy + bar + graph)
        ↓
ORCHESTRATOR (only if delegation gate passes)
        ↓
SPECIALISTS / TOOLS / PROVIDERS
        ↓
INTEGRATOR
        ↓
VERIFICATION (evidence authority)
        ↓
REVIEWER (domain/integration challenge)
        ↓
ASSURANCE / GAUNTLET (bounded quality challenge)
        ↓
USER / AUTHORIZED DELIVERY OWNER
```

Esse desenho não diz que Assurance tem maior autoridade que o usuário. Significa que, quando a tarefa pede um claim de qualidade, o claim só é válido se atravessar as camadas de prova relevantes. O usuário pode aceitar um resultado abaixo do threshold, mas isso precisa ser `OVERRIDE` explícito com escopo, motivo, trade-off e revalidação; não vira `AAA_VERIFIED`.

## Regras normativas

- **Router não é Director:** o router produz uma proposta de composição; o Director resolve estratégia e ambiguidades.
- **Director não é builder:** pode definir acceptance e graph, mas não pode declarar evidência de execução.
- **Orchestrator não é requirement owner:** não cria lanes para justificar seu uso.
- **Specialist não é sistema inteiro:** output fora do scope é `ESCALATED`, não “best effort” silencioso.
- **Tool result não é quality result:** uma chamada bem-sucedida pode retornar dados errados, incompletos ou inadequados.
- **Verification não é crítica:** registra procedimento/result; não redefine o bar.
- **Reviewer não é executor:** crítica é read-only por default.
- **Assurance não é loop infinito:** usa stop conditions e orçamento.
- **Evals não são aprovação live:** regressão de cenário informa evolução; não substitui verification atual.
- **Human authority não é inferida:** ausência de actor/evidence mantém `PENDING` ou `UNKNOWN`.

## Quem decide routing

O Domain Router decide a composição mínima usando `TaskProfile`, registry, policy e usuário. Um Director pode refinar a rota após obter contexto adicional, desde que registre o motivo e mantenha a precedência de safety/risk. Invocação explícita do usuário de uma capability força consideração, não execução cega: o router verifica compatibilidade e pode retornar `BLOCKED` ou `CONDITIONAL` com explicação.

## Quem pode bloquear

Qualquer camada pode bloquear seu boundary quando há violação de segurança, permissão, contrato, dependência, evidência mínima ou stop condition. Bloqueio local não autoriza alterar o escopo para escapar. Policy Engine, Verification e Assurance podem bloquear delivery; só autoridade externa/humana autorizada pode aceitar risco material, ação irreversível ou mudança de arquitetura fora do escopo.

## Quem pode retry

O owner do failure pode propor retry. Orchestrator aplica retries de tarefa; Tool/Provider pode aplicar retry idempotente de transporte; Verification reroda procedimento após mudança/invalidacão; Gauntlet inicia nova rodada apenas com hipótese, progresso esperado e budget. Nenhum retry repete ação externa não idempotente sem estado autoritativo.

## Quem pode downgrade scope

Director pode propor uma rota degradada para preservar trabalho não afetado. O usuário ou autoridade designada decide downgrade que muda outcome material. Um downgrade nunca pode ser reportado como cumprimento integral do goal original.

## Quem aprova delivery

O Harness pode entregar um artefato local dentro da autorização existente. Para high/critical residual risk, produção, dados, credenciais, segurança sensível, financeiro, regulatório ou ação irreversível, a aprovação é humana e explícita. Um `PASS` técnico não equivale a `RELEASE_READY`.

## Conflitos

Quando dois documentos/capabilities discordarem:

1. preservar as duas observações;
2. verificar se uma é instrução, requisito, proposta ou evidência;
3. aplicar autoridade externa e safety;
4. usar o owner do contrato para decidir a interpretação local;
5. reabrir gate se a divergência mudar scope, risk, architecture ou acceptance;
6. registrar decision/supersession; nunca apagar a história.

## Relação com o estado observado

O audit encontrou duplicate `engineering-framework` em `.agents` e `.codex` e não teve host-load trace para provar precedência. Por isso esta arquitetura propõe `.agents` como policy canonical por documentação pública, preserva a cópia existente e exige validação controlada antes de qualquer mudança futura. Ver [`13-authority-model.md`](../skill-audit/reports/13-authority-model.md) e ADR-009.
