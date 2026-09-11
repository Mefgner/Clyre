import os
import sys
from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache(maxsize=1)
def get_app_root_dir() -> Path:
    return Path(__file__).parent.parent.parent.resolve()


def _default_runtime_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / "clyre"


@lru_cache(maxsize=1)
def get_app_runtime_dir() -> Path:
    """Return the OS-specific directory for desktop runtime data."""
    config_path = get_app_root_dir() / "configs" / "platform.yaml"
    if config_path.exists():
        with config_path.open(encoding="utf-8") as file:
            platform_info: list[dict[str, str]] = yaml.load(file, Loader=yaml.FullLoader)

        for platform in platform_info or []:
            if sys.platform == platform["name"]:
                workdir = Path(
                    os.path.expanduser(os.path.expandvars(platform["workdir"]))
                ).resolve()
                workdir.mkdir(parents=True, exist_ok=True)
                return workdir

    workdir = _default_runtime_dir().resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    return workdir
