# Capability discovery report

The real local scan produced 43 sanitized capability records across 5 bounded
roots. The canonical detailed record set is
`real-capability-inventory.json`; `real-inventory.json` is retained as the
legacy summary artifact.

| Kind/status | Count |
| --- | ---: |
| `SYNTHESIZED` | 37 |
| `NATIVE` | 1 |
| `INVALID`/rejected | 5 |
| inspected lifecycle records | 38 |

The inventory preserves `SKILL.md`, native manifest, `agents/openai.yaml`,
references, scripts, evals, benchmarks, rubrics, templates, examples and
assets when observed. Every record includes scope, provenance, content hash,
compatibility, trust, load eligibility and field provenance. Unknown metadata
is visible as `UNKNOWN`; synthesized fields are not represented as native.
Scripts/assets and sensitive files are metadata-only. Non-sensitive
metadata-only bytes receive bounded digests without content retention.
