# Residual branch review

Este arquivo revisa os 1.377 branches ausentes enumerados individualmente em
`branch-inventory.json`; cada item tem ID determinístico, arquivo, função,
linha, target, categoria e risco. Não há exclusões.

| Grupo residual | Quantidade | Razão observada | Decisão |
| --- | ---: | --- | --- |
| high-value guards compostos | 509 | Combinações de validação já cobertas por equivalentes tipados; alguns arcos exigem falsificação múltipla | Manter no inventário; sem claim de exaustividade |
| medium parser/validation | 203 | Entradas defensivas raras e combinações de shape | Não bloquear o piloto; próximo ciclo pode ampliar |
| low defensive/platform | 665 | cleanup, fallback, platform capability e ramos de apresentação | Não excluir; sem mudança de produção |

Os branches críticos de ledger, replay, migração, rollback e integridade foram
fechados pela suíte `test_phase71_critical_residuals.py` e pelo piloto. Os
resíduos de host/authentication, filesystem race e caminhos internos compostos
continuam como limitação qualitativa: o pacote não diz que todo failure path
do kernel foi testado exaustivamente. Se a política exigir cobertura de cada
arco residual como condição de promoção, a decisão correta é manter o
candidato não promovido e abrir novo ciclo, não reduzir a métrica.
