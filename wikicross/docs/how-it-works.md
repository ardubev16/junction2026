# How WikiCross works

WikiCross finds where the Wikipedia editions of one topic **frame the same thing differently** or
**contradict each other**: Finnish, Swedish and English from dataset S, every other Latin- or
Cyrillic-script edition fetched live from Wikipedia on the first request (`wiki.py`). It needs no
LLM: bge-m3 vectors compared inside MariaDB, plus two small models on the GPU (a translator to
English and an NLI classifier). An optional LLM step (off by default) can summarise and translate.

Passages in two dataset languages (fi, sv, en) are matched over the whole corpus with HNSW, as below.
Any pair involving another language is matched only inside the topic, by an exact join: HNSW filtered
to a language with a few articles would scan almost the whole index. Framing statistics fall back to
all languages pooled for a language with fewer than 200 sentences.

Everything below was measured on dataset S (history of Finland: 29,460 articles) on one laptop CPU,
unless marked otherwise.

## The pipeline at a glance

```mermaid
flowchart TD
  L[wikicross-load: dataset S into MariaDB] --> A[article + article_vector]
  Q[GET /api/diff?title=…] --> T[Topic: editions sharing a wikidata_id]
  A --> T
  T --> E1[Split articles into passages, embed with bge-m3 on demand]
  E1 --> P[Passage matching: mutual nearest across languages, HNSW]
  P --> E2[Split matched passages into sentences, embed on demand]
  E2 --> S[Sentence matching inside each passage pair: exact join]
  S --> G[Group matched sentences across languages: one group per fact]
  G --> F1[Contradictions: each pair translated to English, NLI both ways; most contradicted → outlier]
  G --> F2[Framing: position on semantic axes, furthest edition → outlier]
  F1 --> R[JSON: differences, contradictions first, then framing]
  F2 --> R
  R --> UI[Web page and Chrome extension: quotes side by side, copy, optional AI]
```

Two different questions are answered by two different mechanisms:

| Question | Mechanism | What it never does |
|---|---|---|
| *Are these about the same thing?* (matching) | vector distance: mutual nearest neighbour, under a threshold | flag anything |
| *Do they say it differently?* (flagging) | NLI on English translations; positions on semantic axes | decide what is about the same thing |

Content that only one edition has never finds a partner, so it is never reported: WikiCross is about
disagreement, not omission.

## Data model

```mermaid
erDiagram
  article ||--|| article_vector : "1 vector per article (from the dataset)"
  article ||--o{ chunk : "split into passages"
  chunk ||--o{ sentence : "split into sentences"
  article {
    char lang PK
    int page_id PK
    varchar wikidata_id "same topic across languages"
    varchar title
    mediumtext text
  }
  article_vector {
    vector embedding "VECTOR(1024), HNSW index"
  }
  chunk {
    smallint seq PK
    varchar heading
    text text
    vector embedding "VECTOR(1024), HNSW index"
  }
  sentence {
    smallint n PK
    text text
    vector embedding "VECTOR(1024), no index"
  }
  llm_cache {
    binary k PK "sha256 of model + prompt"
    mediumtext response
  }
```

`chunk` and `sentence` are filled on demand the first time a topic is asked for, then reused.

## One request

```mermaid
sequenceDiagram
  participant B as Browser
  participant API as FastAPI (/api/diff)
  participant DB as MariaDB
  participant O as Ollama (bge-m3)
  B->>API: title=Urho Kekkonen
  API->>DB: editions with the same wikidata_id
  alt passages not embedded yet
    API->>O: embed passages (≈2 per s on CPU)
    API->>DB: INSERT chunk
  end
  loop each passage × each other language
    API->>DB: ORDER BY VEC_DISTANCE_COSINE(...) LIMIT 1 (HNSW)
  end
  alt sentences not embedded yet
    API->>O: embed sentences (≈8 per s on CPU)
    API->>DB: INSERT sentence
  end
  API->>DB: one query: sentence pairs + axis positions (window functions)
  API->>API: group, flag values and framing
  API-->>B: differences
  opt "Show paragraphs", then "Expand up / down" (web page only)
    B->>API: GET /api/context (neighbouring sentences, from the sentence table)
  end
  opt "AI summaries" ticked
    B->>API: POST /api/explain, /api/translate (LLM, cached in llm_cache)
  end
```

## Step by step

### 1. Splitting

- **Passages** (`split()` in `app.py`): consecutive lines merged until ≥300 characters, never across a
  heading. Sections of sources and links (*Lähteet*, *Källor*, *References*…) and "Main article:"
  lines are skipped: they always differ and say nothing.
- **Sentences** (`sentences()`): split at `.!?` followed by a capital letter, quote or bracket; not
  before a digit, so Finnish "3. syyskuuta" and "(k. 1985)" stay whole. Pieces under 30 characters
  join a neighbour in the same line. Table rows and list items are one sentence each.

### 2. Matching

| Level | How | Threshold | Why this way |
|---|---|---|---|
| Article | same `wikidata_id` | — | exact, free |
| Passage | nearest passage in each other language **over the whole corpus** (HNSW), kept if mutual | cosine distance ≤ 0.40 | the counterpart can sit in another article (fi keeps *Talvisodan tausta* apart from *Talvisota*) |
| Sentence | nearest sentence **inside the matched passage pair**, kept if mutual (`ROW_NUMBER()` both ways) | ≤ 0.40 for contradictions, ≤ 0.35 for framing | a passage pair has a few dozen sentence pairs: an exact join beats index lookups |

"Mutual" means each is the other's nearest: one-to-one, so one long English paragraph cannot absorb
three Finnish ones.

### 3. Grouping across languages

Matched sentence pairs that connect (fi–sv, sv–en, pl–de, …) form one **group** per fact, with at
most one sentence per language. Pairs join groups closest first, and only when the two groups have no
language in common: a chain that would reach a second sentence of one language stops there, and that
pair is kept as a group of its own. Example: the three Urho Kekkonen passages on the 1978 election,
with their measured cosine distances:

```mermaid
flowchart LR
  fi["fi: …hän sai … 82 prosenttia äänistä ja 260 valitsijamiestä"] ---|0.324| sv["sv: …fick han 82 procent av rösterna och 260 elektorer"]
  sv ---|0.223| en["en: …went on to win 259 out of the 300 electoral college votes"]
  fi ---|0.313| en
  classDef odd stroke-width:3px
  class en odd
```

Measured: with three languages most groups are still pairs (Urho Kekkonen: 27 three-language groups
and 90 pairs; Winter War: 8 and 37). Voting needs three; the more languages, the more groups have a
majority.

### 4a. Flagging contradictions: discrepancy (`compare.py`, `embed_gpu.py`)

**Off by default** (`CONTRADICTIONS=1` enables it): translating and judging every matched pair takes
minutes on a topic's first load. With it off, no discrepancies are reported and the GPU container
loads bge-m3 only.

No rules about numbers, dates or names: whether two sentences contradict each other is decided by
what they mean.

1. Every matched sentence pair (cosine distance ≤ 0.40) is **translated to English** with M2M100
   (`facebook/m2m100_1.2B`), whose source language codes are the editions' own (`nb` → `no`,
   `sh` → `hr`); the few editions it lacks go through `Helsinki-NLP/opus-mt-mul-en`, which needs no
   code. English sentences are kept as they are.
2. Two **NLI models** (classifiers, not LLMs) score the pair as entailment, neutral or
   contradiction, **both ways round**: `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli`
   on the English translations, `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` on the
   original sentences. The pair contradicts when all four give contradiction at least 0.9 (the
   lowest of the four). The two fail differently: the English one on mistranslations ("carros", tanks,
   as cars), the multilingual one when neither side is English. Different events about the same
   person tend to score high one way only.
3. Each group is a **vote** over its matched pairs: an edition matched with two or more others and
   contradicting at least two thirds of them is the **outlier**, while the outliers are at most a
   third of the group. Otherwise the editions in the contradicting pairs just **differ**.
4. Outliers come first, then by the highest contradiction probability.

Why both: the multilingual model alone compared the original sentences well when one side was
English (sv vs en on the 1968 invasion: 0.00) and badly when neither was (the same sentence, sk vs
sv: 0.98 "contradiction"). Translating first fixes that but adds translation errors: with opus-mt
alone, Talvisota had 200+ contradictions, many of them mistranslations; requiring both models to
agree brought it to 73. Urho Kekkonen kept every real one we found (1927–1931 vs 1927–1932; the
October vs November 1961 note; Karjalainen sent to Moscow vs home to Helsinki).

Translations, NLI scores and anchor embeddings are kept in `translation_cache`, `nli_cache` and
`embedding_cache`, keyed by sha256 of model + text: a recompute after a code change costs no GPU
call.

### 4b. Flagging framing: impartiality (`compare.py`)

Findings from 4a are **discrepancies** (facts disagree, marked red); findings from here are
**impartiality** findings (the same thing described differently, marked amber).

An **axis** is the difference between the mean vectors of two groups of anchor sentences, written in
all three languages so that the language cancels out:

| Axis | Positive end (anchors) | Negative end (anchors) |
|---|---|---|
| evaluation | "a great success, widely praised", "heroic and admirable" | "a disastrous failure, widely condemned", "brutal and shameful" |
| certainty | "a well-documented fact", "confirmed by the records" | "an unconfirmed, disputed claim", "according to some sources … allegedly" |
| wording | "the ruthless aggressor savagely crushed the heroic defenders", "this shameful betrayal" | "the army attacked the positions and both sides suffered casualties", "the agreement was signed in 1940" |

The wording axis is about how, not which side: emotive words in either direction against neutral,
matter-of-fact ones. Urho Kekkonen, its strongest finding: et "Kekkonen võitles Nurmi osalemise eest
visalt ja isegi **ärritavalt jonnakalt**" (tenaciously and even irritatingly stubbornly) against fi's
plain "Kekkonen taisteli Nurmen osallistumisen puolesta", 3.4σ; the AI check, asked about tone,
agreed ("Estonian portrays Kekkonen as irritatingly stubborn").

A sentence's position is $p = 1 - d_{\cos}(s, \text{axis})$, computed in SQL. Languages sit at
slightly different places on every axis, so positions become z-scores against the language's own mean
and spread: $z_\ell = (p - \mu_\ell) / \sigma_\ell$. In a group, each edition's **deviation** is

$$\Delta_\ell = z_\ell - \frac{1}{|G|-1}\sum_{k \in G,\,k \neq \ell} z_k$$

With two editions this is just their difference. The largest $|\Delta|$ over editions and axes is
reported when it is at least 1.2σ; with three or more editions, that edition is the outlier.

**Leaning** (shown by the extension for the page's edition): an edition's mean $\Delta$ per axis over
every matched group it is in, reported or not. Below 0.2σ on every axis it reads as neutral; the
editions with the nearest and furthest such profiles (Euclidean, editions in at least 5 groups) are
the ones it is framed most and least like. Urho Kekkonen, fi: −0.01, −0.06 and +0.17σ, neutral.

### 5. Worked examples (real output)

| Topic | Kind | Editions | Result |
|---|---|---|---|
| Urho Kekkonen | framing, pair, 3.0σ | fi "1978 presidentinvaalit olivat **riemuvoitto**" (a triumph) vs sv "var **enbart ett statspolitiskt skådespel**" (merely a political spectacle) | fi more positive |
| Urho Kekkonen | contradiction, outlier | en "in **October** 1961, the Soviet Union sent a diplomatic note" vs fr "L'URSS envoie **fin novembre** une note de crise" | fr the outlier |
| Urho Kekkonen | contradiction, pair | en "worked for the Association of Rural Municipalities **until 1932**" vs sv "arbetade han **från 1927 till 1931** för Maalaiskuntien liitto" | differ |
| Urho Kekkonen | contradiction, pair | fi "lähetti ulkoministeri Ahti Karjalaisen **Moskovaan**" vs sv "skickade … Ahti Karjalainen … **hem till Helsingfors**" | differ |

With every Latin- and Cyrillic-script edition (55), Urho Kekkonen gives 20 contradictions, about 8
of them real by our reading. The rest are one place under two names (Ekudden and Tamminiemi,
Sandudd and Hietaniemi) or two events matched as one fact (appointed Minister of Justice in 1936 vs
1944). The number rules this replaced paired figures that were different facts (684 Soviet planes
shot down vs 146 Finnish planes at the start of the war), and could not see a changed date or place.

## Measured cost

| What | Measured |
|---|---|
| Passage matching, HNSW (Winter War: 266 passages; Kekkonen) | 0.45 s; 0.21 s |
| Sentence matching, exact join inside passage pairs (Kekkonen, 183 pairs) | 0.01 s |
| Same alignment with one HNSW lookup per sentence (Winter War, 2,652 lookups) | 3.68 s vs 0.11 s for the join |
| Whole `/api/diff` once embedded (Kekkonen; Winter War) | 0.25 s; 0.50 s |
| Translation to English, M2M100 1.2B on an H100, 2 beams (2,048 sentences, 7 languages) | 58 s |
| Contradiction check on a cached topic (translations and NLI scores in the DB; Kekkonen) | 14 s for the whole `/api/diff` recompute |
| Embedding with Ollama on CPU | ≈2 passages/s, ≈8 sentences/s |
| Dataset S, topics in ≥2 languages | 17,431 articles → 149,524 passages, 594,025 sentences |

Per article that is about **8.6 passages and 34 sentences**, i.e. about 43 vectors of 4 KB.

## Design decisions and tradeoffs

| Decision | Chosen | Alternative | Why |
|---|---|---|---|
| Who judges "different" | NLI classifier on English translations + semantic axes | LLM per pair; rules about numbers | an LLM call per matched pair is 35–60 calls per article; number rules (the first version) missed names, dates and outcomes and paired unrelated figures; one NLI batch scores thousands of pairs in seconds |
| Granularity | sentence | passage | NLI on whole passages mixes facts; sentences pin one fact |
| Matching rule | mutual nearest + threshold | nearest only | one-to-one: a long paragraph cannot match everything |
| Passage search | HNSW over the whole corpus | exact join within the topic | finds counterparts in other articles; stays fast as the corpus grows |
| Sentence search | exact join within passage pairs | HNSW | measured 0.11 s vs 3.68 s; exact; no index to maintain on the largest table |
| Language bias on axes | per-language z-scores, anchors in every language | raw positions | raw positions differ per language before any content does |
| Cross-language NLI | translate both sides to English, then an English NLI model | multilingual NLI on the originals | multilingual NLI called near-translations contradictory when neither side was English |
| Embedding | on demand, cached | precomputed | no upfront job for a demo; `TODO.md` describes the precompute |

## Limitations

- **Only contradictions and tone.** Facts only one edition states are never reported (no partner).
- **Framing is noisy.** Strong hits (≥2σ) are usually real; around 1.2–1.5σ, many are
  wording differences (Urho Kekkonen: 11 framing findings, the top 3 convincing).
- **Three axes.** Others (blame/agency, nationalist vs neutral framing) would need their own anchors
  and checking. The wording axis also fires on sentences that differ in a fact rather than in tone
  ("largest" vs "second largest" national park).
- **Thresholds are tuned on two articles** (Winter War, Urho Kekkonen).
- **Translation errors.** Where both models fail together (a small language translated poorly, and
  neither side English), near-identical sentences can still read as contradicting. M2M100 covers
  100 languages; others fall back to opus-mt, which is weaker.
- **Different events of one subject.** "Appointed Minister of Justice in 1936" vs "joined the
  government in 1950" can still score as a contradiction when matched as one fact.

## Scaling to more languages

What carries over unchanged: bge-m3 covers 100+ languages in one vector space, so matching works as
is; z-scores are per language, so a new language gets its own baseline from its own data.

What needs work:

| Piece | Today | With more languages |
|---|---|---|
| Language list | `LANGS` in `compare.py`, the loader, the page | from the data |
| Sentence splitter | `.!?` + an uppercase letter of any alphabet (Latin, Cyrillic) or an opening quote/bracket | per script: CJK `。`, Arabic `؟`, Thai has no sentence punctuation |
| Translation | M2M100 from the edition's code, opus-mt for the rest | NLLB-200 covers 200 languages, with its own codes (`fin_Latn`): a mapping table |
| Axis anchors | fi, sv, en | add anchors in each language; check each axis per language |
| Passage lookups | 2 per passage | L−1 per passage, plus reverse lookups for mutuality |

**Groups get better with more languages.** Pairwise comparison grows as $L(L-1)/2$ language pairs (45
for 10 languages); groups need one sentence per language per fact, and a majority vote says *which*
edition is the outlier. With three languages a majority is rare (most groups are pairs); with ten,
most facts are covered several times.

```mermaid
flowchart LR
  subgraph "3 languages: mostly pairs"
    a1[fi] --- a2[sv]
  end
  subgraph "many languages: groups with a majority"
    b1[fi 126 875] --- b2[sv 126 875]
    b2 --- b3[de 126 875]
    b3 --- b4[en 167,976]
    b1 --- b5[et 126 875]
  end
```

**Risk to check before adding many languages: filtered HNSW.** Passage lookups filter by language
(`WHERE lang = %s ORDER BY VEC_DISTANCE_COSINE(...) LIMIT 1`). MariaDB served this from the vector
index with a filter during the scan (`EXPLAIN`: `key: embedding`, `Using where`). With three
languages a third of all passages pass the filter; with 300 languages, a fraction of a percent does,
and the index may need to visit far more nodes to find one. Untested here; options are one table (and
index) per language, or one per group of languages, and measuring recall against the exact join.

## Scaling to all of Wikipedia

Run it as a batch job, not on request:

```mermaid
flowchart LR
  D[Dumps / FineWiki per language] --> K[Topics with ≥2 editions, via wikidata_id]
  K --> W1[Workers, one topic at a time]
  W1 --> EMB[GPU embedding: passages, sentences]
  EMB --> DB[(MariaDB: chunk with HNSW)]
  W1 --> CMP[Match, group, flag]
  DB --> CMP
  CMP --> FT[(findings table)]
  FT --> UI[Web page reads findings only]
  REV[New revisions, rev_id changed] --> W1
```

- **Topics are independent.** Everything after embedding works on one `wikidata_id` at a time, so it
  parallelises across workers; only the passage search touches the whole corpus, and that is an index
  lookup.
- **Only topics with ≥2 editions** need passages and sentences at all.
- **Embedding dominates.** At the measured CPU rates one article costs about $8.6/2 + 34/8 \approx 8.6$
  s; per million articles that is about 100 CPU-days. A GPU is required; its throughput was not
  measured here.
- **Storage**, at about 43 vectors of 4 KB per article: about 175 GB per million articles, ~80 % of it
  sentence vectors. Sentence vectors are only needed while aligning, so a batch job can embed,
  align, flag and discard them, keeping only passages (~35 GB per million articles) and findings.
- **HNSW memory.** The passage index must fit the server's vector-index cache to stay fast; size the
  MariaDB vector index cache for it (not measured here).
- **Framing statistics** (`axis_stats()`) are computed today by scanning every sentence once per
  process; at scale, compute them once per bulk load and store them in a table.
- **Updates.** Re-embed and re-compare only what changed: see the next section.
- **The LLM stays optional.** At scale it is best used to verify the top findings per topic (a few
  per topic), not every matched pair.

## Recomputing embeddings when an article changes

Articles are edited all the time; the stored vectors describe the text they were made from.

**Today nothing detects a change.** `ensure_chunks()` and `ensure_sentences()` only check whether an
article has rows at all, and the loader keeps no revision (`rev_id` is in the dataset files but not
loaded). Loading newer text with `wikicross-load` replaces `article` but leaves the old passages,
sentences and vectors in place: findings would quote text that no longer exists. Until the steps
below exist, after reloading changed text: `DELETE FROM chunk` / `sentence` for those articles (or
`TRUNCATE` both).

**What goes stale when one edition of a topic changes:**

| What | Stale? | Why |
|---|---|---|
| That article's `chunk` and `sentence` rows | the edited passages | their text changed |
| Findings of its topic | yes | they quote and compare the old text |
| Findings of *other* topics | sometimes | a passage of this article may have been the cross-article counterpart of a passage elsewhere (HNSW search over the whole corpus) |
| `article_vector` | yes, if used | one vector of the whole old text |
| Framing statistics | negligibly | per-language means over millions of sentences barely move |
| `llm_cache` | no action | keyed by the text: new text simply misses the cache |

**Recompute incrementally, by content hash.** An edit usually touches a few paragraphs, so the cost
should follow the size of the edit, not of the article:

```mermaid
flowchart TD
  E[Change seen: new rev_id for lang, page_id] --> D{Debounce: last change > N minutes ago?}
  D -->|no| W[wait: articles are often edited several times in a row]
  D -->|yes| S[Fetch text, split into passages and sentences]
  S --> H[sha256 of each passage and sentence text]
  H --> R{Hash already stored for this article?}
  R -->|yes| K[Reuse the stored vector]
  R -->|no| M[Embed: only new or edited text]
  K --> X[In one transaction: replace the article's chunk and sentence rows, store rev_id]
  M --> X
  X --> C[Re-run comparison for its topic]
  X --> O[Re-run topics whose findings referenced this article's passages]
  C --> F[(findings)]
  O --> F
```

What that needs:

1. **Store the revision**: a `rev_id` column in `article` (the dataset already has it) and the
   `rev_id` each article's rows were made from, so "stale" is a comparison, not a guess.
2. **Store a content hash** per passage and sentence (`sha256(text)`, `BINARY(32)`). Positions shift
   when a paragraph is inserted, so rows are matched by hash, not by `seq`. Rewrite an article's rows
   in one transaction (delete, insert with reused or new vectors) so a reader never sees half of it.
3. **Track who used a passage**: findings store the `(lang, page_id, seq)` of every member, so the
   topics to recompute after an edit are one query away, including cross-article matches.
4. **A change feed**: Wikimedia's EventStreams (revision events, near real time) for live updates, or
   a diff of `rev_id` between two dumps / FineWiki snapshots for periodic batches.

Cost of one edit: embedding the changed passages and sentences (≈0.5 s per passage, ≈0.13 s per
sentence on the measured CPU), a few HNSW lookups per changed passage, and one comparison of the
topic (0.25–0.5 s measured). MariaDB keeps the HNSW index on `chunk` up to date on every insert and
delete; whether heavy churn degrades its recall over time was not measured here; if it does, rebuild
the index periodically.
