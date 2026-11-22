# Quick matching ideas: value masking, instruction embeddings, questions as keys (2026-11-22)

**Question.** Can a different way of embedding fix the two failures of matching (different things matched as
one statement, e.g. Trento 1919 vs 1943; real disagreements ranked no better than chance by bge-m3)? Ideas 1,
2 and 4 of [ideas](ideas.md), tried cheaply.

**Cost.** Everything on Modal, as an ephemeral app (`app.run()`, nothing deployed) on one L4: bge-m3 and
Qwen3-Embedding-0.6B, ~16k texts in 4 minutes including the image build, about $0.05. Questions: ~25 LLM calls
(20 sentences each), cached. Decision labels: the free decision model. (A first try downloading the models for
local CPU ran at ~190 KB/s; OpenRouter's embeddings API also works, $0.01 per million tokens, but Modal was
preferred.)

## Two yardsticks

1. **Ranking candidates.** 4,009 candidate pairs (Kuopio and Mainila whole, 1,500 of Talvisota; thresholds
   opened to distance 0.45 and no tone gate), the first two quotes of each, labelled by the decision model: 733
   real. Does a score put real ones first? AUC, and real ones in the top 20% (chance: 147).
2. **Telling claims apart.** The labelled cases: pairs of one claim ("differ", "agree") should be closer than
   pairs of different claims ("different"), as `evals embeddings`. AUC; 41 pairs (29 with questions).

## Ranking candidates

| Score | AUC | Real in top 20% (of 733) | With the number rule first: AUC |
|---|---|---|---|
| bge-m3 dissimilarity (today's vectors) | 0.50 | 121 | 0.73 |
| the number rule alone | — | — | 0.73 |
| bge-m3: masked minus raw similarity (idea 1) | 0.39 | 141 | 0.73 |
| Qwen3-0.6B + instruction, dissimilarity (idea 2) | 0.57 | 204 | 0.73 |
| Qwen3-0.6B: masked minus raw (ideas 1+2) | 0.45 | 181 | 0.72 |
| questions (idea 4), bge-m3 similarity (990 pairs) | 0.34 | 51 of 346 | 0.76 |
| questions minus statements, bge-m3 (990 pairs) | 0.37 | 68 of 346 | 0.77 |
| bge-m3 dissimilarity, the same 990 pairs | 0.65 | 90 of 346 | 0.80 |
| questions minus statements, Qwen3 (990 pairs) | 0.47 | 72 of 346 | 0.80 |

- **No score beats the number rule** at ranking candidates; added to it, none moves the AUC.
- **"Same question, different statement" ranks worse than plain dissimilarity.** Among candidates, what the
  judge rejects are mostly agreeing paraphrases, not different things: a same-question score finds agreement.
- Qwen3 with the instruction is the only embedding better than chance alone (0.57), not enough to re-embed
  every sentence for.
- One hint for tone: Qwen3 question similarity put 13 of the 33 bias/framing pairs in the top 20% (chance:
  6.6). Too few to act on.

## Telling claims apart (labelled cases)

| Method | AUC (one claim closer) | Distances: differ / agree / different | Trento#5 |
|---|---|---|---|
| bge-m3, sentences (today) | 0.63 | 0.24–0.36 / 0.11–0.33 / 0.03–0.43 | 0.35: matched |
| Qwen3-0.6B + instruction, sentences | 0.45 | 0.26–0.55 / 0.26–0.40 / 0.09–0.55 | 0.23 |
| **bge-m3, generated questions** | **0.77** | 0.11–0.29 / 0.11–0.57 / 0.14–0.59 | **0.53** |
| Qwen3-0.6B, generated questions | 0.78 | 0.16–0.40 / 0.15–0.62 / 0.12–0.80 | 0.53 |

Questions keep the time and circumstances ("What happened to Trento's sovereignty under the Third Reich?") and
drop the wording. With bge-m3 questions, every "differ" pair is within 0.29 and Trento is at 0.53: a cut at
~0.45 would drop it and keep every real case. **Promising, on 29 pairs**: not enough to adopt.

## Outcome

- Idea 1 (value masking): **rejected**, worse than nothing on both yardsticks.
- Idea 2 (instruction embeddings): **rejected for now**: slightly better ranking, worse at telling claims apart,
  and re-embedding everything.
- Idea 4 (questions): **open.** Not as a ranking; as a **gate for different things matched**, the failure the
  decision model misses (Trento). The cheap form: generate questions only for the quotes of *kept* findings
  (60–250 per topic, a few dozen cached LLM calls, or in the card's explanation call that runs anyway) and drop
  a finding whose questions are further apart than ~0.45. Next: label ~50 more same/different pairs (e.g. from
  the decision model's kept findings on the reference topics) and check the cut there before adopting it.

## How to repeat

- **Pairs:** in the project environment, set `app.CODE` to something else (see the pitfall in
  [bias and framing](2026-11-bias-framing.md#pitfall-met)), patch `compare.FRAMING_MAX = 0.45` and
  `compare.FRAMING_MIN_Z = 0`, run `compare.differences()` per topic, `app.card_order()`, `decide.decide()`
  on the first three quotes; keep the first two quotes, the label and whether their numbers differ.
- **Questions:** one `llm.chat()` per 20 sentences: "for each numbered sentence write in English the one
  question it answers about its subject, without giving the answer: keep the subject, and the time, place or
  circumstances it states".
- **Embeddings:** a Modal class like `embed_gpu.Embedder` with both models (`Qwen/Qwen3-Embedding-0.6B`, prompt
  "Instruct: Represent the specific fact or claim this sentence states about its subject, regardless of the
  exact numbers, dates or wording\nQuery: "), on an L4, called inside `with app.run():` so nothing stays
  deployed.
