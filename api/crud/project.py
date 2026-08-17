from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import FileMetadata, Project


async def create_project(session: AsyncSession, *, user_id: str, title: str) -> Project:
    project = Project(user_id=user_id, title=title)
    session.add(project)
    return project


async def list_user_projects(session: AsyncSession, user_id: str) -> list[Project]:
    result = await session.execute(
        select(Project).where(Project.user_id == user_id).order_by(Project.title)
    )
    return list(result.scalars().all())


async def get_project_for_user(
    session: AsyncSession, project_id: str, user_id: str
) -> Project | None:
    result = await session.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_project_ids_for_user(
    session: AsyncSession, user_id: str, project_ids: Sequence[str] | None = None
) -> list[str]:
    stmt = select(Project.id).where(Project.user_id == user_id)
    if project_ids is not None:
        if not project_ids:
            return []
        stmt = stmt.where(Project.id.in_(project_ids))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_project_files(session: AsyncSession, project_id: str) -> list[FileMetadata]:
    result = await session.execute(
        select(FileMetadata).where(FileMetadata.project_id == project_id)
    )
    return list(result.scalars().all())


async def delete_project(session: AsyncSession, project: Project) -> None:
    await session.delete(project)


__all__ = [
    "create_project",
    "delete_project",
    "get_project_files",
    "get_project_ids_for_user",
    "get_project_for_user",
    "list_user_projects",
]
