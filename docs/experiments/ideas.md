# Ideas: other ways to find disagreements (2026-11-22)

Tried so far (results in [quick matching ideas](2026-11-matching-ideas.md)): **1 rejected**, **2 rejected
for now**, **4 open** (as a gate against different things matched, not as a ranking).

A brainstorm, with what each would fix and how to test it. Nothing here has been measured yet. Move an
idea to its own page when it is run, and add a row to the [index](README.md).

## What goes wrong today

Detection is one sentence vector per sentence (bge-m3), cosine distance, and tone axes. One vector mixes
*what a sentence is about* with *what it says about it*, which causes two failures:

- **Different things matched as one statement.** Data centres vs employees (Google); Trento given to
  Italy in 1919 vs annexed by Germany in 1943; an investment vs a total budget. They share a topic, so
  the vectors are close. The judge catches most of them (none, ~83% of candidates), and it pays for
  every one.
- **Real disagreements never become candidates.** The tone gate passes only ~1/5 of what the judge
  confirms ([thresholds](2026-11-detection-thresholds.md)). And a sentence whose value differs moves
  *away* from its counterpart, exactly where it should be compared.

The fix in every idea below is the same: **match on the question a sentence answers, compare on its
answer.**

## Ideas, cheapest first

| # | Idea | Fixes | Cost | Test |
|---|---|---|---|---|
| 1 | **Value-masked matching.** Embed each sentence a second time with its numbers and dates replaced by placeholders ("Kuopio has ⟨N⟩ inhabitants (⟨YEAR⟩)"). Match on the masked vectors; compare the unmasked values with rules (digit grouping, units, rounding) | recall of factual disagreements; value differences no longer push matches apart | one more embedding pass over matched passages (GPU seconds); regex masking per script | embeddings eval: does differ/different separate better? Yield eval: confirmed findings at equal decision budget |
| 2 | **Instruction-tuned embeddings.** A model that takes a task instruction (Qwen3-Embedding, multilingual-e5-instruct): "Represent the fact this sentence states, not its value" | both failures, if the model obeys the instruction across languages | a new Modal function; re-embedding the sentences of matched passages | the embeddings eval first (20 cases, seconds), then the yield eval |
| 3 | **Cross-encoder reranker** (bge-reranker-v2-m3, multilingual) scoring "same statement?" on each matched pair, instead of the cosine threshold | different things matched; a cross-encoder reads both sentences together and is far sharper than cosine | on the same GPU, a pass over the matched pairs (~10k per topic at full opening), much cheaper than the judge | label 200 pairs with the judge, compare AUC with cosine distance |
| 4 | **Questions as keys** (doc2query). Generate per sentence the question it answers, in English ("What was Kuopio's population in 2022?"), and embed and match the questions | both failures; the time ("in 1943") becomes part of the key, which would separate Trento | one LLM call per matched sentence (thousands per topic): cache, cheapest model | the embeddings eval on questions, then the yield eval on one topic |
| 5 | **Wikilinks as anchors.** Fetch HTML or wikitext instead of plain extracts and keep each sentence's links: every link is a Wikidata item, the same in every language. Pair sentences only if they share linked items, and compare years in the sentence or passage | different things matched (Trento: "Treaty of Saint-Germain" vs "Third Reich"); free cross-language entity matching | changes `wiki.py`'s fetch and storage; same request count | rerun the labelled cases' topics; yield eval |
| 6 | **Claim extraction.** Per sentence, extract structured claims: subject, property, value, time, place. OpenRouter's Extractions API returns typed fields with source spans and confidence. Match claims on (subject, property, time) and compare values exactly | both failures, for facts; also a natural outlier and consensus (values grouped per claim) | an extraction call per matched sentence; the largest change | build on the labelled cases first: do the right claims come out? |
| 7 | **Infobox and Wikidata facts.** Compare infobox values across editions and against Wikidata (values with references and a point in time) | the commonest factual disagreements (population, area, dates), and a ground truth for them | infobox templates differ per edition; mapping their fields to Wikidata properties is the work | precision on the reference topics, by hand |
| 8 | **Fine-tune the encoder on the judge's labels.** 26k judged pairs from the threshold analysis; contrastive LoRA on bge-m3 (same statement vs different) | both failures, learned | a training run on Modal; label noise from the judge | held-out topic, as the probe was (that probe had AUC 0.54–0.76, but it was linear on frozen vectors) |
| 9 | **Section alignment.** Use Wikimedia Research's cross-language section alignments (Content Translation's section mapping) to restrict passage matching to aligned sections | different things matched across sections | a lookup per pair of editions | yield eval |
| 10 | **Recency from history.** For a factual disagreement, read each edition's revision that introduced the value; the most recently sourced value is the likelier truth | "which is true" for numbers that change over time (populations) | history API calls per finding, on demand | the consensus cases (Kuopio's population) |

## Suggested order (revised after 1, 2 and 4)

1. **4 as a gate**: generate questions only for kept findings and drop those whose questions are far apart
   (Trento: 0.53, every real case under 0.29). Label more pairs first; cheap (a few dozen cached LLM calls
   per topic).
2. **3 (cross-encoder)** on kept findings, the same role as 4 without an LLM: bge-reranker-v2-m3 fits on the
   same Modal GPU as bge-m3.
3. **5 (wikilinks)** if Trento-like cases (same place, different event) matter. They need a fetch
   change anyway, which also brings citations (whether two editions cite the same source).
4. **6 (claims)**: the largest gain and the largest change; worth it once 1–3 show how much is left.

Cheap above all: this is a free project. Modal (ephemeral apps, small GPUs, scale to zero) and the free
decision model come first; the LLM only per shown card or per kept finding, cached.

Every one is checked against the same yardsticks: `evals decide` and `evals embeddings` on the
labelled cases, and `evals yield` A/B on the reference topics (confirmed findings at the same decision
budget).
