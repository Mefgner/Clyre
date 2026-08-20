import json

import httpx
import pytest

from pipelines import inference
from pipelines.inference import LLMPipeline, Tier, _resolve_chat_tier


async def test_count_tokens_many_uses_tokenize_endpoint():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        content = json.loads(request.content)["content"]
        return httpx.Response(200, json={"tokens": list(range(len(content)))})

    pipeline = LLMPipeline("http://llama", "model", httpx.MockTransport(handler))

    assert await pipeline.count_tokens_many(["one", "two words"]) == [3, 9]
    assert [request.url.path for request in requests] == ["/tokenize", "/tokenize"]


def _set_tiers(monkeypatch, **kwargs):
    for key in (
        "SMALL_BASE_URL",
        "SMALL_MODEL",
        "BIG_BASE_URL",
        "BIG_MODEL",
        "SMALL_BIND_HOST",
        "SMALL_BIND_PORT",
        "BIG_BIND_HOST",
        "BIG_BIND_PORT",
    ):
        monkeypatch.setattr(inference.env, key, kwargs.get(key), raising=False)


def test_resolve_big_falls_back_to_small(monkeypatch):
    _set_tiers(
        monkeypatch,
        SMALL_BASE_URL="http://small",
        SMALL_MODEL="Small",
        BIG_BASE_URL=None,
        BIG_MODEL=None,
    )
    assert _resolve_chat_tier(Tier.BIG) == ("http://small", "Small")


def test_resolve_small_uses_local_bind_when_only_model_set(monkeypatch):
    _set_tiers(
        monkeypatch,
        SMALL_BASE_URL=None,
        SMALL_MODEL="Small",
        BIG_BASE_URL=None,
        BIG_MODEL=None,
        SMALL_BIND_HOST="localhost",
        SMALL_BIND_PORT=6760,
    )
    assert _resolve_chat_tier(Tier.SMALL) == ("http://localhost:6760", "Small")


def test_resolve_raises_when_no_tier_configured(monkeypatch):
    _set_tiers(
        monkeypatch,
        SMALL_BASE_URL=None,
        SMALL_MODEL=None,
        BIG_BASE_URL=None,
        BIG_MODEL=None,
    )
    with pytest.raises(RuntimeError):
        _resolve_chat_tier(Tier.SMALL)


async def test_wait_for_startup_raises_after_retry_limit(monkeypatch):
    monkeypatch.setattr(inference, "STARTUP_RETRIES", 2)
    monkeypatch.setattr(inference, "STARTUP_RETRY_DELAY", 0.01)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    pipeline = LLMPipeline("http://llama", "model", httpx.MockTransport(handler))
    with pytest.raises(ConnectionError):
        await pipeline.wait_for_startup()


async def test_wait_for_startup_returns_when_healthy(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    pipeline = LLMPipeline("http://llama", "model", httpx.MockTransport(handler))
    await pipeline.wait_for_startup()
