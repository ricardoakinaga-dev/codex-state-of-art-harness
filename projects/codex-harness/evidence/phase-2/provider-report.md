# Provider report

O protocolo `CapabilityProvider` recebe `CapabilityInvocation` e retorna
`ProviderExecutionResult`. O registry é immutable e cada descriptor declara
ID, versão, capabilities, operations, origin, mode, limits,
security-characteristics e cancellation support.

Admission Phase 2 exige origin `PROJECT`, `local_only`, execution mode
`FIXTURE`/`DETERMINISTIC_FIXTURE` e as características project-local,
non-networked, non-shell e non-privileged. Availability é separada de
registration e seleção. `resolve` exige provider ID, operation e capability
compatíveis; não há fallback.

Fixtures registradas: success, failure, retry, partial e repair. Resultados
validam provider/invocation correlation, output digest, typed failure, attempt,
refs e status. Os testes cobrem provider unavailable, mismatch, digest forged,
retry bounded e provider partial/failure.
