# Fresh Independent Capability and Evidentiary Review

Reviewer: `/root/phase81_capability_review` (read-only, no implementation role)

Reviewed chain: `P81-COMPOSE-013` → `P81-BROWSER-018` → `P81-VERIFY-010`

Verdict: `PASS_WITH_LIMITATIONS`

## Blockers

- Critical: none.
- High: none.
- Medium: none.

The prior runtime-ID laundering, raw-write lineage, verifier-independence, reflow and idempotency defects are materially corrected. Raw frontend events contain five path-bearing writes at sequences 167, 173, 183, 193 and 203 and cover exactly the independently measured four-file delta. Source, build, artifact, browser and verifier identities agree on `sha256:e3306ed2bdf13317f7486af6e61b0e4182abbc25d3d9e0fdfdb3dd8c4519643a`.

Browser evidence has 44 passing checks: exactly 33 unique direct `P8-EVAL-*` IDs and 11 supplemental checks. All 40 capture hashes, including six screenshots, verify. Each runtime traceability record uses its own catalog ID as the procedure; no generic or structural alias remains.

The neutral verifier content-read 32 required files and obtained host SHA-256 observations for all 50 indexed paths. Its receipt, report and raw events agree, all five criteria pass, the workspace is unchanged, and no write, approval, MCP, shell, network, provider or credential surface was observed. Adversarial checks cover stale identities, timeline substitution, alternate/manual producers, hidden browser failures, runtime aliasing, deleted producer events, substituted verifier observations and verifier writes.

`PROVEN_WITH_OBSERVABLE_ALTERNATIVE_CAUSALITY` is supported. `HOST_LOAD_UNOBSERVABLE` remains correct; `FULL_HOST_CAUSALITY` and `HOST_SKILL_LOAD_OBSERVED` remain excluded.

## Accepted identities

- Frontend fingerprint: `sha256:c0cd7c9611a89bdb730b2ba73a06212f4b3d432e06ed4f9792550ff7dacd9342`
- Frontend invocation: `INV-33bdb675aa0b5612b85eac20`
- Frontend receipt digest: `sha256:7de739a073f9705cbf61afdf9712cf8717a71714a13f9bac32939c49049a7bd2`
- Frontend events digest: `sha256:6bc37d4d72de346a6548f03b24ebab845693d5f8315c8622c511f631949dd741`
- Browser manifest digest: `sha256:becf97cb77e4c9d13d1dd9735a0f5974451117496230cb120d6f5cc006e277e3`
- Verifier fingerprint: `sha256:dc380396cdc489976b5d120a964321032907f0101431786cda060dae15c11a4b`
- Verifier invocation: `INV-a5d5f1c817335f03892a0fd1`
- Verifier receipt digest: `sha256:5a837184aaddbf512d49be8df6670b30e057d4b0b578521fc3c516c36f1466a8`
- Verifier events digest: `sha256:12c2d9251d276286f5a180a0e2c5b54e5a4ac26208d6f40bbd2058de8c21553a`
- Verification digest: `sha256:4fdcf391244e6f5a294897943be9e65933ec736781720395410d97ad58b08b7f`

## Nonblocking limitations

Chromium-only runtime, no assistive-technology/WCAG certification, a synthetic loopback fixture, and the expiring third-party-scanner waiver remain explicit. Staging complete catalog acceptance metadata and also asserting event class/method would be additional hardening, not a blocker for this bounded candidate.
