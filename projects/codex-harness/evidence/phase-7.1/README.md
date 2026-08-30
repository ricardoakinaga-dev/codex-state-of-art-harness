# Phase 7.1 — Branch Hardening Closeout

Status atual: `PASS_WITH_LIMITATIONS`; decisão de promoção:
`KEEP_CANDIDATE_NOT_PROMOTED`.

O input autoritativo é `evidence/phase-7/closeout-rerun-0009/`. Os closeouts
anteriores permanecem históricos. A superfície ficou congelada em
`P7_1_FEATURE_FREEZE`; não foram adicionados recursos, domínios ou arquitetura.

Resultados atuais:

- baseline: 65,5363% branches e 80,5504% linhas;
- final: 81,4120% branches e 89,1294% linhas;
- 1.283 testes passados, incluindo 720 testes específicos de hardening;
- piloto backend real: `PASS_WITH_LIMITATIONS`;
- builder real, repair limitado e verifier real em `real-rerun-final-2/`:
  `SUCCESS`, `SUCCESS`, `PASS_WITH_LIMITATIONS`;
- catálogo Phase 7: 48/48 cenários passados;
- Phase 2–7, Ruff, formato, mypy estrito e compilação: passados novamente.
- revisão independente exata: `FAIL`, `Critical=0`, `High=1`, `Medium=0`;
  `H-01` permanece material e bloqueia a promoção.

O pacote não reivindica produção, AAA, aprovação de segurança, release,
superioridade universal, causalidade ou cobertura exaustiva de todos os
failure paths. `pip-audit`, Bandit, Semgrep e Trivy não estão disponíveis neste
ambiente; isso permanece uma limitação explícita.

Arquivos JSON de cobertura e inventário são os artefatos brutos; os relatórios
Markdown explicam o vínculo entre cada gate, teste, estado observado e risco
residual.
