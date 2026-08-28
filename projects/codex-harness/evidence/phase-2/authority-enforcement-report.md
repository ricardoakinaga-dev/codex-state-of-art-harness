# Authority enforcement report

Authority é uma entrada explícita e caller-owned. O kernel nunca sintetiza um
grant: sem `AuthorityScope`, execução normal, dry-run e graph terminam com
`AUTHORITY_REQUIRED` antes de resolver ou chamar provider. A CLI e o benchmark
criam grants explícitos e limitados apenas na borda de seus adapters locais.
Antes do provider, o kernel verifica subject task/invocation/capability,
operation, scopes, decision `TRANSITION`, issued/expiry, conditions e
delegation. O snapshot efetivo é hashable e fica ligado à invocation.

Denied, expired, missing-scope, wrong-operation, condition-unmet,
delegation-missing e subject-mismatch são failures tipados e não resolvem
provider. Repair exige `REPLAN` e escopo próprio. Finalize/approve preservam
as regras de evidence e self-approval da Fase 1.

Os testes de authority e os cenários adversariais verificam expiry, operation,
scope, subject, authority required em direct/graph/dry-run, no-fallback e
ordem deny-before-execute. A prova executável está em
`test_phase2_kernel.py`, `test_phase2_execution_paths.py` e
`test_phase2_adversarial.py`.
