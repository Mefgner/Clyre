import logging
import os
import subprocess
from pathlib import Path
from subprocess import Popen
from urllib.parse import urlparse

from scripts.utils import cfg
from shared.pyutils.env import Settings

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)

_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _is_local_url(url: str | None) -> bool:
    """True when a URL is unset (local default) or points at this host."""
    if not url:
        return True
    return urlparse(url).hostname in _LOCAL_HOSTS


def build_llama_command(
    model_name: str,
    *,
    executable_path: Path,
    host: str,
    port: int,
    embeddings: bool = False,
) -> list[str]:
    """Build the llama-server command for one model tier."""
    resolved_model_path = cfg.resolve_model_path(model_name)
    command = [
        str(executable_path),
        "--model",
        str(resolved_model_path),
        "--host",
        host,
        "--port",
        str(port),
        "--alias",
        model_name,
        "-ngl",
        "40",
        "--jinja",
    ]
    if embeddings:
        command.append("--embeddings")
    return command


def start_server(
    model_name: str,
    *,
    executable_path: Path,
    host: str,
    port: int,
    embeddings: bool = False,
) -> Popen:
    command = build_llama_command(
        model_name,
        executable_path=executable_path,
        host=host,
        port=port,
        embeddings=embeddings,
    )
    Logger.info("Starting llama.cpp server: %s", " ".join(command))
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    Logger.info("Started llama.cpp with pid %d", process.pid)
    return process


def start_local_servers() -> list[Popen]:
    """Start the local llama-server processes for every required tier and export
    the resolved model aliases to the environment for the API to pick up.

    SMALL and EMBEDDING are always started (chat + RAG are required). BIG is
    optional: it is started only when a model is configured for it and it points
    at a local process; otherwise the API falls back to SMALL.
    """
    settings = Settings()
    executable_path = cfg.get_default_llama_executable()
    processes: list[Popen] = []

    small_url = settings.SMALL_BASE_URL
    if _is_local_url(small_url):
        small_model = settings.SMALL_MODEL or cfg.get_default_model_name_by_role("small")
        processes.append(
            start_server(
                small_model,
                executable_path=executable_path,
                host=settings.SMALL_BIND_HOST,
                port=settings.SMALL_BIND_PORT,
            )
        )
        os.environ["SMALL_MODEL"] = small_model

    embedding_url = settings.EMBEDDING_BASE_URL
    if _is_local_url(embedding_url):
        embedding_model = settings.EMBEDDING_MODEL or cfg.get_default_model_name_by_role(
            "embedding"
        )
        processes.append(
            start_server(
                embedding_model,
                executable_path=executable_path,
                host=settings.EMBEDDING_BIND_HOST,
                port=settings.EMBEDDING_BIND_PORT,
                embeddings=True,
            )
        )
        os.environ["EMBEDDING_MODEL"] = embedding_model

    big_model = settings.BIG_MODEL or cfg.get_default_model_name_by_role_or_none("big")
    big_url = settings.BIG_BASE_URL
    if big_model and _is_local_url(big_url):
        processes.append(
            start_server(
                big_model,
                executable_path=executable_path,
                host=settings.BIG_BIND_HOST,
                port=settings.BIG_BIND_PORT,
            )
        )
        os.environ["BIG_MODEL"] = big_model
    elif big_url and not _is_local_url(big_url):
        Logger.warning(
            "BIG_BASE_URL points outside this host (%s); the reasoning tier sees "
            "full user context and must stay local.",
            big_url,
        )

    return processes
