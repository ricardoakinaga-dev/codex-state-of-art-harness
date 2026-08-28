# Authority enforcement report

Authority é uma entrada explícita; `authorize_decision(decision, None)` retorna
`AUTHORITY_REQUIRED` e nunca sintetiza grant. Antes do provider, o kernel
verifica subject task/invocation/capability, operation, scopes, decision
`TRANSITION`, issued/expiry, conditions e delegation. O snapshot efetivo é
hashable e fica ligado à invocation.

Denied, expired, missing-scope, wrong-operation, condition-unmet,
delegation-missing e subject-mismatch são failures tipados e não resolvem
provider. Repair exige `REPLAN` e escopo próprio. Finalize/approve preservam
as regras de evidence e self-approval da Fase 1.

Os testes de authority e os cenários adversariais verificam expiry, operation,
scope, subject, authority required, no-fallback e ordem deny-before-execute.
