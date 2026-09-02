# State and interaction contracts

Classify every state before implementation:

| Kind | Examples | Owner |
| --- | --- | --- |
| Local/UI | open panel, draft input, selected row, focus state | component/flow |
| Server/data | queue records, submit result, request lifecycle | data boundary |
| URL/navigation | route, shareable filter, query string | router/browser |
| Derived | filtered count, urgency summary, disabled state | pure derivation |

Keep fetched data immutable and derive views without mutating it. Give each
request a clear lifecycle: idle, loading, success, empty, error and retry.
Stale responses must not overwrite a newer request. Forms keep drafts local,
validate at the boundary, map server errors to named controls and disable the
primary action during an in-flight idempotent submit. A double click must not
create two records.

Use native controls first. Buttons have visible labels and a single job;
links navigate; inputs have labels and error relationships; tables preserve
headers and reading order. Keyboard behavior is explicit for every custom
interaction. Focus remains visible and is restored after an overlay or
navigation when the surface exposes one.

Do not present a polished loading or error shell that lies about data. Empty,
stale, permission and recovery states are content contracts, not decorative
variants. Test the actual state transition, not only the final DOM snapshot.
