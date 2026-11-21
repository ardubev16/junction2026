# Decision model as the judge (2026-11-22)

**Question.** Can a decision model (OpenRouter's Decisions API, `perplexity/pplx-decider-v1.3:free`)
tell which candidates are real disagreements, of which kind, fast and cheaply enough to judge every
candidate of a topic, so that false positives are never shown?

**Setup.** `decide.py`: per finding, the first three quotes as `[lang] sentence` lines; two questions, a
`choice` for the kind (factual, bias, framing, none, each with a written criterion) and a 3-level
`score` for the strength. Several findings go in one request, keyed `f0…`, with questions `kind_i` and
`strength_i` ("About f{i} only. …").

## Probes

| Probe | Result |
|---|---|
| Data centres (fi) vs employees (ceb), Google | none, P 0.99 |
| Population 109,455 (ceb) vs 122,590 (vi), Kuopio | factual, P 0.99 |
| War ended 13 March 1940 (fi, sv) | none, P 0.99 |
| The same three in one request | the same answers: batching keeps answers per finding |
| Latency | 0.4–0.7 s per request |
| 40 requests, 8 at a time | 2.8 s, all 200: no rate limit met (the free tier's daily cap is undocumented) |

## Labelled findings

`python -m wikicross.evals decide` on `evals/findings.json`:

- First run, 17 cases: **17/17**. Real ones at P(disagreement) ≥ 0.95, the rest ≤ 0.17. The LLM's own
  verdict on the same cases scored 0.82 ([explain prompt](2026-11-explain-prompt.md)).
- A false positive seen in the extension: Kuopio, en "the two companies plan to invest about 40
  million euros" vs ba/ru "the project's budget is 1.4 billion euros" (different quantities), factual
  at P 0.98. Added as case `Kuopio#59` ("different"): 17/18.
- The `none` criterion was sharpened ("…even about the same place, project or company (e.g. … one an
  investment, another a total budget)"): **18/18**, identical on a rerun (deterministic). Caveat: the
  example mirrors the case, so the case guards the wording more than it proves generalisation.

## On whole topics

| Topic | Candidates | Judged | First run |
|---|---|---|---|
| Kuopio | 262 | 54 factual, 4 framing, 204 none | 2.0 s |
| Talvisota | 1,168 | 188 factual, 45 framing, 12 bias, 923 none | 9.2 s |
| Google | 1,528 | 133 factual, 22 framing, 6 bias, 1,367 none | 10.2 s |

(Before the criterion fix; the current yield baseline is 60 / 248 / 160 kept.)

## Adopted as

`/api/diff` judges every candidate (`app.judge()`), drops `none`, counts kinds, filters by `kinds=` and
orders by P(disagreement) × (1 + strength). If the model fails, findings stay unchecked (kind null) with a
warning. Answers are cached per finding in `llm_cache`; the cache key includes the questions, so editing
a criterion re-asks every candidate once.

## Open points

- Two judges can disagree: a card's LLM description sometimes says the quotes "do not address the same
  thing" while the decision model kept it (that is how `Kuopio#59` was found). Such cards are the source
  of new labelled cases.
- Bias is rare (6–14 per topic); its precision is unmeasured beyond the labelled cases, which hold none.
  Label some bias and framing cases.
