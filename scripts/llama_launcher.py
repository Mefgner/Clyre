import logging
import subprocess
from pathlib import Path
from subprocess import Popen

from shared.pyutils.env import Settings
from scripts.utils import cfg

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)


def build_llama_command(
    model_name: str | None = None,
    executable_path: Path | None = None,
) -> list[str]:
    """Builds command to start llama.cpp server"""
    selected_model = model_name or cfg.get_default_llama_model_name()
    resolved_model_path = cfg.resolve_llama_model_path(selected_model)
    resolved_executable = executable_path or cfg.get_default_llama_executable()

    return [
        str(resolved_executable),
        "--model",
        str(resolved_model_path),
        "--host",
        Settings().LLAMA_WIN_HOST,
        "--port",
        str(Settings().LLAMA_WIN_PORT),
        "-ngl",
        "40",
        "--jinja",
    ]


def start_llama_server(
    model_name: str | None = None,
    executable_path: Path | None = None,
) -> Popen:
    command = build_llama_command(model_name=model_name, executable_path=executable_path)
    Logger.info("Starting llama.cpp server: %s", " ".join(command))
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    Logger.info("Started llama.cpp with pid %d", process.pid)
    return process
