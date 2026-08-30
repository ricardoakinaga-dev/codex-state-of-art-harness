# Upstream analysis — `backend-patterns`

## Observed source

The authoritative upstream repository was inspected read-only at:

- repository: `https://github.com/affaan-m/ECC`
- branch: `main`
- observed revision: `d8e6a51755c6971a65eef73419076d449df0f490`
- path: `skills/backend-patterns/SKILL.md`
- digest: `sha256:9b983d0297a983110fdfda8dce55d19b750ca3e53ef155d75a3eff740d3874b8`
- size: 13,349 bytes, 562 lines, 1,613 words

The source was obtained with a shallow sparse read-only clone and the revision
was resolved by `git ls-remote`. The prior audit also records the installed
lineage commit `8bdf88e5ad8877bcd00a4aba7ccbfb50f235f10f`, Ricardo fork head
`1e8c7e7994223e0ff337d1626cd08e04a1ae67ed`, and an earlier upstream
observation. The current observation supersedes the earlier revision for this
Phase 7 packet; no upstream bytes are merged into the project.

## Difference summary

The upstream file differs materially from the installed legacy body (the prior
raw comparison recorded 60 changed lines). It remains a prose Skill without a
native manifest, typed contracts, evidence ledger, bounded stop conditions,
deterministic evals or a Codex-native Phase 3/4 execution policy. The upstream
body is therefore useful lineage and comparison input, not an execution source.

The upstream revision is treated as a current snapshot, not as a quality
endorsement. Any exact line-level comparison beyond the frozen hashes is
reported only where directly inspected. No automatic merge or package update is
performed.

## Modernization implications

- Retain useful API/data/reliability vocabulary, but convert material claims
  into contracts and evidence rather than copying prose.
- Preserve the upstream/current distinction in the benchmark so vNext is not
  compared to a straw man.
- Add package identity, role ownership, security handoff, migration safety,
  stop conditions and verification composition that neither prose package
  provides.
- Keep ecosystem decisions adaptive; the existing Harness Python environment
  does not justify adding FastAPI/SQLAlchemy solely for this pilot.

Unknowns retained: upstream history between the installed import and the
observed revision is not reconstructed; no signed release provenance is
claimed; upstream runtime behavior is not executed; and no causal quality
comparison is inferred from line or word counts.
