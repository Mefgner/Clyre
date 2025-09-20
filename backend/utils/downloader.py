import logging
import re
from pathlib import Path

import pooch
import yaml

import utils.base
from utils import cfg


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


def _download_from_config(item_to_download: dict[str, str]) -> str:
    url = item_to_download["url"]
    sha256 = item_to_download["sha256"].split(":")[1]
    dest_subdir = item_to_download["dest_subdir"]
    filename = item_to_download["filename"]
    folder = item_to_download.get("folder")

    Logger.info("Downloading %s...", shorter_path_repr(url))

    if folder:
        folder = cfg.get_app_runtime_dir() / dest_subdir / sha256 / folder
        Logger.info("Checking if folder %s exists", shorter_path_repr(folder))
        if folder.exists():
            Logger.info(
                "Folder %s already exists, skipping download", shorter_path_repr(folder)
            )
            return str(folder)

    file_path = cfg.get_app_runtime_dir() / dest_subdir / sha256 / filename

    Logger.info("Checking if file %s exists", shorter_path_repr(file_path))
    if file_path.exists():
        Logger.info("File %s already exists, skipping download", shorter_path_repr(file_path))
        return str(file_path)

    return pooch.retrieve(
        url,
        sha256,
        str(file_path),
        processor=(pooch.Unzip(extract_dir=folder) if filename.endswith(".zip") else None),
    )


def predownload(*files: str) -> list[str]:
    all_downloads = []

    for config_file in files:
        with open(
            utils.base.get_app_root_dir() / "configs" / config_file, encoding="utf-8"
        ) as file:
            files_to_download: list[dict[str, str]] = yaml.load(
                file.read(), Loader=yaml.FullLoader
            )

            for download in files_to_download:
                file = _download_from_config(download)
                all_downloads += file

    return all_downloads


__all__ = ["predownload"]
