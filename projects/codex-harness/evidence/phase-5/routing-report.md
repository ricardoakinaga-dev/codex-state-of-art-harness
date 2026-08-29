# Routing and eligibility

The pilot selected exactly one capability for the builder role:
`design-director@0.1.0`, `GLOBAL`, package fingerprint
`sha256:564d610da9260d25cbcddfbb3f96f70fb9dabd643c46b4242c4b891d399eba95`,
and manifest fingerprint
`sha256:402e36727b060eaf4ef740daf8ddfdcfce40cede7cb51ad48c14a582b9037c43`.
The package was inspected read-only, with 44 files, 29 references, 12 script
entries, and no dependencies. Its scripts were metadata-only and disabled.

The exact decision was `PASS` / `RESPONSE_ONLY_BUILDER`, not a general
execution grant. The authorization denied tools, scripts, shell, network,
MCP, providers, credentials, subagents, and host file changes. The host
boundary was bound to the project fixture and to the observed executable and
interpreter digests in the authorization evidence.

The preferred secondary `verification-loop@0.1.0` was inspected separately and
blocked as `EXTERNAL_VERIFIER_NOT_ELIGIBLE` because its metadata/load state was
invalid/rejected. Its exact package fingerprint is
`sha256:6cddd9e336f44c261eea24fc983c18f740df9dca8ebfbed0faffc7b9d73ba0ce` and
its observed manifest fingerprint is
`sha256:1ad02d474bf8f54eb48ea482bc2c628e6611be913a9b41de502241fe135c43f4`.
No fallback was labeled as that capability, so the support level remains A.

Primary evidence: `pilots/design-director/eligibility.json`,
`pilots/design-director/route-decision.json`,
`design-director-eligibility.json`, `verifier-eligibility.json`, and
`capability-fingerprints.json`.
