# Phase 7.1 final report

O baseline tinha 4.851/7.402 branches cobertos (65,5363%) e 15.659/19.440
linhas (80,5504%). O coverage final limpo tem 6.031/7.408 branches (81,4120%)
e 17.333/19.447 linhas (89,1294%), com 1.283 testes passados.

Foram adicionadas suítes de failure-path para boundaries backend/host, core,
persistence, Phase 4–7 e um residual crítico de ledger. Elas verificam estado,
efeitos, rollback, concorrência real no piloto, idempotência, migration,
authorization, retry/timeout/cancel, staleness e routing negativo.

Dois bugs reais foram corrigidos, sempre com teste associado:

1. `P7.1-BRANCH-1f3a3c37ff18`: digest de evidence inválido era normalizado
   somente no blocker, mas ainda alimentava um model estrito e levantava
   `ValueError`; agora o relatório falha fechado com digest zero.
2. `P7.1-BRANCH-7fa6c1dea2fb`: o suffix de timeout/output podia ultrapassar o
   limite de bytes após a truncagem inicial; agora a saída final é truncada
   novamente ao bound UTF-8.
3. `P7.1-BRANCH-9d0a9d7cb4b1`: os receipts do verifier usavam labels fixos do
   namespace histórico e o reparo não aceitava o defeito Ruff `SIM102` do
   arquivo alterado; os labels agora são relativos ao projeto atual e o repair
   bounded corrige somente Ruff em `app/service.py`/`tests/test_pilot.py`, com
   checks do verifier atualizados para esses paths exatos.

O builder real, repair bounded e verifier read-only da cadeia
`real-rerun-final-2/`, catálogo 48/48, piloto e regressões Phase 2–7 passaram.
Ruff, formato, mypy estrito e compilação
passaram. As ferramentas de auditoria de dependência/semgrep não estão
instaladas; por isso a segurança é `PASS_WITH_LIMITATIONS`.

O inventário ainda contém 1.377 arcos residuais sem cobertura, classificados e
revisados qualitativamente em `residual-branch-review.md`. A revisão
independente exata resultou em `FAIL`, com `0/1/0` findings
Critical/High/Medium, confirmou `H-01` e encerrou `H-02`/`M-01`. A decisão final
é `KEEP_CANDIDATE_NOT_PROMOTED`; nenhum ignore amplo ou claim de cobertura
exaustiva foi usado.
