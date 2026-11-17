"""bge-m3 on a Modal H100. Deploy with `uv run modal deploy src/wikicross/embed_gpu.py`.

Runs in Modal's cloud, not in the web app: `embeddings.embed()` looks the deployed class up by name.
"""

import modal

MODEL = "BAAI/bge-m3"  # multilingual, one vector space for every edition
APP = "wikicross-embed"

app = modal.App(APP)
weights = modal.Volume.from_name("wikicross-hf-cache", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("sentence-transformers>=5", "torch>=2.7")
    .env({"HF_HOME": "/cache"})
)


@app.cls(gpu="H100", image=image, volumes={"/cache": weights}, scaledown_window=300, max_containers=1)
class Embedder:
    @modal.enter()
    def load(self) -> None:
        # Only in the Modal image, not installed locally: imported here, in the container.
        import torch  # noqa: PLC0415  # ty: ignore[import-not-found]
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415  # ty: ignore[import-not-found]

        self.model = SentenceTransformer(MODEL, device="cuda", model_kwargs={"torch_dtype": torch.float16})
        self.model.max_seq_length = 8192  # bge-m3's limit; longer texts are truncated, as Ollama did
        weights.commit()
        # The first encode of each batch shape is slow (~2.5 s for an article's sentences, then 0.2 s):
        # pay it here, before the container takes requests.
        self.model.encode([" ".join(["sana"] * n) for n in (4, 16, 64, 256, 1024) for _ in range(64)], batch_size=64)

    @modal.method()
    def embed(self, texts: list[str]) -> list[bytes]:
        """Normalised dense vectors (CLS pooling) as MariaDB VECTOR values (little-endian float32)."""
        vectors = self.model.encode(texts, batch_size=64, normalize_embeddings=True, convert_to_numpy=True)
        return [v.astype("<f4").tobytes() for v in vectors]
