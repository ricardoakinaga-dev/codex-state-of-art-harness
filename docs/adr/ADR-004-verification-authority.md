# ADR-004 — Verification relata fatos; assurance decide qualidade

**Status:** `PROPOSED` · **Data:** 2026-08-28 · **Escopo:** prova e autoridade

## Contexto

Um `PASS` de teste, review ou modelo não cobre automaticamente segurança, UX, completude ou requisitos não executados. Misturar essas camadas produz claims fortes sem evidence.

## Decisão

Verification é autoritativa sobre procedimentos e observações. Reviewer critica contra um bar congelado. Assurance agrega gates, risco residual e stop/continue. Nenhuma camada apaga `NOT_RUN`, `UNKNOWN`, limitation ou dissent; release/commit continua sujeito à autoridade externa apropriada.

## Alternativas consideradas

- Um score único: esconde blockers críticos.
- Builder aprovar seu próprio output: reduz independência.
- Reviewer substituir testes: opinião não é execução.

## Consequências

Reports ficam mais explícitos e podem parecer menos “limpos”, mas se tornam auditáveis e reprodutíveis. AAA exige evidence por gate.

## Evidência

`docs/13-verification-system.md`, `docs/14-assurance-system.md`, `docs/22-aaa-definition.md`, `docs/contracts/VerificationReport.json.md`.

## Revalidação

Aplicar known-bad evals com claims deliberadamente não executados e confirmar que o sistema bloqueia completion/AAA.
