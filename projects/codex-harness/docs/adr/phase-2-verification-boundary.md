# ADR P2-004 — Verification, critique e assurance separados

## Decisão

Provider execution só produz output estruturado. Verification aplica
procedures determinísticas e liga claims a evidence fresca. Critique recebe um
blind packet com digest e verifica lacunas. Assurance transforma verification +
critique + quality bar em `QUALITY_ACCEPTED`, `REPAIR_REQUIRED`, `BLOCKED` ou
`FAILED`. Nenhuma dessas decisões é inferida de `provider status=success`.

## Consequências

O fixture reviewer determinístico é suficiente para o kernel local e é marcado
como `SEPARATED_SELF`; revisão independente do artefato integrado permanece
obrigatória para o veredito da fase.
