# Context-cost report

The measured comparison is byte-oriented and records what was actually
available. It does not treat a larger prompt as a quality advantage.

| Surface | Measurement | Interpretation |
| --- | ---: | --- |
| installed current `SKILL.md` | 13,837 bytes | forensic snapshot only |
| upstream `SKILL.md` | 13,349 bytes | read-only upstream snapshot only |
| vNext `SKILL.md` | 10,342 bytes | high-signal router/workflow |
| backend vNext loaded instruction kernel | 10,342 bytes | actual Phase 3 bounded load used by builder host adapter |
| verification-loop-vNext loaded instruction kernel | 4,652 bytes | actual Phase 3 bounded load used by final verifier host adapter |
| vNext selected-reference budget | 65,536 bytes | package bound, not consumed total |
| vNext host context budget | 16,384 bytes | package bound |
| real verifier total prompt | unavailable | host does not expose a trustworthy byte counter |
| critic context | not run as a pre-repair stage | strict Level C not claimed |

The host adapter passes the Phase 3-loaded kernel as host-managed text because
the official app-server `skills/list` did not expose the project-local package
as a native installed skill. This preserves project-local scope and records the
load as unobservable rather than inferring it from the request.
