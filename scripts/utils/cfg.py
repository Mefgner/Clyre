import logging
import os
import sys
from functools import lru_cache
from pathlib import Path

import yaml

Logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_app_root_dir() -> Path:
    res = Path(__file__).parent.parent.parent.resolve()
    return res


def dict_from_yaml(absolute_file_path: Path) -> dict:
    with open(absolute_file_path, encoding="utf-8") as file:
        data = yaml.load(file, Loader=yaml.FullLoader)
        if not data:
            raise ValueError(f"Configuration is not set in {absolute_file_path.name}")
        return data


@lru_cache(maxsize=1)
def get_app_runtime_dir() -> Path:
    platform_info = dict_from_yaml(get_app_root_dir() / "configs" / "platform.yaml")
    if not platform_info:
        raise ValueError("No platform information found in platform.yaml")

    for p in platform_info:
        if sys.platform == p["name"]:
            workdir = Path(os.path.expanduser(os.path.expandvars(p["workdir"]))).resolve()
            Logger.debug("platform path: %s", workdir)
            workdir.mkdir(parents=True, exist_ok=True)
            return workdir.resolve()
    raise ValueError("Platform not found")


@lru_cache(maxsize=1)
def get_default_llama_executable() -> Path:
    binaries = dict_from_yaml(get_app_root_dir() / "configs" / "binaries.yaml")

    for b in binaries:
        if b.get("type") == "llama.cpp" and b.get("platform") == sys.platform:
            dest_subdir = b["dest_subdir"]
            executable = b["exe_name"]
            base = get_app_runtime_dir() / dest_subdir
            # Zips are extracted into the `folder` directory (see binaries.yaml),
            # so the exe normally lives under binaries/<folder>/.
            folder = b.get("folder")
            if folder:
                nested = base / folder / executable
                if nested.exists():
                    return nested
            # Fallback for flat layouts (no folder) or not-yet-extracted state.
            return base / executable
    raise ValueError("No default llama executable")


@lru_cache(maxsize=16)
def resolve_model_path(model_name: str) -> str:
    models = dict_from_yaml(get_app_root_dir() / "configs" / "models.yaml")
    for m in models:
        if m.get("name") == model_name:
            dest_subdir = m["dest_subdir"]
            filename = m["filename"]
            return str((get_app_runtime_dir() / dest_subdir / filename).resolve())
    raise ValueError(f"Model '{model_name}' not found in models.yaml")


@lru_cache(maxsize=16)
def get_default_model_name_by_role(role: str) -> str:
    """Return the `name` of the first catalog entry tagged with the given role
    (small | big | embedding)."""
    models = dict_from_yaml(get_app_root_dir() / "configs" / "models.yaml")
    for m in models:
        if m.get("role") == role:
            return m.get("name")
    raise ValueError(f"No model with role '{role}' found in models.yaml")


@lru_cache(maxsize=16)
def get_default_model_name_by_role_or_none(role: str) -> str | None:
    try:
        return get_default_model_name_by_role(role)
    except ValueError:
        return None


__all__ = [
    "dict_from_yaml",
    "get_app_runtime_dir",
    "get_default_llama_executable",
    "resolve_model_path",
    "get_default_model_name_by_role",
    "get_default_model_name_by_role_or_none",
]
