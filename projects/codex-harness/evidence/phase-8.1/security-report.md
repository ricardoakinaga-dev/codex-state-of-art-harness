# Security Report

Status: `BOUNDED_PASS_WITH_LIMITATIONS`.

Fresh artifact search found no `eval`, `new Function`, HTML injection sink, client secret/token storage, authorization header, open redirect assignment, or external target pattern. Dynamic content is constructed with `createElement`/`textContent`; URL filter values are allowlisted; the server confines static paths, bounds bodies to 64 KiB, validates species/urgency, requires idempotency keys, binds only `127.0.0.1`, and has no external dependency. This is not `SECURITY_APPROVED`.
