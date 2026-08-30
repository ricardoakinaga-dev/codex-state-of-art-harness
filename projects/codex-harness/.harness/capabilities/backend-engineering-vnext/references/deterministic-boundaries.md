Load when: a package contract, procedure allowlist, path boundary, budget, or evidence identity must be checked without executing package content.

The package procedures are metadata only. Select a declared procedure by
stable ID, intersect its inputs with the authorized project-local metadata,
and return a typed observation. Do not infer execution from a plan, a
description, or a missing observer. Each procedure has one attempt; the run
has bounded procedure count, references, context, evidence records, report
size, and duration.

Bind package fingerprint, manifest digest, task identity, artifact/diff
identity, criteria digest, and evidence digest before a result can support a
claim. Reject changed, stale, missing, aliased, traversing, or unapproved
references. An artifact substitution or criteria change invalidates dependent
results and requires a fresh observation.

The package has no tools, providers, executable scripts, network, shell, MCP,
credential, secret, subagent, or interpolation surface. Workspace writes are
host policy, not package permission. A host may grant a bounded pilot root
after exact-byte preflight; package files and control-plane files remain
outside that grant. A builder host can optionally expose fixed dynamic
list/read/write operations and a fixed test observer, but those are host
capabilities rather than package tools and cannot accept arbitrary commands,
providers, paths outside the declared roots, or widened permissions.

Deterministic metadata can prove shape, identity, field presence, allowed
values, path confinement, and counters. It cannot prove that a test is
adequate, an architecture is wise, a security risk is acceptable, or a
production outcome follows from a fixture.
