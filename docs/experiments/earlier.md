# Contradiction detectors without an LLM (2026-11-14)

Reconstructed from the commit messages and `docs/how-it-works.md`; the numbers are the ones recorded
there. The full code is recoverable from the commits named.

## Number rules (`4eef7d7`, removed in `56dcbbe`)

Sentence-level conflicts between the figures in matched sentences (regex numbers, a 20% bar, votes
over the editions' figures), plus passage-level quantity conflicts anchored by a shared number.

- Missed disagreements about names, dates and outcomes (no numbers to compare).
- Paired unrelated figures (two numbers in matched sentences about different things).
- **Rejected as the judge.** Numbers came back on 2026-11-22 as a *prefilter* for the decision model,
  which does the judging ([number prefilter](2026-11-detection-thresholds.md#number-prefilter)): a
  different role, where pairing unrelated figures only costs a judge call.

## NLI on machine translations (`56dcbbe`; behind a flag in `28799a4`; removed in `f9c1a27`)

Each matched sentence pair was judged by two NLI classifiers, both ways round: DeBERTa-v3-large on
M2M100 English translations, and mDeBERTa (XNLI) on the originals. A pair contradicted when all four
scores were ≥ 0.9; an edition contradicting ≥ 2/3 of those it was matched with was the outlier.

- About half the findings were real.
- Minutes per topic's first load, mostly translation.
- **Rejected**: too slow for its precision. The decision model now judges every candidate in ~10 s for
  1,500 candidates, with 18/18 right on the labelled cases
  ([decision model](2026-11-decision-model.md)).

## What stayed

Framing on semantic axes (evaluation, certainty, later wording), z-scored per language: the candidate
generator today. Its 1.2σ gate turned out not to select factual disagreements
([detection thresholds](2026-11-detection-thresholds.md)).
