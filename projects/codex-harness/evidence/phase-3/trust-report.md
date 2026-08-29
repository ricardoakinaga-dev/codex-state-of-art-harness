# Trust and provenance report

The canonical machine-readable assessment is `trust-report.json`. The real
scan classified 1 project-local record as `PROJECT_TRUSTED`, 37 global/local
synthesized records as `THIRD_PARTY`, and 5 rejected records as `REJECTED`.
These labels derive from observed scope, lifecycle, source and validation
evidence; repository ownership or an in-package `origin` claim is not proof of
authorship or safety.

Each record retains root/scope, source refs, source repository root ID, upstream
and fork claims when declared, tag/commit/license when observable, local
modification state, package hash and inspection time. Unknown provenance stays
`UNKNOWN`.
