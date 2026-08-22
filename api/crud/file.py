from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import FileHasProject, FileHasThread, FileMetadata


async def create_file(
    session: AsyncSession,
    *,
    file_id: str,
    user_id: str,
    name: str,
    content_type: str,
    head_value: str | None,
) -> FileMetadata:
    file_metadata = FileMetadata(
        id=file_id,
        user_id=user_id,
        name=name,
        content_type=content_type,
        head_value=head_value,
    )
    session.add(file_metadata)
    return file_metadata


async def get_file_for_user(
    session: AsyncSession, file_id: str, user_id: str
) -> FileMetadata | None:
    result = await session.execute(
        select(FileMetadata).where(FileMetadata.id == file_id, FileMetadata.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_user_files(session: AsyncSession, user_id: str) -> list[FileMetadata]:
    result = await session.execute(
        select(FileMetadata).where(FileMetadata.user_id == user_id).order_by(FileMetadata.name)
    )
    return list(result.scalars().all())


async def get_project_index_statuses(
    session: AsyncSession, project_ids: Sequence[str]
) -> dict[str, set[str]]:
    if not project_ids:
        return {}
    result = await session.execute(
        select(FileMetadata.project_id, FileMetadata.index_status).where(
            FileMetadata.project_id.in_(project_ids)
        )
    )
    statuses: dict[str, set[str]] = {}
    for project_id, index_status in result:
        statuses.setdefault(project_id, set()).add(index_status)
    return statuses


async def list_project_files(session: AsyncSession, project_id: str) -> list[FileMetadata]:
    result = await session.execute(
        select(FileMetadata)
        .where(FileMetadata.project_id == project_id)
        .order_by(FileMetadata.name)
    )
    return list(result.scalars().all())


async def get_owned_file_ids(
    session: AsyncSession, file_ids: Sequence[str], user_id: str
) -> set[str]:
    if not file_ids:
        return set()
    result = await session.execute(
        select(FileMetadata.id).where(
            FileMetadata.id.in_(file_ids), FileMetadata.user_id == user_id
        )
    )
    return set(result.scalars().all())


async def delete_file(session: AsyncSession, file_metadata: FileMetadata) -> None:
    await session.delete(file_metadata)


async def get_thread_link(
    session: AsyncSession, file_id: str, thread_id: str
) -> FileHasThread | None:
    result = await session.execute(
        select(FileHasThread).where(
            FileHasThread.file_id == file_id,
            FileHasThread.thread_id == thread_id,
        )
    )
    return result.scalar_one_or_none()


async def get_project_link(
    session: AsyncSession, file_id: str, project_id: str
) -> FileHasProject | None:
    result = await session.execute(
        select(FileHasProject).where(
            FileHasProject.file_id == file_id,
            FileHasProject.project_id == project_id,
        )
    )
    return result.scalar_one_or_none()


async def link_file_to_thread(
    session: AsyncSession, file_id: str, thread_id: str
) -> FileHasThread:
    link = FileHasThread(file_id=file_id, thread_id=thread_id)
    session.add(link)
    return link


async def link_file_to_project(
    session: AsyncSession, file_id: str, project_id: str
) -> FileHasProject:
    link = FileHasProject(file_id=file_id, project_id=project_id)
    session.add(link)
    return link


__all__ = [
    "create_file",
    "delete_file",
    "get_file_for_user",
    "get_project_link",
    "get_project_index_statuses",
    "get_owned_file_ids",
    "get_thread_link",
    "link_file_to_project",
    "link_file_to_thread",
    "list_project_files",
    "list_user_files",
]
