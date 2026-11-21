# Detection thresholds against the decision model (2026-11-22)

**Question.** Are `compare.FRAMING_MAX` (0.35, the largest cosine distance inside a group) and
`compare.FRAMING_MIN_Z` (1.2σ, the deviation on a tone axis a candidate needs) right, now that a
decision model judges every candidate? And is there a cheaper way to raise precision (real findings per
candidate)?

**Setup.** Kuopio, Talvisota and Google, with both thresholds opened up (`FRAMING_MAX` = 0.45,
`FRAMING_MIN_Z` = 0): 26,303 candidates (2,252 / 10,137 / 13,914), every one judged by the decision model
([decision model](2026-11-decision-model.md); criterion before the "investment vs budget" fix). "Real" =
judged factual, bias or framing. The labels are the judge's, not human ones: on 18 labelled cases it is
right on all.

How to repeat: patch the two constants, call `compare.differences(cur, wikidata_id,
app.ensure_sentences, every_lang)`, `app.card_order(found)`, then `decide.decide()` on each finding's
first three quotes; group by distance and |deviation|. Took ~6 min (all decisions new); the cached
answers make a rerun take seconds, as long as `decide.QUESTIONS` is unchanged.

## By distance

| Distance | Candidates | Real | Rate | Factual | Bias | Framing |
|---|---|---|---|---|---|---|
| 0.00–0.15 | 441 | 53 | 0.12 | 52 | 0 | 1 |
| 0.15–0.20 | 624 | 131 | 0.21 | 126 | 0 | 5 |
| 0.20–0.25 | 1,490 | 253 | 0.17 | 239 | 0 | 14 |
| 0.25–0.30 | 2,960 | 481 | 0.16 | 446 | 3 | 32 |
| 0.30–0.35 | 4,726 | 800 | 0.17 | 720 | 15 | 65 |
| 0.35–0.40 | 7,514 | 883 | 0.12 | 725 | 20 | 138 |
| 0.40–0.45 | 8,548 | 747 | 0.09 | 543 | 57 | 147 |

## By deviation

| \|Deviation\| | Candidates | Real | Rate | Factual | Bias | Framing |
|---|---|---|---|---|---|---|
| 0.0–0.5 | 3,716 | 577 | 0.16 | 545 | 9 | 23 |
| 0.5–1.0 | 9,694 | 1,238 | 0.13 | 1,121 | 12 | 105 |
| 1.0–1.2 | 3,328 | 431 | 0.13 | 369 | 6 | 56 |
| 1.2–1.5 | 3,752 | 442 | 0.12 | 348 | 16 | 78 |
| 1.5–2.0 | 3,494 | 395 | 0.11 | 293 | 20 | 82 |
| 2.0–3.0 | 2,046 | 231 | 0.11 | 151 | 25 | 55 |
| ≥ 3.0 | 273 | 34 | 0.12 | 24 | 7 | 3 |

## Candidate rules compared

| Candidates kept if | Candidates | Real | Precision | Kuopio | Talvisota | Google |
|---|---|---|---|---|---|---|
| distance ≤ 0.35, deviation ≥ 1.2σ (**today**) | 2,306 | 371 | 0.16 | 229/51 | 767/177 | 1,310/143 |
| distance ≤ 0.35, any deviation | 10,241 | 1,718 | 0.17 | 1,259/211 | 2,377/511 | 6,605/996 |
| distance ≤ 0.40, deviation ≥ 1.2σ | 5,091 | 696 | 0.14 | 357/82 | 2,164/402 | 2,570/212 |
| distance ≤ 0.40, any deviation | 17,755 | 2,601 | 0.15 | 1,791/333 | 5,420/1,022 | 10,544/1,246 |
| distance ≤ 0.45, any deviation | 26,303 | 3,348 | 0.13 | 2,252/421 | 10,137/1,548 | 13,914/1,379 |
| distance ≤ 0.30, any deviation | 5,515 | 918 | 0.17 | 734/83 | 1,039/171 | 3,742/664 |

(Per topic: candidates/real. Today's counts here differ a little from production's, 262/1,168/1,528,
because groups formed at 0.45 split differently.)

## Conclusions

- **The deviation gate does not select disagreements**: about 13% real in every band, and 90% of the
  real ones are factual, which tone axes catch only by chance. Today's gate passes ~1/5 of what the judge
  would confirm. Only bias grows with deviation (21 of 1,815 real below 1σ; 32 of 265 above 2σ).
- **Distance 0.35 is right**: the rate is flat (0.16–0.21) up to 0.35, then falls.
- **Opening the gate is not feasible**: 4.6× the real findings for 4.4× the decision calls (Google: ~660
  requests, ~45 s on a first load instead of 10 s). The user ruled it out: thresholds kept.

## Number prefilter

Rule: both of the first two quotes contain numbers (digit grouping ignored: 122,590 = 122.590 = 122 590)
and their sets differ. Within distance ≤ 0.35:

| Rule | Candidates | Real | Precision | Recall (of 1,718) | Bias kept |
|---|---|---|---|---|---|
| deviation ≥ 1.2σ (today) | 2,306 | 371 | 0.16 | 0.22 | 11 |
| numbers differ | 3,908 | 1,371 | 0.35 | 0.80 | 0 |
| numbers differ, or deviation ≥ 1.2σ | 5,380 | 1,462 | 0.27 | 0.85 | 11 |
| numbers differ, or deviation ≥ 1.5σ | 4,684 | 1,420 | 0.30 | 0.83 | 8 |
| today's count per topic, numbers-differ first, then by deviation | 2,306 | 777 | 0.34 | 0.45 | 0 |

At today's decision cost (the last row) it finds 2.1× the real disagreements (Kuopio 132 vs 51,
Talvisota 268 vs 177, Google 377 vs 143), but the budget fills with number candidates and bias drops to
0. Not the old number rule: that one was the *judge* and paired unrelated figures; here it only orders
candidates for the decision model. **Open.**

### Next: number prefilter with a tone share

Keep a fixed share of the budget (e.g. a quarter) for the highest-deviation candidates without
numbers, the rest numbers-differ first. Measure with the yield eval per kind: bias and framing must not
fall below today's, factual should about double, total candidates must stay at today's count.

## Linear probe

Logistic regression on the first two quotes' bge-m3 vectors (|u−v| and u⊙v, 2,048 features, plus
distance, deviation and the number flag), trained on two topics' judge labels and tested on the third,
distance ≤ 0.35:

| Test topic | AUC | Real in today's budget: probe | today's gate |
|---|---|---|---|
| Kuopio | 0.76 | 109 of 229 | 51 |
| Talvisota | 0.58 | 202 of 767 | 177 |
| Google | 0.54 | 215 of 1,310 | 143 |

The number-first ordering alone beats it on every topic (132, 268, 377 real at the same budgets), and the
vectors do not generalise across topics. **Rejected.**

## Yield eval

`python -m wikicross.evals yield [--update]`: per reference topic (`evals.TOPICS`: Kuopio, Talvisota,
Google) the candidates and how many the judge keeps, by kind, against `evals/yield.json`; a topic keeping
over 15% fewer fails. The baseline is per database (passages are matched over the whole corpus) and
gitignored: save it on main's code, then run the change. CI's on-demand `yield` job does exactly that in
one fresh database.

Baseline (local database, 2026-11-22): Kuopio 262 candidates / 60 kept, Talvisota 1,168 / 248, Google
1,528 / 160. Simulated regression, `FRAMING_MAX` = 0.30 (with `app.CODE` changed so the diff cache is not
reused): 125 / 20, 583 / 107, 734 / 87, all three flagged, exit 1. Note: that run overwrote the topics'
`diff_cache` rows (keyed by wikidata id); the next real load recomputes them.

After the decider gained its outlier question (same day): 54, 236 and 158 kept (−10%, −5%, −1%), within
the 15% tolerance. Questions asked together in one request nudge each other's answers a little.

## CI without Modal

Not run; an estimate. The reference topics hold ~5.4k passages and ~22k sentences in the database (only
matched passages get sentences). At the CPU rates measured with Ollama (≈2 passages/s, ≈8 sentences/s
on a laptop) that is ~1.5 h per fresh run, too slow for CI; CPU vectors would also differ slightly from
the GPU's. Better: a MariaDB dump of the reference topics (articles, chunks, sentences, embedding and
decision caches) restored in CI. No Wikipedia fetches, no embedding, and only new candidates ask the
judge. It needs a home outside git (~100 MB of vectors: 4 KB × ~27k, float32 barely compresses) and a
refresh when the embedding model or the chunking changes.

Where it could live:

| Option | For | Against |
|---|---|---|
| **GHCR: a MariaDB image with the fixture baked in** (`ghcr.io/ardubev16/wikicross-evaldb:<date>`), used directly as the job's `services.mariadb.image` | no download step; versioned by tag; the registry and `GITHUB_TOKEN` push already used for the app image; free for a public package | an image build per refresh (a workflow: dump, then `docker build` from `mariadb:lts` with the dump in `/docker-entrypoint-initdb.d`, or the data directory baked for a faster start) |
| GitHub release asset (`gh release download`) | simplest; up to 2 GB per file; versioned | a restore step on every run (a minute or two for ~100 MB of inserts) |
| Actions cache | built in, 10 GB | evicted after 7 days unused; not reproducible as a reference |
| Git LFS | in the repository | 1 GB of free storage and bandwidth a month: a few CI runs |
| Hugging Face dataset, or object storage (Cloudflare R2: 10 GB free, no egress fees) | large, versioned | another account and its secrets |

Recommended: the GHCR image. The yield job's two runs, main then branch, would then start from the
fixture instead of an empty database.
