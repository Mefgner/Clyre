import asyncio
import json
import logging
from enum import Enum
from typing import Any, AsyncGenerator

import httpx

from utils import env

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)

# Fallback model aliases used when the launcher did not export a resolved name.
# In normal desktop runs these are overridden by the launcher via env.
DEFAULT_SMALL_MODEL = "Qwen3.5-9B"

STARTUP_RETRIES = 60
STARTUP_RETRY_DELAY = 5.0


class Tier(str, Enum):
    SMALL = "small"
    BIG = "big"


class LLMPipeline:
    """OpenAI-compatible chat client for one model tier.

    Talks to an OpenAI-compatible endpoint (/v1/chat/completions, /tokenize).
    One client class, configured per tier (small / big); the embedding tier uses
    the dedicated EmbeddingPipeline instead.
    """

    def __init__(
        self,
        base_url: str,
        model_name: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.__base_url = base_url.rstrip("/")
        self.__model_name = model_name
        self.__transport = transport

    @property
    def base_url(self) -> str:
        return self.__base_url

    @property
    def model_name(self) -> str:
        return self.__model_name

    async def wait_for_startup(self) -> None:
        """Poll /health until the server is ready, then raise on timeout."""
        async with httpx.AsyncClient(timeout=10, transport=self.__transport) as client:
            Logger.info("Waiting for llama.cpp to become ready at %s", self.__base_url)
            for attempt in range(1, STARTUP_RETRIES + 1):
                try:
                    (
                        await client.get(f"{self.__base_url}/health", timeout=10)
                    ).raise_for_status()
                    Logger.info("llama.cpp ready at %s", self.__base_url)
                    return
                except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException):
                    if attempt == STARTUP_RETRIES:
                        break
                    await asyncio.sleep(STARTUP_RETRY_DELAY)
            raise ConnectionError(
                f"llama.cpp at {self.__base_url} did not become ready within "
                f"{STARTUP_RETRIES * STARTUP_RETRY_DELAY:.0f}s"
            )

    def _build_payload(
        self,
        history: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
        stream: bool,
        response_format: dict[str, Any] | None = None,
        grammar: str | None = None,
    ):
        payload = {
            "model": self.__model_name,
            "messages": history,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if grammar is not None:
            payload["grammar"] = grammar
        return payload

    async def chat_completion_sync(
        self,
        history: list[dict[str, Any]],
        max_tokens: int = 800,
        temperature: float = 0.7,
        response_format: dict[str, Any] | None = None,
        grammar: str | None = None,
    ):
        payload = self._build_payload(
            history,
            max_tokens,
            temperature,
            stream=False,
            response_format=response_format,
            grammar=grammar,
        )
        link = f"{self.__base_url}/v1/chat/completions"
        async with httpx.AsyncClient(timeout=100.0, transport=self.__transport) as client:
            response = await client.post(link, json=payload)
            response.raise_for_status()
            response_json = response.json()
            Logger.info(
                "LLM response:\n\t%s\n\t%s\n\t%s",
                response_json["id"],
                response_json["usage"],
                response_json["timings"],
            )
            return response_json

    async def chat_completion_stream(
        self,
        history: list[dict[str, Any]],
        max_tokens: int = 800,
        temperature: float = 0.7,
        response_format: dict[str, Any] | None = None,
        grammar: str | None = None,
    ) -> AsyncGenerator[str, None]:
        payload = self._build_payload(
            history,
            max_tokens,
            temperature,
            stream=True,
            response_format=response_format,
            grammar=grammar,
        )
        link = f"{self.__base_url}/v1/chat/completions"
        async with httpx.AsyncClient(timeout=60.0, transport=self.__transport) as client:
            async with client.stream("POST", link, json=payload) as stream:
                async for line in stream.aiter_lines():
                    try:
                        formated_chunk = line[6:].strip()
                        if not formated_chunk:
                            continue

                        if formated_chunk == "[DONE]":
                            break

                        chunk_json: dict[str, Any] = json.loads(formated_chunk)

                        if len(chunk_json.get("choices", ())) <= 0:
                            if not chunk_json.get("usage") or not chunk_json.get("timings"):
                                continue
                            Logger.info(
                                "LLM response:\n\t%s\n\t%s\n\t%s",
                                chunk_json["id"],
                                chunk_json["usage"],
                                chunk_json["timings"],
                            )
                            continue

                        token: str | None = chunk_json["choices"][0]["delta"].get("content")
                        if not token:
                            continue

                        yield token
                    except json.JSONDecodeError:
                        Logger.error("Failed to decode JSON from llama.cpp response (%s)", line)
                        continue

    async def count_tokens_many(self, texts: list[str]) -> list[int]:
        """Count tokens through llama-server without approximating them locally."""
        if not texts:
            return []

        async with httpx.AsyncClient(timeout=60.0, transport=self.__transport) as client:
            responses = await asyncio.gather(
                *(
                    client.post(f"{self.__base_url}/tokenize", json={"content": text})
                    for text in texts
                )
            )
        for response in responses:
            response.raise_for_status()
        return [len(response.json()["tokens"]) for response in responses]


def _resolve_chat_tier(role: Tier) -> tuple[str, str]:
    """Return the (base_url, model) pair for a chat tier, applying small<->big
    fallback. Raises when no chat tier is configured at all."""
    small = (env.SMALL_BASE_URL, env.SMALL_MODEL)
    big = (env.BIG_BASE_URL, env.BIG_MODEL)

    if all(value is None for value in (*small, *big)):
        raise RuntimeError(
            "No chat model tier configured: set SMALL_* and/or BIG_* "
            "(base URL or model) in the environment."
        )

    url, model = small if role is Tier.SMALL else big

    if url is None and model is None:
        url, model = big if role is Tier.SMALL else small

    if url is None:
        host, port = (
            (env.SMALL_BIND_HOST, env.SMALL_BIND_PORT)
            if role is Tier.SMALL
            else (env.BIG_BIND_HOST, env.BIG_BIND_PORT)
        )
        url = f"http://{host}:{port}"

    if model is None:
        model = DEFAULT_SMALL_MODEL

    return url, model


_instances: dict[Tier, LLMPipeline] = {}


def get_inference_pipeline(role: Tier) -> LLMPipeline:
    if role not in _instances:
        base_url, model = _resolve_chat_tier(role)
        _instances[role] = LLMPipeline(base_url, model)
    return _instances[role]


__all__ = ["LLMPipeline", "Tier", "get_inference_pipeline"]
