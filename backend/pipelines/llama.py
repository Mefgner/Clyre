import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
from subprocess import Popen
from typing import Any, AsyncGenerator

import httpx

from utils import cfg, env

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)

LLAMA_URL = env.LLAMA_URL


class LlamaLLMPipeline:
    is_running = False
    __process: Popen | None = None
    __current_model: str | None = None

    def __init__(
        self,
        llama_url: str,
        model_name: str,
        model_path: str | Path,
        executable_path: os.PathLike,
        is_in_docker: bool = False,
    ):
        Logger.info("Initializing LlamaLLMPipeline")
        self.__llama_url = llama_url
        self.__current_model = self.__model_name = model_name
        self.__model_path = model_path
        self.__executable_path = executable_path
        self.__is_in_docker = is_in_docker

        self._startup()

    @property
    def current_model(self):
        return self.__current_model

    def _startup(self):
        if not self.__is_in_docker:
            Logger.info("Starting Llama.cpp executable")
            self.__process = subprocess.Popen(
                [
                    self.__executable_path,
                    "--model",
                    self.__model_path,
                    "--host",
                    env.LLAMA_WIN_HOST,
                    "--port",
                    str(env.LLAMA_WIN_PORT),
                    "-ngl",
                    "-1",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )

        self.is_running = True

    @staticmethod
    async def wait_for_startup():
        async with httpx.AsyncClient(timeout=10) as client:
            Logger.info("Waiting for Llama.cpp to ready to process requests")
            while True:
                try:
                    (await client.get(f"{LLAMA_URL}/health", timeout=10)).raise_for_status()
                    break
                except httpx.HTTPStatusError:
                    await asyncio.sleep(2)

    def _build_payload(
        self,
        history: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        stream: bool,
    ):
        return {
            "model": self.__model_name,
            "messages": history,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }

    async def chat_completion_sync(
        self,
        history: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
    ):
        payload = self._build_payload(history, max_tokens, temperature, stream=False)
        link = f"{self.__llama_url}/v1/chat/completions"
        async with httpx.AsyncClient(timeout=100.0) as client:
            response = await client.post(link, json=payload)
            response.raise_for_status()
            response_json = response.json()
            Logger.info(
                "LLama response:\n\t%s\n\t%s\n\t%s",
                response_json["id"],
                response_json["usage"],
                response_json["timings"],
            )
            return response_json

    async def chat_completion_stream(
        self,
        history: list[dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        payload = self._build_payload(history, max_tokens, temperature, stream=True)
        link = f"{self.__llama_url}/v1/chat/completions"
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", link, json=payload) as stream:
                async for line in stream.aiter_lines():
                    try:
                        formated_chunk = line.split("data: ")[-1].strip()
                        if not formated_chunk or formated_chunk == "[DONE]":
                            continue

                        chunk_json: dict[str, Any] = json.loads(formated_chunk)

                        if len(chunk_json.get("choices", ())) <= 0:
                            if not chunk_json.get("usage") or not chunk_json.get("timings"):
                                continue
                            Logger.info(
                                "LLama response:\n\t%s\n\t%s\n\t%s",
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
                        Logger.error("Failed to decode JSON from Llama.cpp response (%s)", line)
                        continue

    def __del__(self):
        Logger.info("Shutting down Llama.cpp executable")
        if self.__process:
            self.__process.terminate()
            self.__process.wait()
            self.is_running = False
            self.__process = None


llama_instance: LlamaLLMPipeline | None = None


def get_llama_pipeline(
    model_name: str | None = None,
    executable_path: Path | None = None,
    is_in_docker: bool = False,
) -> LlamaLLMPipeline:
    if not model_name:
        model_name = cfg.get_default_llama_model_name()
    if not executable_path:
        executable_path = cfg.get_default_llama_executable()

    setup_payload = (
        LLAMA_URL,
        model_name,
        cfg.resolve_llama_model_path(model_name),
        executable_path,
        is_in_docker,
    )

    global llama_instance

    if not llama_instance:
        llama_instance = LlamaLLMPipeline(*setup_payload)

    if llama_instance.current_model != model_name:
        del llama_instance
        llama_instance = LlamaLLMPipeline(*setup_payload)

    return llama_instance
