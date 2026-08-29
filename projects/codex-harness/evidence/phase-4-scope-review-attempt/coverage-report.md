# Coverage report

Fresh full verification: `354 passed`; combined branch coverage: `80%`.

Command: `.venv/bin/coverage erase && PYTHONPATH=src .venv/bin/coverage run --branch -m pytest -q -p no:cacheprovider && .venv/bin/coverage report -m`.
