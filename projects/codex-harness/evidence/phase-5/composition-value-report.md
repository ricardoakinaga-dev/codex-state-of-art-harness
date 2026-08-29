# Composition value report

This is a single bounded pilot comparison, labeled
`PILOT_COMPOSITION_EVIDENCE`. It compares the native minimal baseline with the
final bounded builder/review composition. It is not scientific causal proof,
a production benchmark, or evidence that the installed Skill alone caused the
visual delta.

| Measure | Native minimal baseline | Builder + review composition |
| --- | ---: | ---: |
| Visual score | 34/100 | 87/100 |
| Material evidence items | 8 | 4 |
| Native desktop load-event observation | 38 ms | 58 ms |
| Builder invocations | 0 | 2 |
| Structural verifier invocations | 0 | 2 |
| Blind critic invocations | 0 | 2 |
| Repair invocations | 0 | 1 |

Observed deltas are: `+53` score points, `4` fewer recorded evidence items,
and `+20 ms` in this one browser navigation observation. The composition score
is the independent v2 visual score; the baseline score is a conservative
inspection of the deliberately minimal fixture against the same 12 dimensions
and is not an independent scientific sample.

The largest attributable pilot change was the bounded repair of the 390px
header status from a crowded three-line state to a compact `Open 24/7` signal.
The v2 packet still documents unresolved mobile composition/accessibility
limitations and the unverified fictional phone target.
