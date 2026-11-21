# Experiments

What has been tried on WikiCross's detection and AI, what it measured, and what came of it: read this
before starting an experiment, so that nothing is tried twice and nothing measured is forgotten. Each
entry has its own page with the setup, the numbers and how to repeat it. Newest first.

Status: **adopted** (in the code), **rejected** (measured, not worth it), **open** (measured, decision
pending), **planned** (not run yet).

| Date | Experiment | Result | Status |
|---|---|---|---|
| 2026-11-22 | [Decider asks for the outlier](2026-11-decision-model.md#follow-up-outlier-and-a-same-thing-question-2026-11-22) | Manila: English named (the tone axis said Italian); decide accuracy 0.95 on 20 cases, Trento#5 the miss | adopted |
| 2026-11-22 | ["Same specific thing?" question, passage context](2026-11-decision-model.md#follow-up-outlier-and-a-same-thing-question-2026-11-22) | 0.85 and 0.55 (drops populations from different years); context 0.90 (fixes Trento, breaks two) | rejected |
| 2026-11-22 | [Detection thresholds against the decision model](2026-11-detection-thresholds.md) | The 1.2σ deviation gate does not select disagreements (13% real at every deviation) and passes ~1/5 of what the judge confirms; distance 0.35 is right | thresholds kept; documented |
| 2026-11-22 | [Number prefilter for candidates](2026-11-detection-thresholds.md#number-prefilter) | Same candidate budget, 2.1× the real disagreements (precision 0.34 vs 0.16), but almost no bias ones | open |
| 2026-11-22 | [Linear probe on bge-m3 vectors](2026-11-detection-thresholds.md#linear-probe) | Cross-topic AUC 0.54–0.76: does not carry across topics | rejected |
| 2026-11-22 | [Yield eval as the regression test for detection](2026-11-detection-thresholds.md#yield-eval) | `FRAMING_MAX` 0.30 caught on all three topics (60→20, 248→107, 160→87 kept) | adopted |
| 2026-11-22 | [Decision model as the judge](2026-11-decision-model.md) | 18/18 labelled findings right (LLM: 0.82); ~0.5 s per 10 findings; no rate limit at 40 requests in 3 s | adopted |
| 2026-11-21 | [What the other editions say (consensus)](2026-11-consensus.md) | One LLM call groups up to 40 editions' sentences by claim; populations differ mostly by year, so "most editions" ≠ truth | adopted |
| 2026-11-21 | [Explain prompt for deepseek-4-1-flash](2026-11-explain-prompt.md) | Overlong translations 6/64→2/64, verdict accuracy 0.71→0.82, highlights 1.00 | adopted (verdict since replaced by the judge) |
| 2026-11-21 | [Embedding distances by label](2026-11-embedding-distances.md) | Same-claim and different-claim pairs overlap (0.28–0.33 vs 0.32–0.43): no clean threshold | `FRAMING_MAX` kept at 0.35 |
| before 2026-11 | [Contradiction detectors without an LLM](earlier.md) | Number rules and NLI on machine translations: removed (commit `56dcbbe`) | rejected |

## Running now

Nothing. Last run: the yield eval after the outlier question, 54 / 236 / 158 kept, within 15% of the
baseline ([yield eval](2026-11-detection-thresholds.md#yield-eval)).

## Planned

| Experiment | Why | Notes |
|---|---|---|
| [Number prefilter with a share kept for tone](2026-11-detection-thresholds.md#next-number-prefilter-with-a-tone-share) | 2× the real findings at today's decision cost, without losing bias | check with the yield eval, by kind |
| [CI fixture: where the test database lives](2026-11-detection-thresholds.md#ci-without-modal) | the yield eval on CI needs Modal and Wikipedia; CPU embedding is ~1.5 h (estimate) | recommended: a MariaDB image with the fixture on GHCR |
| [Other ways to find disagreements](ideas.md) | different things matched (Trento), real ones missed | 10 ideas ranked: value-masked matching and instruction embeddings first |
| Wikidata as ground truth for factual disagreements | "most editions" is not truth (see consensus) | needs mapping the subject to a property: unreliable, untried |
| Staying under Wikimedia's API rate limits | 200 requests/min per client | options in [TODO.md](../../TODO.md) |

## Rules of thumb so far

- **A cheap judge on every candidate beats tuning the candidate generator by hand.** The decision model
  made it possible to measure detection at all (26k candidates labelled in minutes).
- **Tone axes find tone, not facts.** 90% of real disagreements are factual; the axes catch them by
  chance. Numbers in both quotes are the best cheap factual signal found.
- **Labelled cases go stale as models change.** Every model switch so far changed the verdicts: run
  `make eval` after one, and add a case for every wrong finding fixed.
- **Counts depend on the database.** Passages are matched over the whole corpus, so yield numbers are
  compared only within one database (A/B), never across.
- **The models are deterministic enough to A/B.** The decision model gave identical answers on reruns;
  the LLM did not (Talvisota#9 flipped between runs).
