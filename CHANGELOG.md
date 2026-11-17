# Changelog

## [0.2.0](https://github.com/ardubev16/junction2026/compare/v0.1.0...v0.2.0) (2026-11-17)


### Features

* add challenge submodules ([227e34e](https://github.com/ardubev16/junction2026/commit/227e34e1ceb4d725f515e1f7fd8f47d31410e560))
* Azure AI Translator translates the snippets instead of the LLM ([b030968](https://github.com/ardubev16/junction2026/commit/b03096826933137b6eed4b16fbeea743b3ba3581))
* later pages and the extension ask the AI per card, as it nears the view ([17cc00b](https://github.com/ardubev16/junction2026/commit/17cc00b32d71bdbe006133a777e64ecc1db2e7dc))
* LLM configured by four required settings; .env.example ([301c9c5](https://github.com/ardubev16/junction2026/commit/301c9c563b8a00d6fad1c437adb3ef1f4049b805))
* named profile runs; --fresh also makes the LLM calls; make check / fix ([f799d39](https://github.com/ardubev16/junction2026/commit/f799d39a98a6b1f6fdd114d284ce0d765f3b7c19))
* OpenTelemetry traces and metrics in the deployment ([d65b0db](https://github.com/ardubev16/junction2026/commit/d65b0db0c95d88b6217bbf7bbda0f457221da3e2))
* scripts/profile.py profiles a new article's pipeline with VizTracer ([c5883d8](https://github.com/ardubev16/junction2026/commit/c5883d8365b984d254d2ba855906299c8d28d3d4))
* the server makes every AI call; loading times all from the server ([bda89d7](https://github.com/ardubev16/junction2026/commit/bda89d72f8c25e070e455819cbcfa1fa7399856f))
* **ui:** seconds per loading step and in total, AI step in the web app; retry dropped requests ([79fcedf](https://github.com/ardubev16/junction2026/commit/79fcedf2c463a93fa3c4b157bb6ee1a9e223da06))
* **ui:** the loading view lists the comparison's steps and checks each one off ([f2c0e17](https://github.com/ardubev16/junction2026/commit/f2c0e1777b037a62a19faadd4e2ec73ebe88d87f))
* **ui:** use Codex, the Wikimedia design system ([1e10290](https://github.com/ardubev16/junction2026/commit/1e10290c98b5b04bf3dbbd8dd9c753a499143fc4))


### Bug Fixes

* **api:** bounded LLM requests, more worker threads, one indexing per topic; rate limit optional ([37d15a1](https://github.com/ardubev16/junction2026/commit/37d15a15925be8f4e83e021dddfc74f96fadff3a))
* Azure Translator gets each text's language; the LLM for languages Azure lacks, logged and counted ([ce38d5c](https://github.com/ardubev16/junction2026/commit/ce38d5c1d4892df568639c607bd6f9b6216c4e43))
* **ui:** a failed quote translation is not retried in a loop ([1eee9a0](https://github.com/ardubev16/junction2026/commit/1eee9a0e7784d67e429a15ef3a84b83df2a8967c))


### Documentation

* license under GPL-3.0-or-later ([61bbc33](https://github.com/ardubev16/junction2026/commit/61bbc33cce53ac1573b2bf65d7c5095466011e6c))
* README cut to a reference (326 -&gt; 129 lines) ([63b0857](https://github.com/ardubev16/junction2026/commit/63b0857e6168c7f1e6ecdd6d645ac9c5f21ff436))
