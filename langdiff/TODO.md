# TODO

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

**Time:** measured with Ollama on this machine's CPU: ~2 parts/s and ~8 sentences/s, so ~21 h of
parts plus ~21 h of sentences for the 2-language set. A GPU is much faster; measure on the first
100 articles before committing to a full run.

### Steps

1. **Prerequisites:** MariaDB up and loaded (`docker compose up -d --wait`, `uv run langdiff-load`),
   Ollama with `bge-m3`. Check `ollama ps` shows `GPU` under PROCESSOR, not `100% CPU`. To embed on
   another machine, point `OLLAMA_URL` at its Ollama; the database stays here.

2. **Make the per-article insert atomic.** `ensure_chunks()` and `ensure_sentences()` treat an
   article as done as soon as it has one row; a run stopped in the middle of an `executemany` leaves
   a half-embedded article that is never finished. Run each `INSERT` in a transaction
   (`conn.begin()` … `conn.commit()`; the connection is autocommit) so an article is either complete
   or absent.

3. **Add `src/langdiff/precompute.py`** with a `main()` and register it in `pyproject.toml` under
   `[project.scripts]` as `langdiff-precompute = "langdiff.precompute:main"`. It should:
   - Select the articles still to do — the query is resumable by itself:
     ```sql
     SELECT a.lang, a.page_id, a.text FROM article a
     WHERE a.wikidata_id IN (SELECT wikidata_id FROM article GROUP BY wikidata_id HAVING COUNT(*) >= 2)
       AND NOT EXISTS (SELECT 1 FROM chunk c WHERE c.lang = a.lang AND c.page_id = a.page_id)
     ```
     With `--all-three`, use `HAVING COUNT(*) = 3`.
   - Call the existing `ensure_chunks(cur, lang, page_id, text)` then `ensure_sentences(cur, lang,
     page_id)` for each one; no second copy of the splitting or embedding code.
   - Run `--workers N` threads (default 1), **one DB connection per thread** (pymysql connections
     are not thread-safe). Start Ollama with `OLLAMA_NUM_PARALLEL=N` so the requests really run in
     parallel.
   - Print progress every 100 articles: done / total, parts per second, estimated time left.

4. **Run it**, safe to stop and restart at any time:
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
