# Phase 7 modernization plan

The current package is retained as a read-only baseline. The project-local
candidate will be a compact router plus detailed references, immutable native
manifest, deterministic metadata procedures, quality profiles, evals,
benchmark fixtures and composition contracts.

The primary task profile is `BACKEND_FEATURE` with `EXPERIMENT` and `MIGRATION`
overlays. The overlays add evaluation and schema-safety controls; they do not
expand the requested pilot into a general migration program.

The implementation sequence is:

1. Freeze evidence and entry gate.
2. Write RED contract/security/eval tests.
3. Build the package and contract validator.
4. Build the isolated Veterinary Appointment API and tests.
5. Discover/load the package via Phase 3 and approve exact bytes via Phase 4.
6. Invoke the real builder in a disposable workspace-write sandbox.
7. Run migration/static/tests and record v1 artifacts.
8. Invoke read-only verification-loop-vNext with all immutable handoffs.
9. Obtain independent capability and pilot/security criticism.
10. Repair at most once, then rerun all affected tests and fresh verification.
11. Regress Phases 2–6, scan security/dependencies, benchmark and review.
12. Recompute exact manifest/closure and issue only the supported promotion.

The pilot must remain dependency-free beyond Python's standard library because
the existing Harness environment has no FastAPI/SQLAlchemy runtime dependency.
Introducing a framework only for this benchmark would measure dependency setup,
not backend modernization value.
