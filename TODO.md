# TODO

## Recompute embeddings when articles change

Nothing detects changed text today: `ensure_chunks()`/`ensure_sentences()` only check that rows
exist, and a topic's editions are fetched once with no `rev_id`. To refresh a topic, delete its rows
by hand (see the doc below).
The incremental design (rev_id, content hashes, change feed, recomputing
affected topics) is in [docs/how-it-works.md](docs/how-it-works.md#recomputing-embeddings-when-an-article-changes).
