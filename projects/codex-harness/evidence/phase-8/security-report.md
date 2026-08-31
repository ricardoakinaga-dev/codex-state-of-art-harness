# Phase 8 bounded security handoff

## Scope

This is a bounded static and policy handoff for the fictional local pilot. It
is not an independent security approval or a production security assessment.

## Observed controls

- The fixture binds only to `127.0.0.1`, uses a static path allowlist, caps
  request bodies at 64 KiB, validates patient/species/urgency/notes at the
  server boundary and requires an idempotency key.
- The browser pilot has no external resources or dynamic external requests;
  the observed default request is only
  `GET /api/queue?scenario=default -> 200`.
- Phase 4 policy and host staging deny network, shell, providers, MCP,
  credentials and package-owned side effects. Synthetic patient data is used;
  no owner contact data is collected.
- A scoped marker/sink scan over final `app/` and `build/final/` source found
  no credential markers, `eval`, `new Function`, `innerHTML`,
  `document.write`, `javascript:` or external URL matches.

## Tooling limitations

The pilot has no `package.json` or `node_modules`, so `npm audit` is not
applicable. `pip-audit` was unavailable in the environment. No dependency or
production supply-chain approval is claimed.

## Result

`BOUNDED_PASS_WITH_LIMITATIONS`: no scoped static issue was found, but the
security authority remains a separate handoff and the broad scanner,
deployment, authentication, authorization, CSRF and production threat-model
surfaces were not assessed in this phase.
