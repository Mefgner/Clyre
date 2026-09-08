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

# Per-process stdout/stderr logs. Piping would freeze llama-server once the
# OS pipe buffer fills (nobody drains it) — files are append-only and free
# (known-issues #4). Same cwd-relative convention as ./data/files.
_LOG_DIR = Path("data/logs")


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
    log_name: str,
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
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOG_DIR / f"llama-{log_name}.log"
    log_file = log_path.open("ab")
    try:
        process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT)
    finally:
        log_file.close()  # the child inherited its own handle at spawn
    Logger.info("Started llama.cpp with pid %d (log: %s)", process.pid, log_path)
    return process


def stop_local_servers(processes: list[Popen]) -> None:
    """Terminate llama-server children started by `start_local_servers`.

    Only the desktop launcher owns these processes; without this, a Ctrl+C
    or a crash leaves orphans holding ports 6760-6762 and VRAM
    (known-issues #4). The launcher is a console app, so a hard console-window
    close bypasses this path — job-object cleanup is deferred to M11 packaging.
    """
    for process in processes:
        if process.poll() is not None:
            continue
        Logger.info("Terminating llama-server pid %d", process.pid)
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            Logger.warning("llama-server pid %d ignored terminate; killing", process.pid)
            process.kill()
            process.wait(timeout=5)


def start_local_servers() -> list[Popen]:
    """Start the local llama-server processes for every required tier and export
    the resolved model aliases to the environment for the API to pick up.

    SMALL and EMBEDDING are always started (chat + RAG are required). In
    TEST_MODE the default SMALL role is replaced by TEST and the default BIG tier
    is disabled. Explicit *_MODEL overrides remain authoritative.
    """
    settings = Settings()
    executable_path = cfg.get_default_llama_executable()
    processes: list[Popen] = []

    small_url = settings.SMALL_BASE_URL
    if _is_local_url(small_url):
        default_small_role = "test" if settings.TEST_MODE else "small"
        small_model = settings.SMALL_MODEL or cfg.get_default_model_name_by_role(
            default_small_role
        )
        processes.append(
            start_server(
                small_model,
                executable_path=executable_path,
                host=settings.SMALL_BIND_HOST,
                port=settings.SMALL_BIND_PORT,
                log_name="small",
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
                log_name="embedding",
                embeddings=True,
            )
        )
        os.environ["EMBEDDING_MODEL"] = embedding_model

    default_big = None
    if not settings.TEST_MODE:
        default_big = cfg.get_default_model_name_by_role_or_none("big")
    big_model = settings.BIG_MODEL or default_big
    big_url = settings.BIG_BASE_URL
    if big_model and _is_local_url(big_url):
        processes.append(
            start_server(
                big_model,
                executable_path=executable_path,
                host=settings.BIG_BIND_HOST,
                port=settings.BIG_BIND_PORT,
                log_name="big",
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
