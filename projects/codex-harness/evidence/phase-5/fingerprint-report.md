# Fingerprint report

All final capability and handoff records use exact SHA-256 identities.

| Capability | Package fingerprint | Manifest fingerprint | Decision |
| --- | --- | --- | --- |
| `design-director@0.1.0` | `sha256:564d610da9260d25cbcddfbb3f96f70fb9dabd643c46b4242c4b891d399eba95` | `sha256:402e36727b060eaf4ef740daf8ddfdcfce40cede7cb51ad48c14a582b9037c43` | `ELIGIBLE_DECLARATIVE_METADATA_ONLY` |
| `verification-loop@0.1.0` | `sha256:6cddd9e336f44c261eea24fc983c18f740df9dca8ebfbed0faffc7b9d73ba0ce` | `sha256:1ad02d474bf8f54eb48ea482bc2c628e6611be913a9b41de502241fe135c43f4` | `BLOCKED_INVALID_METADATA` |

The installed design-director package was not edited, copied, installed or
executed through its scripts. The exact package and manifest fingerprints are
repeated in the policy, eligibility, route, context and authorization
evidence; a mismatch blocks the route.
