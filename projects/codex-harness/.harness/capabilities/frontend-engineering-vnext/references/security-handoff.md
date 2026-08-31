# Security handoff

Frontend implementation must be safe by default but cannot self-approve
security. At boundaries validate and constrain user input; use native text
rendering instead of unsanitized HTML; allowlist local API routes; reject
external sinks, remote scripts, tracking pixels, credentials and secret-like
fixtures; and keep synthetic data in tests. Never log raw sensitive values.

Escalate to `security-review` when authentication, authorization, sensitive
or health data, user-generated HTML, uploads, payment, third-party scripts,
external network or cross-origin behavior is material. The handoff includes
the boundary, threat, validation, redaction, auth assumption, evidence,
unresolved questions and owner. A clean source scan is not a security
approval.

For a local pilot, the intended safe boundary is loopback-only deterministic
fixture data, no external requests, no secrets and no production state. The
browser network log and source audit must prove the declared boundary.
