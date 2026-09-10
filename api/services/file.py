import contextlib
import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from crud.file import (
    count_thread_files,
    create_file,
    delete_file,
    get_file_for_user,
    get_project_link,
    get_thread_link,
    link_file_to_project,
    link_file_to_thread,
    list_user_files,
)
from crud.project import get_project_for_user
from crud.thread import get_thread_by_id
from crud.vector import VectorRepository, get_vector_repository
from db import get_session_manager
from models import FileMetadata
from pipelines.fs import FileStore, get_file_store
from pipelines.ingest import (
    UndecodableFileText,
    UnsupportedFileType,
    extract_text,
    is_supported_text_type,
    normalize_content_type,
)
from services.chat_context import AttachmentLimitExceeded
from services.ingestion import _purge_file_vectors
from utils import env, hashing

Logger = logging.getLogger(__name__)


class FileTooLarge(ValueError):
    def __init__(self, size: int, limit: int):
        super().__init__(f"file size {size} exceeds limit of {limit} bytes")
        self.size = size
        self.limit = limit


def _positive(name: str, value: int) -> int:
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


def _validate_upload_payload(name: str, content_type: str, data: bytes) -> str:
    if not name.strip():
        raise ValueError("filename is required")
    limit = _positive("MAX_UPLOAD_BYTES", int(env.MAX_UPLOAD_BYTES))
    if len(data) > limit:
        raise FileTooLarge(len(data), limit)
    normalized = normalize_content_type(content_type)
    if not is_supported_text_type(content_type, name):
        raise UnsupportedFileType(content_type or name or "unknown content type")
    # Strict UTF-8 with BOM support; NUL rejected. Empty text is allowed.
    extract_text(data, content_type=content_type, filename=name)
    return normalized


def _head_value(data: bytes, *, content_type: str, filename: str) -> str | None:
    try:
        return extract_text(data, content_type=content_type, filename=filename)[:128]
    except (UnsupportedFileType, UndecodableFileText, ValueError):
        return None


async def upload_file(
    session: AsyncSession,
    *,
    user_id: str,
    name: str,
    content_type: str,
    data: bytes,
    file_store: FileStore | None = None,
) -> FileMetadata:
    normalized = _validate_upload_payload(name, content_type, data)

    file_store = file_store or get_file_store()
    file_id = hashing.generate_uuid()
    file_metadata = await create_file(
        session,
        file_id=file_id,
        user_id=user_id,
        name=name,
        content_type=normalized or content_type,
        head_value=_head_value(data, content_type=content_type, filename=name),
    )
    saved = False
    try:
        await session.flush()
        await file_store.save(user_id, file_id, data)
        saved = True
        file_metadata.creation_date = date.today()
        await session.commit()
        return file_metadata
    except Exception:
        await session.rollback()
        if saved:
            with contextlib.suppress(Exception):
                await file_store.delete(user_id, file_id)
        raise


async def get_user_file(session: AsyncSession, user_id: str, file_id: str) -> FileMetadata:
    file_metadata = await get_file_for_user(session, file_id, user_id)
    if not file_metadata:
        raise ValueError("File not found")
    return file_metadata


async def ensure_file_owner(
    session: AsyncSession, *, user_id: str, file_id: str
) -> FileMetadata:
    """Ownership pre-check: must run *before* any activity check.

    A foreign or missing file has to answer 404 even when the thread it is
    linked to is generating — otherwise a 409 would confirm its existence.
    """
    return await get_user_file(session, user_id, file_id)


async def ensure_file_thread_owner(
    session: AsyncSession, *, user_id: str, file_id: str, thread_id: str
) -> FileMetadata:
    """Same pre-check for mutations that touch a file and a thread.

    Ownership is resolved inside the generation mutex but before the
    active-run check, so foreign targets never leak state via 409-vs-404.
    """
    file_metadata = await ensure_file_owner(session, user_id=user_id, file_id=file_id)
    thread = await get_thread_by_id(session, thread_id, user_id, load_messages=False)
    if not thread:
        raise ValueError("Thread not found")
    return file_metadata


async def get_files(session: AsyncSession, user_id: str) -> list[FileMetadata]:
    return await list_user_files(session, user_id)


async def link_file_with_thread(
    session: AsyncSession, *, user_id: str, file_id: str, thread_id: str
) -> FileMetadata:
    file_metadata = await ensure_file_thread_owner(
        session, user_id=user_id, file_id=file_id, thread_id=thread_id
    )
    if await get_thread_link(session, file_id, thread_id):
        # Re-attaching an existing link stays a no-op success.
        await session.commit()
        return file_metadata
    # Same cap as the chat start union: every addition counts, so sequential
    # attach calls can never push a thread past the limit.
    limit = _positive("MAX_THREAD_ATTACHMENTS", int(env.MAX_THREAD_ATTACHMENTS))
    linked = await count_thread_files(session, thread_id)
    if linked >= limit:
        raise AttachmentLimitExceeded(linked + 1, limit)
    await link_file_to_thread(session, file_id, thread_id)
    await session.commit()
    return file_metadata


async def unlink_file_with_thread(
    session: AsyncSession, *, user_id: str, file_id: str, thread_id: str
) -> None:
    # Idempotent: missing link is still success when the owned file and
    # thread both exist (DELETE .../link/thread/... -> 204).
    await ensure_file_thread_owner(
        session, user_id=user_id, file_id=file_id, thread_id=thread_id
    )
    link = await get_thread_link(session, file_id, thread_id)
    if link is None:
        return
    await session.delete(link)
    await session.commit()


async def link_file_with_project(
    session: AsyncSession, *, user_id: str, file_id: str, project_id: str
) -> FileMetadata:
    file_metadata = await get_user_file(session, user_id, file_id)
    project = await get_project_for_user(session, project_id, user_id)
    if not project:
        raise ValueError("Project not found")
    if file_metadata.project_id and file_metadata.project_id != project_id:
        raise ValueError("File is already indexed for another project")
    if not await get_project_link(session, file_id, project_id):
        await link_file_to_project(session, file_id, project_id)
    file_metadata.project_id = project_id
    file_metadata.index_status = "pending"
    file_metadata.index_error = None
    file_metadata.indexed_at = None
    session.add(file_metadata)
    await session.commit()
    return file_metadata


async def unlink_file_with_project(
    session: AsyncSession,
    *,
    user_id: str,
    file_id: str,
    project_id: str,
    repository: VectorRepository | None = None,
) -> None:
    file_metadata = await get_user_file(session, user_id, file_id)
    project = await get_project_for_user(session, project_id, user_id)
    if not project:
        raise ValueError("Project not found")
    link = await get_project_link(session, file_id, project_id)
    if not link:
        raise ValueError("File is not linked to the project")

    repository = repository or get_vector_repository()
    try:
        await _purge_file_vectors(session, file_id, repository)
        if file_metadata.project_id == project_id:
            file_metadata.project_id = None
            file_metadata.index_status = "not_indexed"
            file_metadata.index_error = None
            file_metadata.indexed_at = None
            session.add(file_metadata)
        await session.delete(link)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def index_file_in_background(user_id: str, file_id: str, project_id: str) -> None:
    from services.ingestion import index_file_for_project

    session_manager = get_session_manager()
    async with session_manager.async_session_maker() as session:
        try:
            file_metadata = await get_user_file(session, user_id, file_id)
            await index_file_for_project(session, file_metadata, project_id)
        except Exception as exc:
            await session.rollback()
            try:
                file_metadata = await get_user_file(session, user_id, file_id)
                file_metadata.index_status = "failed"
                file_metadata.index_error = str(exc)[:2000]
                session.add(file_metadata)
                await session.commit()
            except Exception:
                await session.rollback()
            Logger.exception("Failed to index file %s for project %s", file_id, project_id)


async def delete_user_file(
    session: AsyncSession,
    *,
    user_id: str,
    file_id: str,
    repository: VectorRepository | None = None,
    file_store: FileStore | None = None,
) -> None:
    file_metadata = await get_user_file(session, user_id, file_id)
    repository = repository or get_vector_repository()
    file_store = file_store or get_file_store()

    # Delete metadata first: a failed commit must not strand a live row
    # without its bytes. Blob cleanup after commit is best-effort and only
    # logged (never leaks file content).
    try:
        await _purge_file_vectors(session, file_metadata.id, repository)
        await delete_file(session, file_metadata)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    try:
        await file_store.delete(user_id, file_metadata.id)
    except Exception:
        Logger.exception("Blob cleanup failed for file id=%s", file_metadata.id)


__all__ = [
    "FileTooLarge",
    "delete_user_file",
    "ensure_file_owner",
    "ensure_file_thread_owner",
    "get_files",
    "get_user_file",
    "index_file_in_background",
    "link_file_with_project",
    "link_file_with_thread",
    "unlink_file_with_project",
    "unlink_file_with_thread",
    "upload_file",
]
