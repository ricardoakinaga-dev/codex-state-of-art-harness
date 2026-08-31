# Upstream frontend-patterns analysis

## Provenance

The local forensic audit captured the upstream document from
`https://raw.githubusercontent.com/affaan-m/ECC/main/skills/frontend-patterns/SKILL.md`
on 2026-08-28. The captured bytes are 15,432 bytes and 657 lines with SHA-256
`a5b971eb9e74cd763c7e3308bfd888e0d9cf69f8b88477659889d77182479740`.
The local provenance packet does not contain a commit/revision, so the
upstream revision is explicitly `UNKNOWN`, not inferred from the URL or date.

The captured Ricardo fork source is also retained locally at
`references/skill-audit/data/provenance-evidence/raw/frontend_patterns__ricardo_fork_current.md`
with SHA-256
`8e7d5c8c5ed9d24bfcc0b2587738ab9015932472ad4a2cbc9cd3d5862fc6eaa7`.
It differs from both the installed bytes and the upstream capture. The
installed file currently contains the ECC origin field but not the captured
fork's privacy/data-boundary section; this is an observed byte difference, not
a judgment about the intent of either source.

## Key differences versus installed current

- Upstream has a more specific activation description mentioning React and
  Next.js components/state/render performance.
- Upstream's fetch example contains a note about keeping the latest fetcher
  and options in refs; the installed file does not contain that captured note.
- The current installed file has an `origin: ECC` frontmatter field; the
  captured upstream has `metadata: origin: ECC`.
- The upstream capture does not supply native package identity, typed inputs or
  outputs, evidence lineage, browser/render gates, security boundaries or
  stop conditions.

## Relevance and limitation

The upstream snapshot is a source comparison input, not a live update claim.
No upstream code was copied wholesale. The vNext package extracts domain
responsibilities and adds project-native contracts while retaining explicit
provenance and compatibility debt.
