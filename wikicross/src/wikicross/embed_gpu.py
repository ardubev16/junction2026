"""bge-m3, an English NLI model and a translator to English on a Modal H100. Deploy with
`uv run modal deploy src/wikicross/embed_gpu.py`.

Runs in Modal's cloud, not in the web app: `embeddings` looks the deployed class up by name.
"""

import modal

MODEL = "BAAI/bge-m3"  # the model the dataset's vectors were made with
# Two NLI judges with different failure modes; a pair contradicts only when both say so:
# - English, on both sides translated to English: misled by mistranslations ("carros" as cars, not tanks).
# - multilingual, on the original sentences: misled when neither side is English (it called the same
#   statement in Slovak and Swedish a contradiction).
NLI = "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
NLI_MULTI = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
# To English. M2M100 takes the source language as an ISO 639-1 code, which is the edition's own code;
# the few editions it lacks go through opus-mt, which needs none but translates small languages
# poorly (Asturian, Indonesian: near-identical sentences read as contradicting each other).
MT = "facebook/m2m100_1.2B"
MT_FALLBACK = "Helsinki-NLP/opus-mt-mul-en"
MT_CODES = {"nb": "no", "nn": "no", "be-tarask": "be", "sh": "hr", "simple": "en"}  # edition -> M2M100 code
APP = "wikicross-embed"

app = modal.App(APP)
weights = modal.Volume.from_name("wikicross-hf-cache", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("sentence-transformers>=5", "torch>=2.7", "sentencepiece")
    .env({"HF_HOME": "/cache"})
)


@app.cls(gpu="H100", image=image, volumes={"/cache": weights}, scaledown_window=300, max_containers=1)
class Embedder:
    @modal.enter()
    def load(self):
        import torch
        from sentence_transformers import CrossEncoder, SentenceTransformer

        self.model = SentenceTransformer(MODEL, device="cuda", model_kwargs={"torch_dtype": torch.float16})
        self.model.max_seq_length = 8192  # bge-m3's limit; longer texts are truncated, as Ollama did
        self.nli = {name: CrossEncoder(name, device="cuda", max_length=512) for name in (NLI, NLI_MULTI)}
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        self.mt = {name: (AutoTokenizer.from_pretrained(name),
                          AutoModelForSeq2SeqLM.from_pretrained(name, dtype=torch.float16).to("cuda").eval())
                   for name in (MT, MT_FALLBACK)}
        weights.commit()
        # The first encode of each batch shape is slow (~2.5 s for an article's sentences, then 0.2 s):
        # pay it here, before the container takes requests.
        self.model.encode([" ".join(["sana"] * n) for n in (4, 16, 64, 256, 1024) for _ in range(64)], batch_size=64)

    @modal.method()
    def embed(self, texts: list[str]) -> list[bytes]:
        """Normalised dense vectors (CLS pooling) as MariaDB VECTOR values (little-endian float32)."""
        vectors = self.model.encode(texts, batch_size=64, normalize_embeddings=True, convert_to_numpy=True)
        return [v.astype("<f4").tobytes() for v in vectors]

    @modal.method()
    def contradiction(self, pairs: list[tuple[str, str]], model: str) -> list[float]:
        """For each (premise, hypothesis), the probability that the hypothesis contradicts the premise,
        by NLI or NLI_MULTI."""
        nli = self.nli[model]
        contra = next(i for i, label in nli.model.config.id2label.items() if label.lower() == "contradiction")
        probs = nli.predict(pairs, batch_size=128, apply_softmax=True, convert_to_numpy=True)
        return [float(p[contra]) for p in probs]

    @modal.method()
    def to_english(self, items: list[tuple[str, str]]) -> list[str]:
        """Each (edition code, text) translated to English, by M2M100 from that language if it has it,
        else by opus-mt."""
        import torch

        tok = self.mt[MT][0]
        jobs: dict[tuple[str, str | None], list[int]] = {}  # (model, source code) -> item positions
        for k, (lang, _) in enumerate(items):
            code = MT_CODES.get(lang, lang)
            jobs.setdefault((MT, code) if code in tok.lang_code_to_id else (MT_FALLBACK, None), []).append(k)
        out = [""] * len(items)
        for (name, code), positions in jobs.items():
            tok, model = self.mt[name]
            gen = {}
            if code:
                tok.src_lang = code
                gen["forced_bos_token_id"] = tok.get_lang_id("en")
            positions.sort(key=lambda k: len(items[k][1]))  # similar lengths per batch: little padding
            for i in range(0, len(positions), 128):
                part = positions[i : i + 128]
                batch = tok([items[k][1] for k in part], return_tensors="pt", padding=True, truncation=True, max_length=256).to("cuda")
                with torch.no_grad():  # a looping output would hold its whole batch to 256 tokens
                    ids = model.generate(**batch, num_beams=2, repetition_penalty=1.2,
                                         max_new_tokens=min(256, 2 * batch["input_ids"].shape[1] + 16), **gen)
                    done = tok.batch_decode(ids, skip_special_tokens=True)
                for k, text in zip(part, done):
                    out[k] = text
        return out

    @modal.method()
    def token_counts(self, texts: list[str]) -> list[int]:
        """Tokens per text as bge-m3 reads it, special tokens included: more than 8192 means truncated."""
        return [len(ids) for ids in self.model.tokenizer(texts, add_special_tokens=True)["input_ids"]]
