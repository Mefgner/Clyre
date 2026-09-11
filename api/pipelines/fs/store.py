import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Protocol

from shared.pyutils.base import get_app_runtime_dir
from utils import env

Logger = logging.getLogger(__name__)


class FileStore(Protocol):
    async def save(self, user_id: str, file_id: str, data: bytes) -> None: ...
    async def read(self, user_id: str, file_id: str) -> bytes: ...
    async def delete(self, user_id: str, file_id: str) -> None: ...


def _validate_component(value: str, label: str) -> str:
    if not value or value in (".", ".."):
        raise ValueError(f"invalid {label}")
    if "/" in value or "\\" in value or "\x00" in value:
        raise ValueError(f"invalid {label}")
    return value


class LocalFileStore:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, user_id: str, file_id: str) -> Path:
        # file_id is an opaque uuid; user_id partitions the tree as defense in
        # depth on top of the ownership check enforced in CRUD.
        _validate_component(user_id, "user id")
        _validate_component(file_id, "file id")
        # Never interpolate the original filename into the path.
        candidate = (self._root / user_id / file_id).resolve()
        try:
            candidate.relative_to(self._root)
            candidate.relative_to((self._root / user_id).resolve())
        except ValueError as exc:
            raise ValueError("path escapes file storage") from exc
        return candidate

    async def save(self, user_id: str, file_id: str, data: bytes) -> None:
        path = self._path(user_id, file_id)
        await asyncio.to_thread(self._write_atomic, path, data)

    async def read(self, user_id: str, file_id: str) -> bytes:
        path = self._path(user_id, file_id)
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, user_id: str, file_id: str) -> None:
        path = self._path(user_id, file_id)
        await asyncio.to_thread(path.unlink, True)

    @staticmethod
    def _write_atomic(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                Logger.exception("Failed to clean temp upload file")
            raise


def _resolve_root() -> Path:
    root = Path(env.FILES_DIR)
    if not root.is_absolute():
        root = get_app_runtime_dir() / root
    return root.resolve()


_file_store_instance: FileStore | None = None


def get_file_store() -> FileStore:
    global _file_store_instance
    if _file_store_instance is None:
        _file_store_instance = LocalFileStore(_resolve_root())
    return _file_store_instance


__all__ = ["FileStore", "LocalFileStore", "get_file_store"]
