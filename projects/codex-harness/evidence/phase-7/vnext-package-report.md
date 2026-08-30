# backend-engineering-vNext package report

Status: package contract `PASS`; external promotion target
`VERIFIED_CANDIDATE` within the bounded Phase 7 scope, subject to the final
exact-packet review. The manifest intentionally remains `CANDIDATE` with
`quality.last_result=NOT_RUN`; promotion is an external evidence decision so
the package does not self-promote or mutate its own identity.

## Identity and compatibility

- package: `.harness/capabilities/backend-engineering-vnext/`
- capability: `backend-engineering-vnext`
- version: `0.1.0`
- type/role: `SPECIALIST` / `SPECIALIST`
- package fingerprint: `sha256:560d801467b48cdd1ea655c744bb31bd881ab77db1cb9d445572f0ad60a1fa0d`
- manifest digest: `sha256:f9205535b0d06540a65d936b318d6066ad760ed5b432e4681e98bfdf9a49f865`
- source baseline digest: `sha256:2e5efd41b7c89432bdd31cebea429dbc6c49a743a558b33040f55be7f7cde165`
- execution model: metadata-only package; external execution is denied
- host compatibility: Phase 3 native manifest/discovery, bounded loader, Phase 4
  exact-byte preflight, and bounded project workspace

The package has 17 files: one router, one manifest, six metadata/control JSON
files, seven references, and one deterministic-procedure file. The exact file
digests are bound in `review-manifest.json`; the most important payload digests
are:

| File | SHA-256 | Bytes |
| --- | --- | ---: |
| `SKILL.md` | `sha256:efe0df26ca2f882b964fffb6f88c0b42483a4f9312e27ca44a5e4f5ce2acee45` | 10,342 |
| `manifest.json` | `sha256:f9205535b0d06540a65d936b318d6066ad760ed5b432e4681e98bfdf9a49f865` | measured in manifest |
| `evals/scenarios.json` | `sha256:196c9e46a95c1fd1a21c4009557a3cbd86e705e0784a016741044f7d500d57a6` | measured in manifest |
| `benchmarks/benchmark-fixtures.json` | `sha256:2e518e5d4b82b9222023486afa5b1d55deee80ca72ebd2d1a7574ca6df25004a` | measured in manifest |

## Surface

The candidate declares typed input/output concepts, bounded architecture/API/
data/migration/reliability/security handoffs, explicit stop conditions,
separated specialist/verifier/reviewer ownership, a maximum of one repair, and
fresh final verification after a repair. It declares no tools, providers,
credentials, shell, network, MCP, or package-write authority.

The package is deliberately smaller in `SKILL.md` than the inspected current
and upstream bodies; detailed knowledge is kept in references. This is a
design choice, not evidence that shorter instructions are universally better.

## Validation

`validate_backend_package` with an exact expected fingerprint returned `ok=true`,
with no blockers, 17 files, 48 eval scenarios, and 4 benchmark records. The
validator now rejects an unpinned package validation, validates package
metadata/composition/profiles/budgets/procedure boundaries and all declared eval
and benchmark fields, and the separate `validate_backend_evidence_binding`
requires pinned task/package/artifact/criteria/authority identity plus a bounded
freshness window. It rejects stale, future, mismatched or self-approved
handoffs. Duplicate JSON keys, non-finite JSON, traversal, symlinks, size
limits, package overlap, and manifest/fingerprint drift are rejected by the
Harness contract tests.

Promotion remains candidate-only until the current eval/benchmark packet,
independent review, and exact closeout are bound. Claims explicitly excluded:
host-loaded, production-ready, causal improvement, universal superiority,
security approval, release approval, and AAA quality.
