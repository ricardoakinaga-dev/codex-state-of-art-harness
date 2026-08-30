# Verification Loop Upstream and Provenance Analysis

This is a read-only comparison captured on 2026-08-29. Remote refs and raw
files were fetched with `git ls-remote`/`curl`; no repository or package was
modified. Online availability is not treated as proof of trust.

## Observed references

| Source | URL | Ref observed | File | Raw SHA-256 |
| --- | --- | --- | --- | --- |
| ECC upstream | `https://github.com/affaan-m/ECC.git` | `d8e6a51755c6971a65eef73419076d449df0f490` (`main`) | `skills/verification-loop/SKILL.md` | `sha256:f0d56107f79e607d4de6c5543b8edfb1b58ab9ae4019b39831689cd91116543e` |
| Ricardo fork | `https://github.com/ricardoakinaga-dev/everything-claude-code.git` | `1e8c7e7994223e0ff337d1626cd08e04a1ae67ed` (`main`) | `.agents/skills/verification-loop/SKILL.md` | `sha256:abe40a95fc1fe7d5ff47ed2bab27600f160871e487fb1698546b0c80e45b1fbb` |
| Installed current | local filesystem | audit source commit `8bdf88e5ad8877bcd00a4aba7ccbfb50f235f10f` | `.agents/skills/verification-loop/SKILL.md` | physical file `sha256:01a9ae310ad4426bb05660dda6cefdeaac9513417585c09c8bb1b94738649a78` |

The installed package also has `agents/openai.yaml` with physical hash
`sha256:1907fd04fea5c83d15faf14acfc978de90076d4351341cf9259639aa0c3b7bd3`.
The local lineage audit explicitly notes that its clone is shallow and no
import tag is proven.

## Differences relevant to modernization

- The current installed and fork snapshots are Claude-oriented and largely
  prose-driven; the upstream snapshot adds metadata such as a license and
  uses the same shell-centric verification phases.
- None of the observed snapshots supplies the native Harness manifest,
  criterion-level Claim/Procedure/Evidence/Status model, typed freshness,
  role ownership, deterministic tool boundary or project-local Phase 3/4
  execution receipt required by P6-QB-1.
- The upstream and fork files are useful provenance/reference inputs only. A
  newer remote revision does not establish compatibility, safety or
  promotion eligibility.

## Reusable and non-reusable material

Reusable ideas: staged verification, type/lint/test/security/diff categories,
coverage reporting and a final concise report. Non-reusable assumptions:
Claude session identity, implicit shell commands, package-manager choice,
unbounded host environment, `grep`-based security proof and the idea that
running a command is sufficient evidence without artifact identity/freshness.

## Limitations

The raw endpoints and refs were reachable during this snapshot, but a complete
historical commit audit, signed provenance chain, license acceptance and
causal host-load trace remain unproven. The vNext candidate therefore records
the current/fork/upstream references explicitly and remains a project-local
candidate until independent review and benchmark gates pass.
