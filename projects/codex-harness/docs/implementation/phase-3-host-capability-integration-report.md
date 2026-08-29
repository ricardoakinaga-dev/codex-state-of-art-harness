# Phase 3 host capability integration report

## Scope and decision

Phase 3 adds a bounded, read-only bridge from the frozen Phase 2 local kernel
to the local Codex capability layout. It discovers known roots, parses only
declarative metadata, synthesizes observed manifests, evaluates trust and
compatibility, resolves duplicates/dependencies, prepares progressive load
plans, and bridges selected metadata into the existing registry/router.

It does not install or modify Skills, execute scripts/providers/MCP/shell,
perform network or credential access, import package code, or claim that a
discovered package is host-loaded. The independent-review, readiness and gate
records are the controlling status artifacts; this report describes the
implementation and its evidence boundary.

## Architecture rebaseline and modules

The Phase 2 kernel remains frozen and is extended additively under the
project-local `src/harness_kernel/phase3_*` modules:

| Boundary | Implementation contract |
| --- | --- |
| Host adapter | `HostAdapter` protocol and `CodexHostAdapter` expose typed, read-only inspection, root discovery, inventory and load-observation methods. |
| Host model | Immutable `HostSnapshot` includes identity/version/time, roots, project/workspace refs, counts, tool/provider metadata, limitations, fingerprint and official-behavior labels. |
| Path safety | `phase3_paths` validates absolute/NUL-free roots, canonical aliases, descriptor-relative package paths, symlinks, loops and bounded depth/count/bytes. |
| Discovery | `CapabilityDiscovery` inventories `SKILL.md`, native manifests, agents metadata, refs, scripts, evals, benchmarks, rubrics, templates, examples and assets. |
| Parser/synthesis | `phase3_parser` fails closed on malformed structured front matter; discovery distinguishes native, synthesized, legacy and invalid records and retains unknown fields. |
| Loader | `SafeCapabilityLoader` exposes L0 identity, L1 routing, L2 instruction, L3 selected refs and L4 approved declarative metadata. Scripts/providers/MCP remain disabled metadata. |
| Trust/resolution | Trust, provenance, compatibility, staleness, SemVer, precedence, duplicate divergence, dependency cycles and bounded resolution are explicit. |
| Integration | `Phase3RouterBridge` converts selected observed metadata into the existing immutable registry and pure `minimum_route()`, with bounded iterables. |
| Observability/CLI | Immutable lifecycle telemetry, sanitized public serializers, `host` commands and `capabilities` aliases expose inspection and `--explain` without writes. |

## Official behavior and epistemic boundary

The adapter records the evidence class instead of collapsing documentation,
inference and absence into one status:

| Behavior | Status | Basis |
| --- | --- | --- |
| Skill discovery roots and metadata-first loading | `VERIFIED_OFFICIAL` | Current OpenAI Skill documentation: [Build Skills](https://learn.chatgpt.com/docs/build-skills). |
| Optional `agents/openai.yaml` interface metadata | `VERIFIED_OFFICIAL` | The same official Skill documentation. |
| AGENTS project/user discovery chain | `VERIFIED_OFFICIAL` | Current [AGENTS.md configuration documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md). |
| Ancestor project roots and symlinked Skill-folder semantics | `VERIFIED_OFFICIAL` for the documented host behavior | The current official Skill documentation describes these behaviors; this adapter records them without pretending to implement unsafe aliases. |
| Legacy `.codex/skills` compatibility root | `INFERRED` | Observed local layout and compatibility need; not promoted to official semantics. |
| Adapter ancestor traversal, adapter symlink policy, host-load causality, runtime version and provider/tool execution | `UNSUPPORTED_BY_HOST`, `INFERRED` or `UNKNOWN` | The adapter inspects the explicit project root, rejects symlink roots under its safety policy, and has no public read-only runtime signal; no fake load claim is emitted. |

The same labels are present in `HostSnapshot.official_behavior` and the
sanitized host inspection artifact. A package's own `origin` or author claim
cannot promote it to official trust.

## Discovery, inventory and safety

Every capability record retains its installed package path (redacted in public
evidence), root/scope, `SKILL.md` and native manifest paths, package files and
hashes, category surfaces, lifecycle, kind, provenance, compatibility, trust,
load eligibility and normalized manifest. Scripts/assets are not loaded as
instructions. Non-sensitive metadata-only bytes are hashed with a bounded read
without retaining content; sensitive paths remain `UNAVAILABLE` by policy.

Front matter and JSON parsing reject duplicate keys, invalid encodings,
structured/aliased values outside the supported scalar/list contract,
non-finite values, excessive nesting and oversized input. Unknown structures
remain visible as `UNKNOWN`. Synthesized fields are labeled `DECLARED`,
`DERIVED`, `INFERRED` or `UNKNOWN`; a synthesized record is never labeled as a
native manifest.

## Loader, trust, compatibility and resolution

The loader only prepares bounded context. L0/L1 do not prepare instructions;
L2 reads a bounded UTF-8 instruction kernel; L3 reads selected in-package
references; L4 returns approved package metadata and script descriptors with
`execution=DISABLED_PHASE3`. Reference paths are normalized, contained and
bounded by count, bytes and depth. Host load is always `UNAVAILABLE` in this
adapter.

Trust derives from root scope, rejection state and observed evidence. Platform
requirements remain compatibility assessments with explicit portability debt.
Expected inventory fingerprints mark records stale before selection. Duplicate
resolution distinguishes same bytes, divergent same-ID/version bytes, multiple
versions, aliases and forks. A divergent version blocks that version, while a
clean compatible version remains resolvable; dependencies are depth-bounded and
cycles/conflicts fail closed. Project-local roots have higher precedence than
workspace/shared/global/system roots, but precedence never overrides divergent
bytes for the affected version.

## Routing and telemetry

Only selected, eligible records cross the Phase 2 registry boundary. The bridge
does not execute a provider or change Phase 2 routing semantics. Telemetry keeps
`DISCOVERED`, `SELECTED`, `LOAD_PLANNED`, `CONTEXT_PREPARED`, `HOST_LOADED` and
`EXECUTED` distinct; host-loaded/executed events require an `OBSERVED` signal.
The current host has no such signal, so telemetry records zero host-loaded or
executed events. Paths and sensitive key values are redacted before telemetry
serialization.

## Verification and evidence

The exact artifact set is listed in `evidence/phase-3/README.md`. It includes
the sanitized real inventory, host/duplicate/compatibility/trust/loader/router/
telemetry reports, security and coverage reports, a reproducible `P3-BENCH-1`
runner with a feasible 100-capability scenario, the independent review and
readiness gate. The committed fixture catalog is
`tests/fixtures/phase3/scenarios.json`; real-host smoke exercises installed
`design-director`, `engineering-framework` and ECC cross-agent records when
present and reports absence instead of simulating them.

The current verification numbers and tool availability are recorded in
`evidence/phase-3/coverage-report.md`, `security-summary.md` and
`readiness.json`; `pip-audit` is explicitly unavailable when it cannot run.
The Phase 2 full regression remains a blocking acceptance criterion and is
reported separately from the Phase 3 additions.

## ADRs, limitations and deferred work

The roadmap rebaseline is recorded in
`../../../../architecture/docs/adr/ADR-012-phase-roadmap-rebaseline-after-phase-2.md`;
`evidence/phase-3/phase2-supersession.md` records why the Phase 2 packet remains
immutable. Deferred work includes real host-load causality, provider/tool/MCP
runtime integration, installation/mutation, shell/network/credential access,
subagent orchestration, production SLOs and causal-quality/`AAA_VERIFIED`
claims. Any such change requires a new scope decision, evidence manifest and
independent review.
