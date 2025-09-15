from pathlib import Path

import pooch
import yaml

from utils import cfg


def _download_from_config(item_to_download: dict[str, str]) -> str:
    url = item_to_download['url']
    sha256 = item_to_download['sha256']
    dest_subdir = item_to_download['dest_subdir']
    filename = item_to_download['filename']

    file_path = str(cfg.get_app_runtime_dir() / dest_subdir / sha256.split(':')[1] / filename)

    if filename.rsplit('.', 1)[0] in (cfg.get_app_runtime_dir() / dest_subdir).glob('*'):
        return file_path

    return pooch.retrieve(
        url, sha256, file_path,
        processor=pooch.Unzip() if filename.endswith('.zip') else None
    )


def predownload(*files: str) -> list[str]:
    all_downloads = list()

    for config_file in files:
        with open(cfg.get_app_root_dir() / 'configs' / config_file) as file:
            files_to_download: list[dict[str, str]] = yaml.load(file.read(), Loader=yaml.FullLoader)

            for download in files_to_download:
                file = _download_from_config(download)
                if Path(file[0]).parent.suffix == '.unzip':
                    unpacked_path = Path(file[0]).parent
                    try:
                        unpacked_path.rename(unpacked_path.parent / unpacked_path.name.rsplit('.', 2)[0])
                    except FileExistsError:
                        continue

                all_downloads += file

    return all_downloads


__all__ = ["predownload"]
