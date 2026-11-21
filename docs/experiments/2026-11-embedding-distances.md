# Embedding distances by label (2026-11-21)

**Question.** Does bge-m3's cosine distance between two quotes tell "the same claim" (whether they agree
or differ) from "claims about different things"? If so, `FRAMING_MAX` could be set to separate them.

**Setup.** `python -m wikicross.evals embeddings`: every pair of quotes in the labelled cases
(`evals/findings.json`, then 17), embedded on Modal, distance against `FRAMING_MAX` = 0.35.

| Label | Distance range |
|---|---|
| differ (one claim, different values) | 0.277–0.327 |
| agree (one claim, same value) | 0.108–0.303 |
| different (different claims) | 0.317–0.426 |

`embeddings_accuracy` 0.67 (pairs on the right side of 0.35); floor set at 0.6.

## Outcome

The ranges overlap (0.317–0.327 holds both "differ" and "different"): no threshold separates them, so
`FRAMING_MAX` stayed at 0.35 and telling them apart was left to a judge, first the LLM's verdict, then
the [decision model](2026-11-decision-model.md). The [threshold analysis](2026-11-detection-thresholds.md)
later confirmed 0.35 on 26k judged candidates. The eval stays as a check that a model or chunking change
does not move the distances.
