import datetime
import logging
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

import yaml

from utils import env
from utils.base import get_app_root_dir

Logger = logging.getLogger(__name__)


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
def get_resolved_db_path() -> Path:
    db_file_path_pattern = re.compile(r"^\.(/\w+)+(\.\w{2,})?$")
    db_path = env.DB_PATH
    if db_file_path_pattern.match(db_path):
        # Absolute path for the db .sqlite file
        db_path = get_app_runtime_dir().joinpath(db_path)

        db_path.touch(exist_ok=True)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        return db_path
    raise ValueError("DB_PATH is not a valid relative path pattern or is not set.")


@lru_cache(maxsize=1)
def get_default_llama_executable() -> Path:
    binaries = dict_from_yaml(get_app_root_dir() / "configs" / "binaries.yaml")

    for b in binaries:
        if b.get("type") == "llama.cpp" and b.get("platform") == sys.platform:
            dest_subdir = b["dest_subdir"]
            folder = b["folder"]
            executable = b["exe_name"]
            return get_app_runtime_dir() / dest_subdir / folder / executable
    raise ValueError("No default llama executable")


@lru_cache(maxsize=1)
def get_default_llama_model_path() -> Path:
    models = dict_from_yaml(get_app_root_dir() / "configs" / "models.yaml")
    target = None

    for m in models:
        if m.get("framework") == "llama":
            target = m
            break

    if not target:
        raise ValueError("No llama.cpp-compatible model found in models.yaml")

    dest_subdir = target["dest_subdir"]
    filename = target["filename"]

    return (get_app_runtime_dir() / dest_subdir / filename).resolve()


@lru_cache(maxsize=16)
def resolve_llama_model_path(model_name: str) -> str | None:
    models = dict_from_yaml(get_app_root_dir() / "configs" / "models.yaml")
    for m in models:
        if m.get("name") == model_name and m.get("framework") == "llama":
            dest_subdir = m["dest_subdir"]
            filename = m["filename"]
            return str((get_app_runtime_dir() / dest_subdir / filename).resolve())
    raise ValueError(f"Model '{model_name}' not found or not compatible with llama.cpp")


@lru_cache(maxsize=1)
def get_default_llama_model_name():
    models = dict_from_yaml(get_app_root_dir() / "configs" / "models.yaml")
    for m in models:
        if m.get("framework") == "llama":
            return m.get("name")
    raise ValueError("No llama.cpp-compatible model found in models.yaml")


@lru_cache(maxsize=1)
def get_access_token_dur_minutes() -> datetime.timedelta:
    return datetime.timedelta(minutes=int(env.ACCESS_TOKEN_DUR_MINUTES))


@lru_cache(maxsize=1)
def get_refresh_token_dur_days() -> datetime.timedelta:
    return datetime.timedelta(days=int(env.REFRESH_TOKEN_DUR_DAYS))


@lru_cache(maxsize=1)
def get_logging_level() -> int:
    return logging.DEBUG if env.DEBUG else logging.INFO


__all__ = [
    "get_app_root_dir",
    "get_app_runtime_dir",
    "get_resolved_db_path",
    "get_default_llama_executable",
    "get_default_llama_model_path",
    "resolve_llama_model_path",
    "get_default_llama_model_name",
    "get_access_token_dur_minutes",
    "get_refresh_token_dur_days",
    "get_logging_level",
]
