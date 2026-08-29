# Phase 2 final closeout baseline

Recorded: `2026-08-28T19:47:46-03:00`

This snapshot was captured before any functional or evidence change in the
final Phase 2 closeout round.

## Repository state

- Repository root: `/home/ricardo/Área de trabalho/codex-state-of-art-harness`
- Project: `projects/codex-harness/`
- Branch: `main`
- HEAD: `9ef85e93c58fa5d8de92e604b9ecf057b3a50593`
- `git status --porcelain=v2 --untracked-files=all`: empty
- `git diff --stat`: empty
- `git diff --name-status`: empty
- `git diff --binary` byte count: `0`
- Submodule: `../../references/skill-audit` at recorded commit
  `527255bd221761ce35cb63001838b0cff6fc7a3f`, not initialized in this
  checkout; it is preserved and outside the Phase 2 write boundary.

## Initial fingerprints

Fingerprints were computed by sorting all regular files in each scope,
hashing each file with SHA-256, concatenating the `sha256sum` records, and
hashing that manifest. Python cache/build metadata was excluded.

| Scope | Files | SHA-256 |
| --- | ---: | --- |
| `src/` | 29 | `ff02a5f533fd6284cd8d3833f3632baa9be20995c8b6a4b93ce99539bf61070a` |
| `tests/` | 25 | `77bcfe63321896e4b3b2f815fc30d00048b537d3f284344f8e30d70a77bcef68` |
| `config/` | 1 | `1f4c1595be5e55619a5f2e26b220a67be097ca5dffc97c539900c794a12b99a6` |
| `.harness/config/` | 1 | `24bcb96d5a5830514d7c9e6df7b027e2a8d300b93ef0377d8d9e8be547ebe6c7` |
| `evidence/phase-2/` | 18 | `8937579b9d125387313ee797f8e956b461ed34f672664ce606469a99978f10c7` |
| `.agent/` | 17 | `92e6cd320b2c05d5acebcb9efe5102546207e6f3864d72cd53cf4d27cf1f1655` |
| `.gauntlet/` | 2 | `a0a6996bcf1793dea15ae52771ebe9921caba6a834ffb6a3537aece7a1a26f22` |
| `pyproject.toml` | 1 | `f339be89583fcb2ce07abf82235f75c8842e8753767e524646e47475a9e0ac89` |

The closeout target remains project-local. No global Codex/Skills configuration
or installed skill directory was inspected for mutation, and no external
write, deployment, push, or production action was authorized.

## Known starting condition

The project control state was `PHASE2-001 / VERIFY / PARTIAL` with a
`CONDITIONAL_PASS` readiness and `independent_review=NOT_RUN_BLOCKED`. The
previous local evidence claimed 187 tests, 84% coverage, passing Ruff/mypy/CLI,
benchmark and security checks, but those results are historical inputs only and
must be regenerated in this round.
