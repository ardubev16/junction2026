# Why Shelling of Mainila showed no bias (2026-11-23)

**Question.** Mainila showed 0 bias findings, after the changes of [bias and framing](2026-11-bias-framing.md).
Do other topics show bias, and what is missing on Mainila?

## Survey: bias per topic (before)

The page's counts, dialects hidden:

| Topic | Factual | Bias | Framing |
|---|---|---|---|
| Shelling of Mainila | 3 | **0** | 5 |
| Stepan Bandera | 73 | 16 | 20 |
| Benito Mussolini | 171 | 17 | 27 |
| Winter War | 135 | 8 | 38 |
| Continuation War | 40 | 1 | 19 |
| Finnish Civil War | 74 | 3 | 9 |
| Urho Kekkonen | 29 | 4 | 5 |
| Climate change | 66 | 4 | 24 |
| Google | 50 | 4 | 12 |
| Jewish Autonomous Oblast | 39 | 0 | 3 |
| Harald Nugiseks | 1 | 0 | 0 |

Bias is found where editions use loaded words (Bandera: "devoted his whole life to Ukraine's
independence" vs "a controversial figure"), and is rare everywhere: the decision model calls most
differences in stance framing (settled in one, attributed in another), which on Mainila is what they are.

## Tried

| Approach | Cost | Result |
|---|---|---|
| Each member of a big group (8+ editions) judged with the group's two most central quotes (by bge-m3), 164 decisions | free (decision model) | no bias on the lead; ru against pt/it: none. Rejected |
| Earlier: spread order, medoid pairs, axis extremes, all pairs, one question over the whole group ([bias and framing](2026-11-bias-framing.md#the-leads-bias-still-not-found)) | free | no bias on the lead |
| **Reading the texts** | — | the Ukrainian lead's claim was never compared: see below |

## Cause: a sentence split inside brackets

The Ukrainian lead is "Майнільський інцидент (рос. …), або Обстріл Майніли (фін. Mainilan laukaukset,
швед. Skotten i Mainila) — радянська провокація, що була використана керівництвом СРСР…" ("… a Soviet
provocation used by the USSR's leadership…"). The splitter broke it at "(фін." before the capital "M": the
lead group got "Майнільський інцидент (рос. Майнильский инцидент), або Обстріл Майніли (фін." and the
claim went into a separate, unmatched sentence. Leads in Cyrillic editions give the names in other
languages this way ("(англ. …)", "(фін. …)"): 0.5% of all sentences ended inside a bracket (ru 1.5%,
de 1.2%, uk 0.9%), 223 of 1,498 pages, mostly in leads, which are the statements most editions share.

**Fix.** `compare.sentences()` does not break inside brackets. The splitter moved from `app.py` to
`compare.py`, so a change to it changes `app.CODE` and the cached findings are recomputed; and
`ensure_sentences()` re-splits a page whose stored sentences differ from today's split, keeping the vector
of every unchanged sentence (only the changed ones go to Modal: Mainila's re-split took a minute, a
handful of sentences embedded).

**Result.** Mainila's lead group (23 editions) is now judged on fi "staged by the Soviet Union", uk "a
Soviet provocation", da (neutral): **bias**, P 0.71. Mainila: factual 4, bias 1, framing 6.

**A/B** (yield eval's loop, dialects hidden; the old splitter patched in under another `app.CODE`):

| Topic | Kept, old splitter | Kept, new | Bias, old → new |
|---|---|---|---|
| Kuopio | 34 | 34 | 0 → 0 |
| Talvisota | 241 | 235 | 9 → 9 |
| Google | 119 | 120 | 6 → 6 |
| Shelling of Mainila | 17 | 18 | **0 → 1** |

Nothing lost beyond noise (Talvisota −2.5%, within the yield eval's 15%).

## New contested topics

Fetched and embedded for this (on the deployed Modal app; three topics of 44–70 editions):

| Topic | Editions | Factual | Bias | Framing | A bias finding |
|---|---|---|---|---|---|
| Holodomor | 70 | 76 | 4 | 40 | uz "economic and political mistakes" vs sr "Stalin's policy of forced collectivisation" |
| Annexation of Crimea by the Russian Federation | 44 | 46 | 9 | 18 | be "unlawful seizure of the temporarily occupied peninsula" vs fr, af (neutral) |
| Srebrenica massacre | 51 | 84 | 3 | 16 | hr "a particularly fierce Serb attack" vs ro, gl (neutral) |

## Regression tests

- **Yield eval:** `evals.EXPECTED`, per topic, findings that must be shown, as (kind, editions among its
  judged quotes): Mainila bias with uk; Crimea bias with be and fr; Bandera any bias. Crimea and Bandera
  joined `TOPICS`. The yield eval now judges what the page shows (dialects hidden), as does `evals add`:
  before, both included dialects, so their groups and judged quotes were not the page's. (The saved
  baseline must be redone once: its counts included dialects; Kuopio, with many, fell 54 → 34.)
- **Decide eval:** three new bias cases: Mainila#36 (fi, uk, da), Crimea#394 (be, fr), Bandera#4 (az, fr;
  bias or framing). Run: accuracy 0.90 (floor 0.9; wrong: Trento#5, Mainila#de-fr, Mainila#ru-en-et, the
  last right in the previous run), kind 0.86, outlier 1.00. Mainila#36 bias (P 0.65–0.72), Crimea bias
  (0.97) in five fresh runs each; Bandera#4 framing in a batch of three, bias in the page's batch.
- **Pinning a finding is fragile**: the decision model's answer for a finding depends on the other
  findings in its request of ten. Answers repeat for one batch, so the eval is stable on one database, but
  a pinned pair near the bias/framing border can flip on another. Bandera is checked for any bias finding
  instead.
- **Unit test:** `test_sentences_do_not_break_inside_brackets`.

## Not done

- Yakut (`sah`) states the Soviet version as fact ("soldiers near Mainila were shelled from the Finnish
  side") and is hidden by default with the dialects: `is_dialect()` files every code that is not two
  letters as a dialect, and sah is a language. A curated list would fix it; not needed for bias here.
- Bias stays rare (0–21 per topic): the decision model calls stance differences framing unless the
  wording is loaded, which matches the definitions on the About page.
