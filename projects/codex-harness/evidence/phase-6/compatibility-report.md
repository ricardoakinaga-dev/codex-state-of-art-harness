# Codex Compatibility and Real Host Report

| Gate | Result | Evidence |
| --- | --- | --- |
| Phase 3 native discovery | PASS | `sha256:0670b57de0947bd53a493d4f3828b86eb1e2d21a16a2e41a0e75d90df778ea11` |
| bounded instruction-kernel load | PASS | `instruction_loaded=true` |
| Phase 4 controlled-real preflight | PASS | `sha256:84b6a24c944967c60d8f71a7931455ae5231976fc68f85cabbc20140b305e258` |
| exact package policy | PASS | `sha256:dc380396cdc489976b5d120a964321032907f0101431786cda060dae15c11a4b` |
| real app-server invocation | PASS | `sha256:a906a0d6c2e9fbf717735a00d513d72f9f4051fb2b9aa14bb7d2aebbf93772d1` |
| browser capture binding | PASS | `sha256:4c3f5968bf5a6727c8e3e04f94bd61a43e391b03b2479478ade3369ceda76782` |
| telemetry ledger | PASS | `38 events` |
| host load causality | UNAVAILABLE | `HOST_LOAD_UNOBSERVABLE` |

The project-local fallback adapter is explicit and only fills the host's
enumeration gap for the local package. It does not claim that the host emitted
a Skill-load event. Global/current installation state remains untouched.
