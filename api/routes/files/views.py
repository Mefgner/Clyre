from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from fastapi.params import Depends, File
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db_session
from schemas.files import FileResponse
from schemas.general import TokenPayload
from services.file import (
    delete_user_file,
    get_files,
    index_file_in_background,
    link_file_with_project,
    link_file_with_thread,
    unlink_file_with_project,
    upload_file,
)
from utils import web

files_router = APIRouter(tags=["files"])


@files_router.post("/upload", response_model=FileResponse, status_code=201)
async def upload(
    upload: Annotated[UploadFile, File()],
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    content_type = upload.content_type or "application/octet-stream"
    try:
        return await upload_file(
            session,
            user_id=token_payload.user_id,
            name=upload.filename or "",
            content_type=content_type,
            data=await upload.read(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@files_router.get("/", response_model=list[FileResponse])
async def list_files(
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    return await get_files(session, token_payload.user_id)


@files_router.post("/{file_id}/link/thread/{thread_id}", response_model=FileResponse)
async def link_thread(
    file_id: str,
    thread_id: str,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        return await link_file_with_thread(
            session,
            user_id=token_payload.user_id,
            file_id=file_id,
            thread_id=thread_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@files_router.post("/{file_id}/link/project/{project_id}", response_model=FileResponse)
async def link_project(
    file_id: str,
    project_id: str,
    background_tasks: BackgroundTasks,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        file_metadata = await link_file_with_project(
            session,
            user_id=token_payload.user_id,
            file_id=file_id,
            project_id=project_id,
        )
        background_tasks.add_task(
            index_file_in_background,
            token_payload.user_id,
            file_metadata.id,
            project_id,
        )
        return file_metadata
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@files_router.delete("/{file_id}", status_code=204)
async def delete(
    file_id: str,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        await delete_user_file(session, user_id=token_payload.user_id, file_id=file_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@files_router.delete("/{file_id}/link/project/{project_id}", status_code=204)
async def unlink_project(
    file_id: str,
    project_id: str,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        await unlink_file_with_project(
            session,
            user_id=token_payload.user_id,
            file_id=file_id,
            project_id=project_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


__all__ = ["files_router"]
