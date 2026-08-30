Load when: the task crosses a service, module, persistence, API, migration, or architecture boundary and the smallest sufficient change must be chosen.

Start with the existing repository context: runtime, framework, module graph,
data access, API transport, migrations, validation, tests, logging, and
security boundary. Record the owner, inputs, outputs, side effects, data
access, and failure contract for each changed boundary.

Preserve sound architecture by default. A new layer or pattern is justified
only when the current boundary cannot satisfy a stated requirement. The plan
must state the problem, the smallest alternative considered, added complexity,
future cost, and the evidence that the addition is needed. A single endpoint
does not justify a new service, framework, queue, cache, or domain ceremony by
itself.

Use adaptive depth:

| Profile | Minimum emphasis |
| --- | --- |
| `BACKEND_SMALL` | local contract, focused regression, bounded handoff |
| `BACKEND_FEATURE` | use case, API/data boundaries, failure paths, tests |
| `BACKEND_API` | transport, validation, authorization, errors, compatibility |
| `BACKEND_DATA` | constraints, atomicity, race, replay, persisted state |
| `BACKEND_REFACTOR` | baseline, ownership, contract preservation, regression |
| `BACKEND_MIGRATION` | compatibility, preservation, apply, failure, rollback |
| `BACKEND_HIGH_RISK` | security route, independent review, reliability, evidence |

Do not turn a pattern name into an architectural requirement. The specialist
owns the backend change inside the frozen handoff; a director owns broader
architecture decisions and an integrator owns cross-lane assembly.
