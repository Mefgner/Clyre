import logging
import re
from pathlib import Path

import pooch
import yaml

from scripts.utils import cfg
from shared.pyutils.base import get_app_root_dir
from shared.pyutils.env import Settings

Logger = logging.getLogger(__name__)
Logger.setLevel(logging.INFO)

sha256_regex = re.compile(r"[a-fA-F0-9]{64}")


def shorter_path_repr(path: Path | str) -> str:
    if isinstance(path, Path):
        path = str(path)
    if not path:
        Logger.warning("Empty path %s")
        return ""
    sha_part = sha256_regex.search(path)
    if sha_part:
        truncated = sha_part.group(0)[:8] + "..." + sha_part.group(0)[-8:]
        return path.replace(sha_part.group(0), truncated)
    return path


def download_from_config(item_to_download: dict[str, str]) -> str | list[str]:
    url = item_to_download["url"]
    sha256 = item_to_download["sha256"].split(":")[1]
    dest_subdir = item_to_download["dest_subdir"]
    filename = item_to_download["filename"]
    folder = item_to_download.get("folder")
    plugin = item_to_download.get("plugin")

    file_path = cfg.get_app_runtime_dir() / dest_subdir / filename

    Logger.info("Checking if file %s exists", shorter_path_repr(file_path))
    if file_path.exists() and not plugin:
        Logger.info("File %s already exists, skipping download", shorter_path_repr(file_path))
        return str(file_path)

    Logger.info("Downloading %s...", shorter_path_repr(url))

    return pooch.retrieve(
        url,
        sha256,
        str(file_path),
        processor=(pooch.Unzip(extract_dir=folder) if filename.endswith(".zip") else None),
    )


def from_yaml(config_path: Path) -> list[str]:
    with open(config_path, encoding="utf-8") as file:
        files_to_download: list[dict[str, str]] = yaml.load(file, Loader=yaml.FullLoader)

    all_downloads: list[str] = []
    for item in files_to_download:
        downloaded = download_from_config(item)
        if isinstance(downloaded, list):
            all_downloads.extend(downloaded)
        else:
            all_downloads.append(downloaded)
    return all_downloads


def _model_name_by_role(models: list[dict[str, str]], role: str) -> str:
    for model in models:
        if model.get("role") == role:
            return model["name"]
    raise ValueError(f"No model with role '{role}' found in models.yaml")


def _select_model_items(
    models: list[dict[str, str]], settings: Settings
) -> list[dict[str, str]]:
    """Select exactly the catalog entries used by the current desktop mode.

    Normal mode resolves CHAT + EMBEDDING. TEST_MODE swaps the default CHAT role
    for TEST. Explicit *_MODEL overrides remain authoritative and replace, rather
    than supplement, their role defaults.
    """
    chat_role = "test" if settings.TEST_MODE else "chat"
    selected_names = {
        settings.CHAT_MODEL or _model_name_by_role(models, chat_role),
        settings.EMBEDDING_MODEL or _model_name_by_role(models, "embedding"),
    }

    return [model for model in models if model.get("name") in selected_names]


def from_model_catalog(settings: Settings | None = None) -> list[str]:
    settings = settings or Settings()
    config_path = get_app_root_dir() / "configs" / "models.yaml"
    with open(config_path, encoding="utf-8") as file:
        models: list[dict[str, str]] = yaml.load(file, Loader=yaml.FullLoader)

    all_downloads: list[str] = []
    for item in _select_model_items(models, settings):
        downloaded = download_from_config(item)
        if isinstance(downloaded, list):
            all_downloads.extend(downloaded)
        else:
            all_downloads.append(downloaded)
    return all_downloads


def from_files(*files: str) -> list[str]:
    all_downloads: list[str] = []

    for config_file in files:
        config_path = get_app_root_dir() / "configs" / config_file
        all_downloads.extend(from_yaml(config_path))

    return all_downloads


__all__ = [
    "download_from_config",
    "from_yaml",
    "from_model_catalog",
    "from_files",
]
