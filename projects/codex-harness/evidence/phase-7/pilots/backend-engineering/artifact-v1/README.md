# Artifact v1

Artifact v1 is invalidated historical builder output. The real host reported a
change in `app/validation.py`, but source inspection found that the predicate
changed was not the requested identifier guard and the generic acceptance path
was not automatically evaluated. The host response is retained at
`pilots/backend-appointment-api/.harness/phase4/artifacts/INV-fdb34810e7965d93adafcd61.host-response.txt`.

No v1 verification or PASS claim is made. A bounded repair produced v2, which
requires fresh tests and fresh read-only verification.
