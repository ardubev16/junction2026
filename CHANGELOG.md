# Changelog

## [1.0.0](https://github.com/ardubev16/junction2026/compare/v0.1.0...v1.0.0) (2026-11-25)


### ⚠ BREAKING CHANGES

* DECISION_API_KEY is required; /api/diff no longer takes ai= nor returns findings' ai.

### Features

* a decision model judges every finding: false positives never shown, kinds counted and filtered, strongest first ([a820f11](https://github.com/ardubev16/junction2026/commit/a820f11c0b09b5b00cc42b641ed3053ff98d821c))
* add challenge submodules ([227e34e](https://github.com/ardubev16/junction2026/commit/227e34e1ceb4d725f515e1f7fd8f47d31410e560))
* Azure AI Translator translates the snippets instead of the LLM ([b030968](https://github.com/ardubev16/junction2026/commit/b03096826933137b6eed4b16fbeea743b3ba3581))
* **compare:** statements most editions make are candidates, judged on their most different quotes; pairs sharing a sentence shown as one card ([074068b](https://github.com/ardubev16/junction2026/commit/074068b394eb85df5e2a8b1225e60b6003ca0ca7))
* **decide:** the decision model names the outlier; dialects hidden by default; /about served ([348bb8b](https://github.com/ardubev16/junction2026/commit/348bb8b33b76cb16c9f0729119cc5ff082a25df6))
* later pages and the extension ask the AI per card, as it nears the view ([17cc00b](https://github.com/ardubev16/junction2026/commit/17cc00b32d71bdbe006133a777e64ecc1db2e7dc))
* LLM configured by four required settings; .env.example ([301c9c5](https://github.com/ardubev16/junction2026/commit/301c9c563b8a00d6fad1c437adb3ef1f4049b805))
* named profile runs; --fresh also makes the LLM calls; make check / fix ([f799d39](https://github.com/ardubev16/junction2026/commit/f799d39a98a6b1f6fdd114d284ce0d765f3b7c19))
* OpenTelemetry traces and metrics in the deployment ([d65b0db](https://github.com/ardubev16/junction2026/commit/d65b0db0c95d88b6217bbf7bbda0f457221da3e2))
* scripts/profile.py profiles a new article's pipeline with VizTracer ([c5883d8](https://github.com/ardubev16/junction2026/commit/c5883d8365b984d254d2ba855906299c8d28d3d4))
* the server makes every AI call; loading times all from the server ([bda89d7](https://github.com/ardubev16/junction2026/commit/bda89d72f8c25e070e455819cbcfa1fa7399856f))
* **ui:** filters as a Wikipedia Appearance-style panel on the left; Wikipedia's languages button ([c1d5ea6](https://github.com/ardubev16/junction2026/commit/c1d5ea61b3f7f41d8ab8cfcd7f9cf05bca6d5420))
* **ui:** seconds per loading step and in total, AI step in the web app; retry dropped requests ([79fcedf](https://github.com/ardubev16/junction2026/commit/79fcedf2c463a93fa3c4b157bb6ee1a9e223da06))
* **ui:** the decision model's numbers in the info popup, an About page and footer, Wikimedia alignment ([78d853c](https://github.com/ardubev16/junction2026/commit/78d853cd01f9c161e885128e2fa65b45c091f6a3))
* **ui:** the loading view lists the comparison's steps and checks each one off ([f2c0e17](https://github.com/ardubev16/junction2026/commit/f2c0e1777b037a62a19faadd4e2ec73ebe88d87f))
* **ui:** use Codex, the Wikimedia design system ([1e10290](https://github.com/ardubev16/junction2026/commit/1e10290c98b5b04bf3dbbd8dd9c753a499143fc4))
* what the other editions say about a factual disagreement ([ec5b62e](https://github.com/ardubev16/junction2026/commit/ec5b62e991aae4934382333f0851feade2879cd7))


### Bug Fixes

* **ai:** findings need a shared subject visible in the quotes; highlights survive other models; evals ([7d008f0](https://github.com/ardubev16/junction2026/commit/7d008f0c4714bcbef6b902dab5606ed4292039c7))
* **api:** bounded LLM requests, more worker threads, one indexing per topic; rate limit optional ([37d15a1](https://github.com/ardubev16/junction2026/commit/37d15a15925be8f4e83e021dddfc74f96fadff3a))
* Azure Translator gets each text's language; the LLM for languages Azure lacks, logged and counted ([ce38d5c](https://github.com/ardubev16/junction2026/commit/ce38d5c1d4892df568639c607bd6f9b6216c4e43))
* **compare:** never split a sentence inside brackets; re-split stale pages; bias regression topics ([d5910b0](https://github.com/ardubev16/junction2026/commit/d5910b0e7d6a1050bf4ff18c0a3bcc59ba968ceb))
* **ui:** a failed quote translation is not retried in a loop ([1eee9a0](https://github.com/ardubev16/junction2026/commit/1eee9a0e7784d67e429a15ef3a84b83df2a8967c))


### Documentation

* **about:** define factual disagreement, bias and framing ([96e49a3](https://github.com/ardubev16/junction2026/commit/96e49a3cf15a61330468da91d6e074948807b359))
* experiments log (docs/experiments/) and the detection threshold analysis ([9b2d09f](https://github.com/ardubev16/junction2026/commit/9b2d09fc31e38dba9b8644d3d73a390b375693ae))
* **experiments:** bias and framing on Shelling of Mainila, quick matching ideas on Modal (masking, instruction embeddings, questions) ([b902cb4](https://github.com/ardubev16/junction2026/commit/b902cb4facc5d774373c4cfd32128c9dbfdbc983))
* **experiments:** outlier and same-thing variants, CI fixture storage, ideas for matching ([052dc27](https://github.com/ardubev16/junction2026/commit/052dc27e9abe9138b6383f68c2ea4a30a0879c54))
* license under GPL-3.0-or-later ([61bbc33](https://github.com/ardubev16/junction2026/commit/61bbc33cce53ac1573b2bf65d7c5095466011e6c))
* README cut to a reference (326 -&gt; 129 lines) ([63b0857](https://github.com/ardubev16/junction2026/commit/63b0857e6168c7f1e6ecdd6d645ac9c5f21ff436))
* **todo:** a MariaDB fixture image on GHCR for CI's evals ([864e688](https://github.com/ardubev16/junction2026/commit/864e6886c80a6baa4686c3429293e227b7e30523))
* **todo:** staying under Wikimedia's API rate limits ([3dd7c27](https://github.com/ardubev16/junction2026/commit/3dd7c27a06b7f522451d6ab7471f07dc24836a14))
