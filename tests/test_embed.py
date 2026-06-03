import json

import httpx
import pytest

from pipelines.embed import EmbeddingPipeline, _extract_embeddings, _normalize, _postprocess

DIM = 8


def test_normalize_unit_vector():
    assert _normalize([3.0, 4.0]) == pytest.approx([0.6, 0.8])


def test_normalize_zero_vector_unchanged():
    assert _normalize([0.0, 0.0]) == [0.0, 0.0]


def test_extract_embeddings_sorts_by_index():
    payload = {"data": [{"index": 1, "embedding": [9.0]}, {"index": 0, "embedding": [1.0]}]}
    assert _extract_embeddings(payload) == [[1.0], [9.0]]


def test_postprocess_truncates_to_vector_dim_and_normalizes():
    long_vector = [3.0, 4.0] + [0.0] * 10  # len 12 -> truncate to 8
    out = _postprocess([long_vector])
    assert len(out[0]) == DIM
    assert out[0] == pytest.approx([0.6, 0.8, 0, 0, 0, 0, 0, 0])


def test_postprocess_rejects_too_short():
    with pytest.raises(ValueError):
        _postprocess([[1.0, 2.0]])


async def test_embed_posts_and_postprocesses():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [3.0, 4.0, 0, 0, 0, 0, 0, 0]},
                    {"index": 1, "embedding": [0, 0, 0, 0, 0, 0, 6.0, 8.0]},
                ]
            },
        )

    pipe = EmbeddingPipeline("http://emb:6761/", "m", transport=httpx.MockTransport(handler))
    out = await pipe.embed(["hello", "world"])

    assert captured["url"].endswith("/v1/embeddings")
    assert captured["json"] == {"model": "m", "input": ["hello", "world"]}
    assert out[0] == pytest.approx([0.6, 0.8, 0, 0, 0, 0, 0, 0])
    assert out[1] == pytest.approx([0, 0, 0, 0, 0, 0, 0.6, 0.8])


async def test_embed_empty_is_noop():
    pipe = EmbeddingPipeline(
        "http://x", "m", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    )
    assert await pipe.embed([]) == []
