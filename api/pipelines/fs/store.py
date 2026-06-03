import asyncio
import logging
from pathlib import Path
from typing import Protocol

from shared.pyutils.base import get_app_root_dir
from utils import env

Logger = logging.getLogger(__name__)


class FileStore(Protocol):
    async def save(self, user_id: str, file_id: str, data: bytes) -> None: ...
    async def read(self, user_id: str, file_id: str) -> bytes: ...
    async def delete(self, user_id: str, file_id: str) -> None: ...


class LocalFileStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, user_id: str, file_id: str) -> Path:
        # file_id is an opaque uuid; user_id partitions the tree as defense in
        # depth on top of the ownership check enforced in CRUD.
        return self._root / user_id / file_id

    async def save(self, user_id: str, file_id: str, data: bytes) -> None:
        path = self._path(user_id, file_id)
        await asyncio.to_thread(self._write, path, data)

    async def read(self, user_id: str, file_id: str) -> bytes:
        path = self._path(user_id, file_id)
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, user_id: str, file_id: str) -> None:
        path = self._path(user_id, file_id)
        await asyncio.to_thread(path.unlink, True)

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _resolve_root() -> Path:
    root = Path(env.FILES_DIR)
    if not root.is_absolute():
        root = get_app_root_dir() / root
    return root.resolve()


_file_store_instance: FileStore | None = None


def get_file_store() -> FileStore:
    global _file_store_instance
    if _file_store_instance is None:
        _file_store_instance = LocalFileStore(_resolve_root())
    return _file_store_instance


__all__ = ["FileStore", "LocalFileStore", "get_file_store"]
