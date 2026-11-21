# TODO

## Recompute embeddings when articles change

Nothing detects changed text today: `ensure_chunks()`/`ensure_sentences()` only check that rows
exist, and a topic's editions are fetched once with no `rev_id`. To refresh a topic, delete its rows
by hand (see the doc below).
The incremental design (rev_id, content hashes, change feed, recomputing
affected topics) is in [docs/how-it-works.md](docs/how-it-works.md#recomputing-embeddings-when-an-article-changes).

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
