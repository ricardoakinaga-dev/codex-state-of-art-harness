# Scanner Report

- `ruff check src tests scripts`: PASS.
- `mypy src`: PASS (`65` source files).
- `uv pip check --python .venv/bin/python`: PASS (`13` packages compatible).
- `pip-audit`: unavailable in the environment; no substitute vulnerability database was asserted.
- `npm audit`: not applicable; no `package.json` exists in the project.
- `ruff format --check`: remains non-zero on pre-existing files outside the Phase 8.1 additions; those unrelated files were not reformatted.

The unavailable audit tool and pre-existing formatting drift are explicit limitations, not silent passes.
