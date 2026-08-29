# Verification and coverage

Fresh command:

```text
PYTHONPATH=src .venv/bin/coverage run --branch -m pytest -q -p no:cacheprovider
.venv/bin/coverage report --fail-under=80
```

Result: **316 passed**, 86.62 seconds, total combined statement/branch
coverage **82%** (`9,059` statements, `1,328` missed, `3,024` branches,
`718` partial). The run includes Phase 1/2 regression tests, Phase 3 unit and
integration tests, known-bad tests, eval fixtures and CLI/real-host smoke.

Focused adversarial checks also pass for traversal, absolute/NUL paths,
symlink escape, hardlink/case aliasing, depth/file/reference bounds, malformed
front matter, invalid UTF-8, unsafe activation text, native manifest rejection,
duplicate bytes, dependency cycles/version conflicts, loader containment and
host-loaded telemetry honesty.
