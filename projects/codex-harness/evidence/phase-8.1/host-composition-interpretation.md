# Host Composition Interpretation

The fresh probe confirms a usable, supported Codex app-server boundary:
`initialize`, `skills/list` and experimental `thread/start` are documented and
responded successfully under a read-only ephemeral session. The generated
current schema also documents `turn/start`, `skills/changed` and the
`workspace-write` sandbox enum.

The fresh controlled-real handshakes complete with exact frontend and verifier
fingerprints, but they do not provide the missing causal link. The public
protocol does not list a `skill/loaded` or `skill/load/completed` notification,
and the host's `skills/list` response does not directly expose the project-local
`.harness/capabilities` package. Phase 8.1 stages exact copies into
`.agents/skills` and records the host response as limited transport evidence;
discovery, thread creation, transport success and a model response are not
equivalent to an observable load event or artifact causality.

Accordingly, full official host composition remains unproven. The packet's
alternative proof is the post-handshake composition bridge: it validates the
host receipt and exact package identity, creates only a byte-identical copy of
the already-built artifact, rechecks source/artifact digests and changed paths,
then serves that copy to the browser. The bridge reports zero capability/global
mutation and no external/manual producer. It is eligible only as a limited,
independently-reviewed harness causal chain; it is not full host causality and
does not prove production or release readiness.
