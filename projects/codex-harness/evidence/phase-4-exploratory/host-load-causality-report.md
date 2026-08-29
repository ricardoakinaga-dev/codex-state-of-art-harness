# Host-load causality report

The pilot proves a host-managed turn: `skills/list` matched the exact name/path, `thread/start` returned an ephemeral thread, `turn/start` returned a turn ID, and `turn/completed` was observed. The 34-event stream contained no correlated `skill/loaded` or `skill/load/completed` event. Therefore the causal load fact is `HOST_LOAD_UNOBSERVABLE`, not inferred from discovery or turn success. Support level: `P4_LEVEL_B`.
