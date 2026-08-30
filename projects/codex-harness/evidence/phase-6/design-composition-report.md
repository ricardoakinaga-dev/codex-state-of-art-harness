# Real Design Director → vNext Composition

Result: `PASS_WITH_LIMITATIONS` at `P6_LEVEL_B`.

The real Design Director builder produced artifact `ART-P5-V1`
(`sha256:b9dd46c839b3fe03b47439ddc68dee914f2dd25fa54e966408835dfb75bc03bc`), followed by a project-local native vNext discovery,
controlled-real preflight and app-server invocation. The deterministic report
passed `17/17` required criteria and bound the
browser capture manifest to the same source digest, task, run and criteria.

The verifier deliberately deferred `12` qualitative dimensions
to an independent reviewer and did not treat its own report as visual approval.
Host load causality is `HOST_LOAD_UNOBSERVABLE`; that is a limitation, not a
success claim.
