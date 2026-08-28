# 30 — Design Director Integration

## Golden reference

O `design-director` atual é o golden reference comportamental do Harness para direção, escolha de meio, progressive disclosure, evidência visual, crítica independente e loops bounded. Isso é uma afirmação de padrão observado, não uma prova causal de que todos os seus resultados são AAA.

## O que deve permanecer

- começar por user/job/context/audience/product truth;
- escolher HTML/CSS, SVG, raster, browser ou specialist deliberadamente;
- separar strategy, art direction, implementation e QA;
- manter source of truth para tokens, identity locks, asset roles e acceptance;
- inspecionar artifact renderizado, não só source code;
- usar viewport/state/region matrix e fidelity ledger;
- rejeitar fake claims, generic AI slop, placeholders e unsupported pixel parity;
- separar builder de critic;
- registrar evidence, score, confidence, limitations e human overrides;
- escolher edit versus regenerate por causa e impor iteration budget;
- degradar honestamente quando browser/imagegen/Figma/font/reference falta.

Evidência primária: `/home/ricardo/.codex/skills/design-director/SKILL.md` e `references/critic-contract.md`, `visual-qa.md`, `iteration-policy.md`, `degradation-and-evidence.md`.

## O que integrar ao Harness

| Pattern visual | Generalização no Harness |
| --- | --- |
| visual brief | capability handoff contract |
| medium matrix | deliberate tool/provider selection |
| viewport/state/region matrix | public-boundary test matrix |
| fidelity ledger | artifact/evidence discrepancy ledger |
| asset provenance | universal artifact provenance |
| render → inspect → measure → critique → fix | run → inspect → verify → review → repair |
| critic independence levels | reviewer independence contract |
| quality rubric | domain quality profile |
| iteration policy | stop/repair budget |

## O que continua independente

- visual grammar, typography, palette, crop, identity locks, asset anatomy e visual anti-patterns continuam específicos de design;
- image generation/editing mechanics pertencem a native imagegen/provider;
- frontend code/interaction pertence ao frontend specialist;
- game runtime/playtest pertence ao game director/specialists;
- data-viz semantics pertence a data/visualization boundary;
- Figma availability/contract não é inventada pelo Harness.

## Contrato com frontend

Design Director fornece visual brief, product truth, tokens, states, responsive/accessibility requirements, asset roles, acceptance e render matrix. Frontend fornece semantic implementation, interactions, loading/error/recovery, tests, render captures e console/network evidence.

## Contrato com imagegen

Design Director define asset role, prompt constraints, references typed, identity lock, must preserve/avoid, output dimensions, provenance e intended placement. Imagegen/provider executa geração/edição. Raster não pode conter UI text essencial; asset só é aceito em uso pretendido.

## Contrato com game-director

Design Director pode fornecer art direction/visual system, enquanto game-director owns player loop, runtime readability, playtest e systems. Um asset não é “bom” porque é bonito fora do jogo; deve passar integração/runtime scale.

## Contrato com verification

Verification confirma commands, renders, states, keyboard, contrast, dimensions, console/network e evidence freshness. Design Director/critic interpreta visual quality; nenhum substitui o outro.

## Não generalizar cegamente

O pipeline completo não deve rodar para todo backend/SQL. A abstração transportável é `direct → execute → inspect → evidence → critique → bounded repair`; conteúdo visual e ferramentas são plug-ins de domínio.
