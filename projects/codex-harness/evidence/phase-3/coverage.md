# Verification and coverage

Fresh command:

```text
PYTHONPATH=src .venv/bin/coverage run --branch -m pytest -q -p no:cacheprovider
.venv/bin/coverage report --fail-under=80
```

Result: **290 passed**, 52.13 seconds, total combined statement/branch
coverage **82%** (`8,721` statements, `1,281` missed, `2,890` branches,
`698` partial). The run includes Phase 1/2 regression tests, Phase 3 unit and
integration tests, known-bad tests, eval fixtures and CLI/real-host smoke.

Focused adversarial checks also pass for traversal, absolute/NUL paths,
symlink escape, hardlink/case aliasing, depth/file/reference bounds, malformed
front matter, invalid UTF-8, unsafe activation text, native manifest rejection,
duplicate bytes, dependency cycles/version conflicts, loader containment and
host-loaded telemetry honesty.
