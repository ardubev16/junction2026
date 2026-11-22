# TODO

## Recompute embeddings when articles change

Nothing detects changed text today: `ensure_chunks()`/`ensure_sentences()` only check that rows
exist, and a topic's editions are fetched once with no `rev_id`. To refresh a topic, delete its rows
by hand (see the doc below).
The incremental design (rev_id, content hashes, change feed, recomputing
affected topics) is in [docs/how-it-works.md](docs/how-it-works.md#recomputing-embeddings-when-an-article-changes).

## A database fixture for CI's evals

The yield eval on CI starts from an empty database: it fetches the reference topics from Wikipedia and
embeds them on Modal (minutes, GPU cost, Wikipedia requests) before measuring anything. Instead, publish
a MariaDB image with those topics loaded, `ghcr.io/ardubev16/wikicross-evaldb:<date>`, and use it as the
job's `services.mariadb.image`:

- a workflow (on demand) dumps the reference topics' rows (`article`, `chunk`, `sentence`,
  `topic_editions`, `embedding_cache`, and the decision model's rows in `llm_cache`) and builds the image
  from `mariadb:lts`, the dump in `/docker-entrypoint-initdb.d/` (or the data directory baked in, for a
  faster start);
- ~100 MB of vectors (4 KB × ~27k, float32 barely compresses); free as a public GHCR package, pushed with
  `GITHUB_TOKEN` like the app image;
- rebuilt when the embedding model, the chunking or the reference topics change.

Alternatives weighed in [docs/experiments](docs/experiments/2026-11-detection-thresholds.md#ci-without-modal):
a release asset (a restore on every run), the Actions cache (evicted after 7 days), Git LFS (1 GB a
month), Hugging Face or R2 (another account).

## Stay under Wikimedia's API rate limits

Since 2026 Wikimedia limits API clients per minute across all wikis
([rate limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits)): 200 requests/min for an
identified client (our `wiki.UA`), 2000 for an authenticated established editor, none for a bot-flagged
account or Toolforge; 3 or fewer requests in flight are recommended. A new topic costs one request per
edition plus one (127 editions: 128), fetched `wiki.FETCHERS` = 8 at a time, and two readers loading new
topics at once add up; `wiki.api()` only waits out the 429s. In order of cost:

1. `FETCHERS` = 3, as recommended (a slower first load; the 429 waits already cost more).
2. One limiter per process for all requests (a token bucket under 200/min), not per request.
3. Authenticate: an OAuth 2 client-credentials app (owner-only tokens do not count for the new limits);
   2000/min from an established editor's account, unlimited with a bot flag.
4. Fetch only changed editions: store each article's `lastrevid` and refetch when it changed (see above).
5. Preload popular topics from dumps (Wikimedia Enterprise HTML dumps, or its free API tier) so live
   fetches are for new topics only.
6. Fetch the largest editions first and the rest in the background, showing results before every
   edition is in.
