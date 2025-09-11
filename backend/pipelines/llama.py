import logging
import os
import subprocess
import time
from pathlib import Path
from subprocess import Popen

import httpx
from utils import cfg

BASEDIR = cfg.get_app_root_dir()
WORKDIR = cfg.get_app_runtime_dir()

LLAMA_URL = cfg.get_llama_url()
LLAMA_WIN_HOST = cfg.get_llama_win_host()
LLAMA_WIN_PORT = cfg.get_llama_win_port()


class LlamaLLMPipeline:
    is_running = False
    __process: Popen | None = None
    current_model: str | None = None

    def __init__(self, model_name: str, model_path: str | Path, executable_path: os.PathLike,
                 is_in_docker: bool = False):
        self.current_model = self.__model_name = model_name
        self.__model_path = model_path
        self.__executable_path = executable_path
        self.__is_in_docker = is_in_docker

        self._startup()

    def _startup(self):
        if not self.__is_in_docker:
            self.__process = subprocess.Popen([
                self.__executable_path, '--model', self.__model_path, '--host', LLAMA_WIN_HOST, '--port',
                LLAMA_WIN_PORT, '-ngl', '100'
            ], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            with httpx.Client(timeout=10) as client:
                while True:
                    try:
                        client.get(f"{LLAMA_URL}/health", timeout=10).raise_for_status()
                        break
                    except httpx.HTTPStatusError:
                        time.sleep(1.5)
        self.is_running = True

    def _build_payload(self, history: list[dict[str, str]], max_tokens: int, temperature: float, stream: bool):
        return {
            "model": self.__model_name,
            "messages": history,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream
        }

    async def chat_completion_stream(self, history: list[dict[str, str]], max_tokens: int = 512,
                                     temperature: float = 0.7):
        payload = self._build_payload(history, max_tokens, temperature, stream=True)
        link = f"{LLAMA_URL}/v1/chat/completions"
        async with httpx.AsyncClient(timeout=100.0) as client:
            async with client.stream("POST", link, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        yield line

    async def chat_completion_sync(self, history: list[dict[str, str]], max_tokens: int = 512,
                                   temperature: float = 0.7):
        payload = self._build_payload(history, max_tokens, temperature, stream=False)
        link = f"{LLAMA_URL}/v1/chat/completions"
        async with httpx.AsyncClient(timeout=100.0) as client:
            response = await client.post(link, json=payload)
            response.raise_for_status()
            json = response.json()
            logging.info(f"LLama response: \\ \n\t{json['id']}\n\t{json['usage']}")
            return json

    def __del__(self):
        if self.__process:
            self.__process.terminate()
            self.__process.wait()
            self.is_running = False


llama_instance: LlamaLLMPipeline | None = None


def get_llama_pipeline(model_name: str | None = None, executable_path: Path | None = None,
                       is_in_docker: bool = False) -> LlamaLLMPipeline:
    if not model_name:
        model_name = cfg.get_default_llama_model_name()
    if not executable_path:
        executable_path = cfg.get_default_llama_executable()
    global llama_instance

    if not llama_instance:
        llama_instance = LlamaLLMPipeline(model_name, cfg.resolve_llama_model_path(model_name), executable_path,
                                          is_in_docker)

    if llama_instance.current_model != model_name:
        del llama_instance
        llama_instance = LlamaLLMPipeline(model_name, cfg.resolve_llama_model_path(model_name), executable_path,
                                          is_in_docker)

    return llama_instance
