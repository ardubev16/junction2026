# What the other editions say (2026-11-21)

**Question.** For a factual disagreement, can we show the ground truth, or at least what most editions
say?

**Setup.** `POST /api/consensus`: for the card's quotes, each other edition's sentence closest to their
mean vector (`compare.nearest_elsewhere()`, distance ≤ `CONSENSUS_MAX` = 0.40, at most 40 editions),
then one LLM call groups all editions by the claim they state (with the date it is given for), leaving
out those that do not state the subject.

## Tried first

The LLM mapped each other edition to one of the card's quotes, or "other", or "none". Rejected: "other"
hid the values. On Kuopio's population, 19 editions were "other", with figures 90,000, 126,572,
120,246 and more.

## Measured (grouped by claim)

Kuopio's population, Cebuano 109,455 vs Vietnamese 122,590: 23 of the 40 closest editions state it.

| Claim | Editions |
|---|---|
| 122,590 (31 Dec 2022) | 4 |
| 126,572 (2025) | 4 |
| 122,594 (2022), 120,246 (2020), 120,000, 121,572, 119,472 (region) | 2 each |
| 109,455 (the Cebuano quote) and 11 other figures | 1 each |

About 1 s per call.

## Outcome

Adopted, behind "What do the other editions say?" on factual disagreements: top 5 positions plus the
quotes' own, the rest behind "Show N more". The main lesson: **most editions is not truth**. Figures
differ mostly by year, and editions copy one another; the card says so. For real ground truth, Wikidata
(values with references and "point in time") is the candidate. It is untried: the AI's subject would have
to be mapped to a Wikidata property, which looked unreliable.
