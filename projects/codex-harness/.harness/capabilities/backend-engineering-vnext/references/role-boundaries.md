Load when: a request combines implementation with API design, testing, security, verification, review, assurance, orchestration, or release authority.

`backend-engineering-vnext` owns backend implementation within the frozen
handoff. `api-design` may specify or review the public contract. A TDD
workflow may shape tests when selected. `security-review` owns final security
assurance when a trigger is material. `verification-loop-vnext` owns current,
read-only factual verification. An independent reviewer critiques the exact
artifact without builder rationale. Assurance decides whether risk permits a
next state; release authority decides delivery.

Do not give two roles ownership of the same decision. The specialist may
self-check its diff and evidence, but that is not independent review. It may
report a security trigger, but it cannot approve security. It may prepare a
verifier handoff, but it cannot declare factual verification complete. It may
request a bounded repair, but it cannot use a verifier or reviewer as a
mutator.

If an adjacent role is unavailable, preserve the missing evidence and choose a
safe narrower status. Missing optional review is a limitation; missing
required security, authority, artifact, or verifier evidence is a block. Scope
expansion, role collision, or a request to bypass a denied boundary is a typed
stop rather than a new composition edge.
