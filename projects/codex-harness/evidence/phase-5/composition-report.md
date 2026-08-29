# Bounded composition report

The only accepted graph is:

`DESIGN_BUILDER → STRUCTURAL_VERIFICATION → VISUAL_CRITIQUE → OPTIONAL_REPAIR → FINAL_VERIFICATION → ASSURANCE`

The successful run produced `artifact_v1`, captured native desktop and mobile
renders, ran structural verification, received a blind independent visual
critique, applied exactly one material correction, produced retained
`artifact_v2`, recaptured evidence, reran structural verification and visual
critique, and closed with assurance.

| Resource | Observed | Budget |
| --- | ---: | ---: |
| Builder invocations | 2 | 2 |
| Structural verifications | 2 | 2 |
| Visual critiques | 2 | 2 |
| Repair invocations | 1 | 1 |
| Artifact versions | 2 | 2 |
| Artifact v2 bytes | 9,161 | 131,072 |
| Context budget per request | 32,768 bytes | 32,768 bytes |

The v1 digest is
`sha256:28c25dc82baedfb856ea41ce6cde2c520909869c3e946de9d750d826e8ff7e85`.
The v2 digest is
`sha256:b85e7db1b2eb9e6c6f3adfa0a4dd39e0ee01bb955a73a7adec6936ec25483adb`,
and the repair receipt binds v2 to v1 as its parent. v1 verification and
critique remain retained and are marked stale in the composition receipt after
the artifact changed; the current v2 evidence is the only final authority.

The graph rejects arbitrary nodes, cycles, budget bypasses, stale artifact
references, path traversal, unsafe HTML response keys, executable scripts,
remote resources, and ineligible secondary capabilities. The blocked negative
cases are covered by `tests/evals/phase5/test_phase5_negative.py` and the
Phase 5 unit/integration tests.

The final verification is a distinct post-critique record with id
`FINAL-VER-P5-V2` and digest
`sha256:fb725968b77d4c657109b1d45288d9f1566280c3c6e1dde9e666f68197df9b94`;
`verification-v2.json` is retained as the pre-critique v2 structural record.
Browser metric records are bound to the artifact version/digest, native capture
method, captured URL, viewport, capture ID, and Chromium executable/version
digest before structural checks consume them.
