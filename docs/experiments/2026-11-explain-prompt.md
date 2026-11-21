# Explain prompt for deepseek-4-1-flash (2026-11-21)

**Problem.** After the LLM was switched to `deepseek-4-1-flash-1017`:

- quote highlighting broke: the model translated the whole passage instead of the quote, gave the
  differing phrases in English or copied them from the passage, or wrote numbers with other grouping
  (122,590 for 122.590);
- unrelated claims were reported as disagreements, e.g. Google's "15 data centers" (fi) vs "19,156
  employees" (ceb), or a figure found only in the surrounding passage.

**Changes tried** (`app.explain()`):

1. The quote comes after its passage, labelled "passage (context only)".
2. `phrases` asked before `english`, in the quote's own language, copied from the quote; field
   descriptions in the schema.
3. A `subject` field: the one thing every quote itself states a value or judgement of, with examples of
   what is *not* one subject (data centres vs employees; two different features; "most popular" vs "key
   to success").
4. Phrases matched loosely (`app.locate()`: case, spacing, digit grouping).
5. Visibility guard: a discrepancy needs a subject and differing phrases found in at least two quotes.

## Measured

30 findings, fresh calls, old prompt vs new (changes 1–4):

| Metric | Old | New |
|---|---|---|
| Overlong English (a translated passage) | 6/64 | 2/64 |
| Missing highlight in discrepancy quotes | 6/54 | 3/40 |
| Description marks linked to a quote | 63/67 | 70/71 |
| Discrepancy true | 25/30 | 19/30 |

On the labelled findings (`python -m wikicross.evals explain`, then 17 cases): accuracy 0.71 → **0.82**
with change 5, highlighted 1.00, not overlong 1.00; 0.82 again on a rerun. Still wrong: Google#0,
Talvisota#9 (flips between runs), Kuopio#8.

## Outcome

Adopted. The LLM's verdict (`discrepancy`, `kind`) no longer filters anything since the [decision
model](2026-11-decision-model.md) judges candidates (18/18); the explanation, highlights and translation
remain the LLM's, asked per card as it is shown. Mind the provider's per-minute limit when running the
eval twice in a row (`429: rate limit exceeded: tenant rpm` after ~30 calls).
