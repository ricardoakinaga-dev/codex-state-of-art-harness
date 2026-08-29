# Compatibility report

The canonical machine-readable assessment is `compatibility-report.json`.
The real scan observed one project-local native record as `COMPATIBLE` and the
remaining eligible synthesized/local records as `PARTIAL` with explicit
portability debt. Missing host capabilities remain `UNKNOWN`/`UNAVAILABLE`;
they are never upgraded to compatibility merely because a package was found.

Records assessed as incompatible are marked `BLOCKED_INCOMPATIBLE_HOST` and
cannot enter resolution or the router bridge. Compatibility evidence includes
required features, missing features, platform limits, reasons and portability
debt.
