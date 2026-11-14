# TODO

## Recompute embeddings when articles change

Nothing detects changed text today: `ensure_chunks()`/`ensure_sentences()` only check that rows
exist, and `rev_id` is not loaded. After loading newer text, delete that article's `chunk` and
`sentence` rows by hand. The incremental design (rev_id, content hashes, change feed, recomputing
affected topics) is in [docs/how-it-works.md](docs/how-it-works.md#recomputing-embeddings-when-an-article-changes).

## Precompute the part and sentence embeddings

Today an article's parts and sentences are embedded with bge-m3 the first time someone asks for it
(`ensure_chunks()`, `ensure_sentences()` in `src/langdiff/app.py`): 1.5–4 minutes per article on a
CPU. Precomputing makes every request take well under a second (measured: 0.24 s for Urho Kekkonen
once embedded). It also makes the passage search over the whole corpus (HNSW on `chunk`) find
counterparts in other articles, which it can only do among articles already embedded.

**What to embed:** only articles whose topic exists in at least two languages; a part of a
single-language article has nothing to be compared with.

| Scope | Topics | Articles | Parts | Sentences (measured with `split()`, `sentences()`) |
|---|---|---|---|---|
| fi + sv + en | 2,919 | 8,757 | 96,012 | 386,116 |
| at least 2 languages | 7,256 | 17,431 | 149,524 | 594,025 |

About 3 GB of vectors ((149,524 + 594,025) × 1024 × 4 bytes) for the second line.

**Time:** measured with Ollama on a laptop CPU: ~2 parts/s and ~8 sentences/s, so ~21 h of parts plus
~21 h of sentences for the 2-language set. On the Modal H100, warm: 121 parts in 0.1 s and 562
sentences in 0.2 s of GPU time (Talvisota, fi), so the run is bound by the database and the
per-call overhead (~0.5 s). Measure on the first 100 articles before committing to a full run.

### Steps

1. **Prerequisites:** MariaDB up and loaded (`docker compose up -d --wait`, `uv run langdiff-load`),
   the embedder deployed (`uv run modal deploy src/langdiff/embed_gpu.py`). The database stays here;
   only the texts go to Modal.

2. **Add `src/langdiff/precompute.py`** with a `main()` and register it in `pyproject.toml` under
   `[project.scripts]` as `langdiff-precompute = "langdiff.precompute:main"`. It should:
   - Select the articles still to do — the query is resumable by itself:
     ```sql
     SELECT a.lang, a.page_id, a.text FROM article a
     WHERE a.wikidata_id IN (SELECT wikidata_id FROM article GROUP BY wikidata_id HAVING COUNT(*) >= 2)
       AND NOT EXISTS (SELECT 1 FROM chunk c WHERE c.lang = a.lang AND c.page_id = a.page_id)
     ```
     With `--all-three`, use `HAVING COUNT(*) = 3`.
   - Call the existing `ensure_chunks(cur, [(lang, page_id, text), …])` then `ensure_sentences(cur,
     [(lang, page_id), …])` on batches of articles (each makes one Modal call and inserts in one
     transaction); no second copy of the splitting or embedding code.
   - Run `--workers N` threads (default 1), **one DB connection per thread** (pymysql connections
     are not thread-safe). `Embedder` is capped at `max_containers=1`; raise it for more parallel
     H100s, at that cost.
   - Print progress every 100 articles: done / total, parts per second, estimated time left.

3. **Run it**, safe to stop and restart at any time:
   ```bash
   uv run langdiff-precompute --all-three --workers 4   # the 2,919 topics in all three languages first
   uv run langdiff-precompute --workers 4               # then the rest
   ```

5. **Verify:**
   ```sql
   SELECT COUNT(*) FROM (SELECT DISTINCT lang, page_id FROM chunk) t;      -- 8,757, then 17,431
   SELECT COUNT(*) FROM (SELECT DISTINCT lang, page_id FROM sentence) t;   -- the same
   ```
   and `curl 'localhost:8000/api/diff?title=Talvisota'` answers in well under a second.

### Keep in mind

- **Changing the splitting** (`MIN_CHARS`, `SKIP`, `HATNOTE`, `split()`, `sentences()`) makes the
  stored rows stale: `TRUNCATE chunk` and/or `sentence` and run again. Cached LLM answers
  (`llm_cache`) are keyed by the text, so they simply stop matching.
- **Store the framing statistics.** `axis_stats()` in `compare.py` computes each language's mean
  and spread on every axis once per process, over the whole `sentence` table: a full scan that is
  fine for thousands of sentences, not for 594,000. Compute them once after the bulk load and keep
  them in a small table.
- **Share the result** instead of recomputing it: export `chunk` and `sentence` to Parquet, like
  the dataset's own vector files, and teach `langdiff-load` to load them.
- **Do not precompute the LLM summaries** with the current key: they are capped by the provider's
  request limits. They are cached in `llm_cache` as people use the app.
