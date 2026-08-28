# 29 — Engineering Director

## Base conceitual

O futuro `engineering-director` deve absorver as responsabilidades arquiteturais que hoje estão documentadas no `engineering-framework`: discovery proporcional, classification, technical design, risk, execution plan, verification e recovery. Não deve copiar a skill inteira como um prompt universal nem transformar todos os seus gates em obrigação para typo/lookup.

## Missão

Converter uma intenção técnica em uma unidade implementável e verificável:

```text
problem → context/change surface → profile → requirements → architecture
        → task graph → specialist handoffs → verification → assurance
```

## Inputs

User goal, repository instructions, current architecture/behavior, acceptance, risk/data/security boundaries, available capabilities/tools, existing plan/state e unknowns.

## Outputs

- problem/requirements/non-goals;
- classification/profile e confidence;
- architecture/contract decisions, ADR refs;
- implementation/recovery plan;
- task graph com ownership/dependencies;
- quality bar e public-boundary checks;
- selected/excluded capabilities;
- authority/approval needs;
- evidence and traceability expectations.

## Boundaries

Engineering Director owns technical strategy, not code ownership of every lane. Backend/API/security/database/frontend/performance specialists own their outputs. Verification owns executed evidence; assurance owns adversarial challenge and stop.

## Lifecycle

For small tasks, it can be a lightweight logical pass. For multi-boundary/system work, it creates/reuses Context Pack, SPEC, ExecPlan, backlog/task graph, risk register and gates. It must not require a complete ceremony when a proportional route proves sufficient.

## Required decisions

- what is current versus proposed;
- which interfaces are public and what compatibility means;
- data/auth/failure/observability boundaries;
- whether orchestration has independent lanes;
- how every acceptance criterion will be proven;
- what may be delivered if a dependency fails;
- when to stop or ask for human authority.

## Relationship to current skill

The audit rates `engineering-framework` as high-value but duplicated across `.agents` and `.codex`; current installed files remain untouched. A future Director implementation must first prove canonical path/host precedence, then migrate behavior through benchmark, not assumption. Source evidence: [`skill-audit/reports/03-static-audit.md`](../../references/skill-audit/reports/03-static-audit.md) and [`13-authority-model.md`](../../references/skill-audit/reports/13-authority-model.md).

## Quality gates

The Director cannot pass implementation. It must hand off to current verification, domain review, and assurance. A technical design is not `VERIFIED` just because it is well written.
