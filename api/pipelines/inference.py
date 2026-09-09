import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal

import httpx

from utils import env

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)

DEFAULT_CHAT_MODEL = "Qwen3.5-9B"
STARTUP_RETRIES = 60
STARTUP_RETRY_DELAY = 5.0
TOKENIZE_CONCURRENCY = 8
REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0)

ChunkKind = Literal["thinking", "content"]


@dataclass(frozen=True)
class ThinkingWiring:
    chat_template_kwargs: dict[str, Any] | None = None
    reasoning_format: str | None = None


THINKING_WIRING: dict[str, ThinkingWiring] = {
    "qwen3": ThinkingWiring(
        chat_template_kwargs={"enable_thinking": True},
        reasoning_format="deepseek",
    ),
}


def _thinking_payload_fields(model_name: str, enable_thinking: bool) -> dict[str, Any]:
    lowered = model_name.lower()
    for family, wiring in THINKING_WIRING.items():
        if family in lowered:
            if not enable_thinking:
                return {"chat_template_kwargs": {"enable_thinking": False}}
            fields: dict[str, Any] = {}
            if wiring.chat_template_kwargs is not None:
                fields["chat_template_kwargs"] = wiring.chat_template_kwargs
            if wiring.reasoning_format is not None:
                fields["reasoning_format"] = wiring.reasoning_format
            return fields
    Logger.debug("No thinking wiring registered for model %s", model_name)
    return {}


class LLMPipeline:
    """OpenAI-compatible client for Clyre's single chat model."""

    def __init__(
        self,
        base_url: str,
        model_name: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.__base_url = base_url.rstrip("/")
        self.__model_name = model_name
        self.__client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT, transport=transport)
        self.__tokenize_semaphore = asyncio.Semaphore(TOKENIZE_CONCURRENCY)

    @property
    def base_url(self) -> str:
        return self.__base_url

    @property
    def model_name(self) -> str:
        return self.__model_name

    async def aclose(self) -> None:
        await self.__client.aclose()

    async def wait_for_startup(self) -> None:
        Logger.info("Waiting for llama.cpp to become ready at %s", self.__base_url)
        for attempt in range(1, STARTUP_RETRIES + 1):
            try:
                response = await self.__client.get(f"{self.__base_url}/health", timeout=10.0)
                response.raise_for_status()
                Logger.info("llama.cpp ready at %s", self.__base_url)
                return
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException):
                if attempt == STARTUP_RETRIES:
                    break
                await asyncio.sleep(STARTUP_RETRY_DELAY)
        raise ConnectionError(f"llama.cpp at {self.__base_url} did not become ready")

    def _build_payload(
        self,
        history: list[dict[str, Any]],
        temperature: float,
        stream: bool,
        response_format: dict[str, Any] | None = None,
        grammar: str | None = None,
        enable_thinking: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.__model_name,
            "messages": history,
            "temperature": temperature,
            "stream": stream,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        if grammar is not None:
            payload["grammar"] = grammar
        if enable_thinking is not None:
            payload.update(
                _thinking_payload_fields(self.__model_name, enable_thinking=enable_thinking)
            )
        return payload

    async def chat_completion_sync(
        self,
        history: list[dict[str, Any]],
        temperature: float = 0.7,
        response_format: dict[str, Any] | None = None,
        grammar: str | None = None,
        enable_thinking: bool | None = None,
    ):
        payload = self._build_payload(
            history,
            temperature,
            stream=False,
            response_format=response_format,
            grammar=grammar,
            enable_thinking=enable_thinking,
        )
        response = await self.__client.post(
            f"{self.__base_url}/v1/chat/completions", json=payload
        )
        response.raise_for_status()
        response_json = response.json()
        Logger.info(
            "LLM response: id=%s usage=%s timings=%s",
            response_json.get("id"),
            response_json.get("usage"),
            response_json.get("timings"),
        )
        return response_json

    async def chat_completion_stream(
        self,
        history: list[dict[str, Any]],
        temperature: float = 0.7,
        response_format: dict[str, Any] | None = None,
        grammar: str | None = None,
        enable_thinking: bool | None = None,
    ) -> AsyncGenerator[tuple[ChunkKind, str], None]:
        payload = self._build_payload(
            history,
            temperature,
            stream=True,
            response_format=response_format,
            grammar=grammar,
            enable_thinking=enable_thinking,
        )
        async with self.__client.stream(
            "POST", f"{self.__base_url}/v1/chat/completions", json=payload
        ) as stream:
            stream.raise_for_status()
            async for line in stream.aiter_lines():
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    Logger.debug("Ignoring non-data SSE line: %s", line)
                    continue

                formatted_chunk = line[5:].strip()
                if not formatted_chunk:
                    continue
                if formatted_chunk == "[DONE]":
                    break

                try:
                    chunk_json: dict[str, Any] = json.loads(formatted_chunk)
                except json.JSONDecodeError:
                    Logger.warning("Failed to decode JSON from model stream")
                    continue

                choices = chunk_json.get("choices") or []
                if not choices:
                    if chunk_json.get("usage") or chunk_json.get("timings"):
                        Logger.info(
                            "LLM stream summary: id=%s usage=%s timings=%s",
                            chunk_json.get("id"),
                            chunk_json.get("usage"),
                            chunk_json.get("timings"),
                        )
                    continue

                delta = choices[0].get("delta") or {}
                reasoning = delta.get("reasoning_content")
                if reasoning:
                    yield ("thinking", reasoning)

                token = delta.get("content")
                if token:
                    yield ("content", token)

    async def _count_tokens(self, text: str) -> int:
        async with self.__tokenize_semaphore:
            response = await self.__client.post(
                f"{self.__base_url}/tokenize", json={"content": text}
            )
            response.raise_for_status()
            return len(response.json()["tokens"])

    async def count_tokens_many(self, texts: list[str]) -> list[int]:
        if not texts:
            return []
        return await asyncio.gather(*(self._count_tokens(text) for text in texts))


def _resolve_chat_model() -> tuple[str, str]:
    if env.CHAT_BASE_URL is None and env.CHAT_MODEL is None:
        raise RuntimeError(
            "No chat model configured: set CHAT_BASE_URL and/or CHAT_MODEL "
            "in the environment."
        )

    url = env.CHAT_BASE_URL or f"http://{env.CHAT_BIND_HOST}:{env.CHAT_BIND_PORT}"
    model = env.CHAT_MODEL or DEFAULT_CHAT_MODEL

    return url, model


_instance: LLMPipeline | None = None


def get_inference_pipeline() -> LLMPipeline:
    global _instance
    if _instance is None:
        base_url, model = _resolve_chat_model()
        _instance = LLMPipeline(base_url, model)
    return _instance


async def close_inference_pipelines() -> None:
    global _instance
    if _instance is not None:
        await _instance.aclose()
        _instance = None


__all__ = [
    "LLMPipeline",
    "close_inference_pipelines",
    "get_inference_pipeline",
]
