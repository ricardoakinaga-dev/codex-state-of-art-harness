# Eligibility report

The route resolved exactly one installed builder: `design-director@0.1.0`,
scope `GLOBAL`, with package fingerprint
`sha256:564d610da9260d25cbcddfbb3f96f70fb9dabd643c46b4242c4b891d399eba95`
and manifest fingerprint
`sha256:402e36727b060eaf4ef740daf8ddfdcfce40cede7cb51ad48c14a582b9037c43`.
The package was inspected read-only; its files, references, scripts and
dependencies were recorded before the route was authorized.

Eligibility is narrow: `PASS` / `RESPONSE_ONLY_BUILDER` with artifact output
limited to the project fixture. Tools, scripts, shell, network, MCP,
providers, credentials, subagents and host-file changes remain denied.

The requested `verification-loop@0.1.0` secondary is explicitly blocked as
`EXTERNAL_VERIFIER_NOT_ELIGIBLE` with package fingerprint
`sha256:6cddd9e336f44c261eea24fc983c18f740df9dca8ebfbed0faffc7b9d73ba0ce`.
No fallback is presented as that capability; the pilot therefore supports
Level A only.
