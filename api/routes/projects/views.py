from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db_session
from schemas.general import TokenPayload
from schemas.projects import ProjectCreateRequest, ProjectResponse, ProjectUpdateRequest
from services.project import (
    create_user_project,
    delete_user_project,
    get_projects,
    update_user_project,
)
from utils import web

projects_router = APIRouter(tags=["projects"])


@projects_router.post("/", response_model=ProjectResponse, status_code=201)
async def create(
    request: ProjectCreateRequest,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    return await create_user_project(
        session, user_id=token_payload.user_id, title=request.title
    )


@projects_router.get("/", response_model=list[ProjectResponse])
async def list_all(
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    return await get_projects(session, token_payload.user_id)


@projects_router.put("/{project_id}", response_model=ProjectResponse)
async def update(
    project_id: str,
    request: ProjectUpdateRequest,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        return await update_user_project(
            session,
            user_id=token_payload.user_id,
            project_id=project_id,
            title=request.title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@projects_router.delete("/{project_id}", status_code=204)
async def delete(
    project_id: str,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        await delete_user_project(session, user_id=token_payload.user_id, project_id=project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


__all__ = ["projects_router"]
