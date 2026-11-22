# Bias and framing on Shelling of Mainila (2026-11-22)

**Question.** Bias and framing findings must work as well as factual ones. Shelling of Mainila (25
editions) is a contested incident whose editions describe the same shelling very differently: why did
it show 13 framing findings, 7 of them the same Belarusian sentence, and no bias at all?

## What the editions say

| Edition | Its lead |
|---|---|
| fi | "a staged incident by the Soviet Union" (*Neuvostoliiton lavastama*) |
| uk | "a Soviet provocation" used as a formal pretext |
| be | the Soviet version, attributed: "according to official Soviet claims" |
| ru | "an artillery shelling … occurred"; who fired is left open |

The decision model, given the ru, fi and uk leads: **bias, P(disagreement) 0.88, outlier ru**. The
finding was never shown.

## Why

1. **It was never a candidate.** The leads are matched (ru–en 0.21, fi–ru 0.35, uk–fi 0.36) into one
   group of 24 editions. Averaged over 23 others, no edition sits 1.2σ apart on any tone axis: at most
   fi, 1.12σ on certainty. The more editions state something, the more its tone deviations flatten. So
   the tone gate drops a topic's core statements first.
2. **The decider would have seen the wrong three.** A card shows, and the decider judges, the first 3
   members, in language order (fi, sv, en, then alphabetical). For the leads that is fi, sv, en, which
   agree.
3. **Repeated cards.** be's second sentence could not join the lead group (be was taken), so it stayed a
   pair with each other edition's lead: 7 of the 15 cards.

## Changes tried

Ablation of three changes, each on its own then together (kept: cards the decider keeps; shown:
distinct sentences on their first three quotes):

| Variant | Kuopio candidates / kept / shown | Mainila candidates / kept / shown |
|---|---|---|
| before | 257 / 53 / 68 | 35 / 15 / 26 |
| **stars**: pairs left between groups that share a sentence merged around it, before judging | 106 / 23 / 47 | 22 / 5 / 15 |
| **spread**: a group's members ordered most-different-first (farthest matched pair, then max-min distance) | 258 / 56 / 77 | 35 / 15 / 26 |
| **big groups**: 8+ editions are a candidate whatever their tone | 264 / 56 / 75 | 42 / 17 / 30 |

- **Stars: rejected.** A merged group is judged on three of its quotes; judged "none", it takes down
  pairs that were real one by one (Mainila: 26 → 15 sentences shown).
- **Spread and big groups: adopted.** More findings and more distinct sentences shown, at a handful of
  extra decider calls (Mainila: +7 candidates; Kuopio: +7).
- **Repetition fixed after judging instead** (`app.merge_shared()`): judged findings of two quotes that
  share a sentence and a kind become one card around that sentence, which is the outlier. Nothing is lost:
  every pair was judged on its own.

## Result

Yield, A/B against the code before (four reference topics, Mainila added): Kuopio 54 → 60 kept, Talvisota
236 → 253, Google 158 → 171, Mainila 15 → 17, all up. On the page (dialects hidden), Mainila's 15 cards
became 10: the 7 Belarusian ones are one card of 9 editions, outlier be, and the big groups show (Yeltsin on
the war, 12 editions; the Zhdanov archives vs "Finnish historiography regards", 14).

The decision model on new labelled cases (decide eval, 27 cases):

| Case | Label | Decision |
|---|---|---|
| Mainila lead: ru / fi / uk | differ, bias or framing, outlier ru | bias, P 0.93, outlier ru ✓ |
| be "according to official Soviet claims" / cs "false flag" | differ, framing | framing 0.98 ✓ |
| nb "was a false flag operation" / sh "many consider it" | differ, framing | framing 0.88 ✓ |
| be-tarask "Finnish historiography regards" / en, ca "the archives show" | differ, framing, outlier be-tarask | framing 0.76, outlier be-tarask ✓ |
| de / fr, both attributing the casualty claims | agree | framing 0.64 ✗ |
| en / nb, both "false flag" | agree | none ✓ |
| ru pact denounced 28 Nov / en, et relations broken 29 Nov | different | none ✓ |

Accuracy 0.93, kind 1.00, outlier 1.00. **The judge handles bias and framing; choosing what it sees is the
problem.**

## The lead's bias: still not found

Every automatic way of choosing which of the lead group's 24 quotes to judge was tried; all are cheap
(free decider, a few requests per group):

| Selector | What the decider says |
|---|---|
| spread (most different by vector) | fi, be-tarask, da: none (they agree; distance follows wording and length, not stance) |
| all 24 quotes at once | none (P 0.49), outlier an |
| each member against the medoid (pt) | ca factual, an framing; ru: none |
| the two extremes of each tone axis | fi vs sv: none |
| one yes/no per member: "presents it differently from most?" over the whole group | fr, sv, an highest; ru low |
| all 215 matched pairs inside the group | 35 kept, mostly sv (factual) and framing; ru–fi and ru–uk none, ru–cs bias |

Only the triple ru/fi/uk reads as bias: two loaded accounts ("staged", "provocation") next to a neutral one.
Any pair of them reads as "adds detail". The difference here is an omission (ru does not say who fired),
which no vector distance and no tone axis measures. Next options: compare *who is said to be responsible*
explicitly, as a claim (idea 6, [ideas](ideas.md)); or ask the decider, per big group, which editions name a
culprit and which do not, a question specific to contested events.

## Pitfall met

An experiment script that patches `compare.FRAMING_MAX` or `FRAMING_MIN_Z` and calls
`app.compare_editions()` writes its results into `diff_cache` under the real code's hash, if the cache
row is stale. The next real load then serves them: a yield run read 257 Mainila candidates instead of
~42. In experiment scripts, set `app.CODE` to another value first, or delete the topic's `diff_cache` row
after.
