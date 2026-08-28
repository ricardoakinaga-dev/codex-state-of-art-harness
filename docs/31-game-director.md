# 31 — Game Director

## Status

`PROPOSED FUTURE DIRECTOR`. Não existe implementação/game runtime neste workspace.

## Arquitetura

```text
game-director
├── game-design
├── gameplay-engineering
├── game-art-direction
├── asset-pipeline
├── level-design
├── game-ui
├── physics
├── AI
├── VFX
├── audio
├── optimization
└── playtest
```

## Missão e boundaries

Game Director preserva player goal, core loop, genre/identity, readability, difficulty, feedback, platform constraints e fun hypothesis. Não implementa todos os systems, não substitui playtest e não chama media tools por decoração.

| Specialist | Owns | Handoff/evidence |
| --- | --- | --- |
| game-design | rules, loop, progression, win/fail | design brief, acceptance |
| gameplay-engineering | input, state, mechanics | runnable behavior, tests |
| game-art-direction | art bible, palette, silhouettes | reference/art artifact |
| asset-pipeline | import/scale/format/atlas | asset provenance/runtime decode |
| level-design | space, pacing, encounters | playable level/playtest notes |
| game-ui | HUD, menus, feedback | runtime screenshots/input evidence |
| physics | collision/feel/simulation | deterministic scenario/perf |
| AI | behavior/navigation/opponents | fixture runs, failure cases |
| VFX | effects/readability | runtime scale/overdraw evidence |
| audio | cues/mix/feedback | playback/asset provenance |
| optimization | frame time/memory/load | representative benchmark |
| playtest | user/agent interaction/feel | playtest report, findings |

## Adaptive activation

- prototype mechanic: game-design + gameplay + minimal playtest;
- visual asset: game-art + asset-pipeline + design-director if visual QA;
- UI issue: game-ui + frontend/verification;
- physics/AI bug: relevant specialist + deterministic runtime fixture;
- shipping/high-fidelity build: Director + selected specialists + verification + playtest + assurance;
- pure copy/typo in docs: no game route.

## Quality profile

Correct input/state transitions, readable feedback, no impossible/win-lock states, frame-time/resource target, asset provenance, accessibility/controls where applicable, recovery from pause/error, and playtest evidence. “Fun” is a human/eval hypothesis, not a claim from code inspection.

## Tools and failures

Use native browser/game runtime, deterministic fixtures, screenshots/video/audio tools only when required. Missing runtime blocks playability claims; missing art provider need not block mechanics. Preserve independent lanes and label partial output.
