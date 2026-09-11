"""Run the Docker-backed e2e suite and always tear its services down."""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_COMPOSE = "docker-compose.e2e.yml"
GPU_COMPOSE = "docker-compose.e2e.gpu.yml"
WAIT_TIMEOUT_SECONDS = 900


def _display(command: list[str]) -> str:
    return shlex.join(command)


def _run(command: list[str]) -> int:
    print(f"+ {_display(command)}", flush=True)
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def _compose_command(gpu: bool) -> list[str]:
    command = ["docker", "compose", "-f", BASE_COMPOSE]
    if gpu:
        command.extend(["-f", GPU_COMPOSE])
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", action="store_true", help="enable the CUDA compose overlay")
    args, pytest_args = parser.parse_known_args()

    missing = [program for program in ("docker", "poetry") if shutil.which(program) is None]
    if missing:
        parser.error(f"required command(s) not found on PATH: {', '.join(missing)}")

    compose = _compose_command(args.gpu)
    started = False
    result = 1

    try:
        started = True
        result = _run(
            [
                *compose,
                "up",
                "--detach",
                "--wait",
                "--wait-timeout",
                str(WAIT_TIMEOUT_SECONDS),
                "--remove-orphans",
            ]
        )
        if result == 0:
            result = _run(["poetry", "run", "pytest", "tests_e2e", "-m", "e2e", *pytest_args])
    except KeyboardInterrupt:
        result = 130
    finally:
        if started:
            teardown_result = _run([*compose, "down", "--remove-orphans"])
            if result == 0 and teardown_result != 0:
                result = teardown_result

    return result


if __name__ == "__main__":
    raise SystemExit(main())
