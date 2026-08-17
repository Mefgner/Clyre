import logging

from sqlalchemy.ext.asyncio import AsyncSession

from crud.project import (
    create_project,
    delete_project,
    get_project_files,
    get_project_for_user,
    list_user_projects,
)
from crud.vector import VectorRepository, get_vector_repository
from services.ingestion import _purge_file_vectors

Logger = logging.getLogger(__name__)


async def create_user_project(session: AsyncSession, *, user_id: str, title: str):
    project = await create_project(session, user_id=user_id, title=title.strip())
    await session.commit()
    return project


async def get_projects(session: AsyncSession, user_id: str):
    return await list_user_projects(session, user_id)


async def update_user_project(
    session: AsyncSession, *, user_id: str, project_id: str, title: str
):
    project = await get_project_for_user(session, project_id, user_id)
    if not project:
        raise ValueError("Project not found")
    project.title = title.strip()
    session.add(project)
    await session.commit()
    return project


async def delete_user_project(
    session: AsyncSession,
    *,
    user_id: str,
    project_id: str,
    repository: VectorRepository | None = None,
) -> None:
    project = await get_project_for_user(session, project_id, user_id)
    if not project:
        raise ValueError("Project not found")
    repository = repository or get_vector_repository()

    try:
        for file_metadata in await get_project_files(session, project.id):
            await _purge_file_vectors(session, file_metadata.id, repository)
            file_metadata.project_id = None
            file_metadata.index_status = "not_indexed"
            file_metadata.index_error = None
            file_metadata.indexed_at = None
            session.add(file_metadata)
        await delete_project(session, project)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


__all__ = [
    "create_user_project",
    "delete_user_project",
    "get_projects",
    "update_user_project",
]
