import asyncio
import logging
import math

import httpx

from utils import env

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)

DEFAULT_EMBEDDING_MODEL = "Qwen3-Embedding-0.6B"
STARTUP_RETRIES = 60
STARTUP_RETRY_DELAY = 5.0


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        return vector
    return [x / norm for x in vector]


def _extract_embeddings(response_json: dict) -> list[list[float]]:
    data = sorted(response_json["data"], key=lambda item: item.get("index", 0))
    return [item["embedding"] for item in data]


def _postprocess(vectors: list[list[float]]) -> list[list[float]]:
    dim = env.VECTOR_DIM
    out: list[list[float]] = []
    for vector in vectors:
        if len(vector) < dim:
            raise ValueError(f"embedding has {len(vector)} dims, expected at least {dim}")
        vector = vector[:dim]  # Matryoshka truncation to the index dimension
        if env.NORMALIZE_VECTORS:
            vector = _normalize(vector)
        out.append(vector)
    return out


class EmbeddingPipeline:
    def __init__(
        self, base_url: str, model: str, transport: httpx.AsyncBaseTransport | None = None
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._transport = transport

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": self._model, "input": texts}
        async with httpx.AsyncClient(timeout=60.0, transport=self._transport) as client:
            response = await client.post(f"{self._base_url}/v1/embeddings", json=payload)
            response.raise_for_status()
            return _postprocess(_extract_embeddings(response.json()))

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]

    async def wait_for_startup(self) -> None:
        async with httpx.AsyncClient(timeout=10, transport=self._transport) as client:
            Logger.info("Waiting for the embedding server at %s", self._base_url)
            for attempt in range(1, STARTUP_RETRIES + 1):
                try:
                    (await client.get(f"{self._base_url}/health")).raise_for_status()
                    return
                except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException):
                    if attempt == STARTUP_RETRIES:
                        break
                    await asyncio.sleep(STARTUP_RETRY_DELAY)
            raise ConnectionError(
                f"embedding server at {self._base_url} did not become ready within "
                f"{STARTUP_RETRIES * STARTUP_RETRY_DELAY:.0f}s"
            )


_embedding_instance: EmbeddingPipeline | None = None


def get_embedding_pipeline() -> EmbeddingPipeline:
    global _embedding_instance
    if _embedding_instance is None:
        base_url = env.EMBEDDING_BASE_URL or (
            f"http://{env.EMBEDDING_BIND_HOST}:{env.EMBEDDING_BIND_PORT}"
        )
        model = env.EMBEDDING_MODEL or DEFAULT_EMBEDDING_MODEL
        _embedding_instance = EmbeddingPipeline(base_url, model)
    return _embedding_instance


__all__ = ["EmbeddingPipeline", "get_embedding_pipeline"]
