# 34 — Modernization Template

Use este template para qualquer Skill/package. O registro deve ser versionado e separado do pacote atual; não substituir `SKILL.md` durante pesquisa.

## 1. Inspect current

Path, hash, frontmatter, trigger, owner/type, workflow, dependencies, tools, references, scripts, evals, output, stop conditions, portability assumptions, known users e current evidence.

## 2. Inspect upstream

Source URL/revision/date, license, changes, current docs, compatibility, security notes e divergências. “Upstream current” é `UNKNOWN` se não foi fetch/revalidado.

## 3. Identify Codex-native capability

List native tools/features that overlap; decide o que fica como native execution e o que a Skill acrescenta (routing, policy, domain knowledge, evidence, template).

## 4. Remove portability debt

Marcar Claude/Cursor/OpenCode hooks, commands, paths, tool names, memories e schemas. Substituir por capability-level abstraction only when current Codex contract supports; otherwise label adapter/unknown.

## 5. Define scope

Goal, activate, do-not-activate, domain boundary, non-goals, user/product truth, risk, data/security, ownership e expected users.

## 6. Define contracts

Manifest, input/output, composition, dependencies/conflicts, state, error/degradation, artifact/evidence, authority e version compatibility.

## 7. Design workflow

Minimal path, optional overlays, deterministic checks, tool/provider choice, context pack, stage skip reasons e handoffs.

## 8. Add deterministic checks

Parser/link/schema/AST/browser/benchmark/asset/test check. Definir known-bad e expected failure.

## 9. Add references

Move long domain knowledge to `references/`; each file has load trigger, source/date, scope and no duplicate policy.

## 10. Add evals

Positive, negative, ambiguous, unavailable-tool, no-skill, regression and security scenarios; fixed fixtures and oracle.

## 11. Add quality gates

Required/advisory criteria, evidence method, threshold/anchor, baseline, confidence, limitations e review level.

## 12. Add stop conditions

Iteration/retry/budget/no-progress/oscillation/missing-tool/human-stop and residual-risk rules.

## 13. Add benchmarks

Native-only/current/upstream/vNext controls; fixed model/config/repo/fixtures; loaded tokens/tool calls/latency/quality/cost; blind grading.

## 14. Test

Run package validator, scenario evals, contract/link checks, security checks and relevant runtime boundary. Preserve raw evidence.

## 15. Compare

Compare current/vNext on correctness, reliability, activation precision/recall, context cost, tool use, latency, failure handling and human/domain quality.

## 16. Promote or reject

`PROMOTE`, `CANDIDATE`, `DEFER`, `REJECT` with reason, evidence, residual risk, owner, revalidation trigger e authority. Nunca promover porque o texto ficou maior ou “mais moderno”.

## Record shape

```yaml
modernization_record:
  skill: capability-name
  current_ref: path/hash
  upstream_ref: url/revision/date
  vnext_ref: docs/...
  status: CANDIDATE
  portability_debt: []
  contracts: []
  evals: []
  benchmark: null
  findings: []
  promotion_criteria: []
  decision: ""
  authority: PENDING
  revalidation_trigger: ""
```
