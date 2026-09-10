from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from fastapi.params import Depends, File
from sqlalchemy.ext.asyncio import AsyncSession

from crud import get_thread_ids_for_file
from crud.generation import get_running_run_for_thread
from db import get_db_session
from pipelines.ingest import UndecodableFileText, UnsupportedFileType
from schemas.files import FileResponse
from schemas.general import TokenPayload
from services.chat_context import AttachmentLimitExceeded
from services.file import (
    FileTooLarge,
    delete_user_file,
    ensure_file_owner,
    ensure_file_thread_owner,
    get_files,
    index_file_in_background,
    link_file_with_project,
    link_file_with_thread,
    unlink_file_with_project,
    unlink_file_with_thread,
    upload_file,
)
from services.generation import GenerationConflict, get_generation_mutex, get_run
from utils import env, web

files_router = APIRouter(tags=["files"])

_UPLOAD_CHUNK_BYTES = 256 * 1024


async def _read_upload_limited(upload: UploadFile) -> bytes:
    limit = int(env.MAX_UPLOAD_BYTES)
    if limit <= 0:
        raise RuntimeError("MAX_UPLOAD_BYTES must be positive")
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = await upload.read(_UPLOAD_CHUNK_BYTES)
        if not piece:
            break
        total += len(piece)
        if total > limit:
            raise FileTooLarge(total, limit)
        chunks.append(piece)
    return b"".join(chunks)


async def _ensure_thread_idle(session: AsyncSession, thread_id: str) -> None:
    run = get_run(thread_id)
    if run is not None and not run.done:
        raise GenerationConflict("Generation already active for this thread")
    if await get_running_run_for_thread(session, thread_id) is not None:
        raise GenerationConflict("Generation already active for this thread")


@files_router.post("/upload", response_model=FileResponse, status_code=201)
async def upload(
    upload: Annotated[UploadFile, File()],
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    content_type = upload.content_type or "application/octet-stream"
    try:
        data = await _read_upload_limited(upload)
        return await upload_file(
            session,
            user_id=token_payload.user_id,
            name=upload.filename or "",
            content_type=content_type,
            data=data,
        )
    except FileTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except (UndecodableFileText, ValueError) as exc:
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
        async with get_generation_mutex():
            # Ownership first, inside the same critical section: a foreign
            # file/thread must 404 before the active-run check can 409.
            await ensure_file_thread_owner(
                session,
                user_id=token_payload.user_id,
                file_id=file_id,
                thread_id=thread_id,
            )
            await _ensure_thread_idle(session, thread_id)
            return await link_file_with_thread(
                session,
                user_id=token_payload.user_id,
                file_id=file_id,
                thread_id=thread_id,
            )
    except GenerationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AttachmentLimitExceeded as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@files_router.delete("/{file_id}/link/thread/{thread_id}", status_code=204)
async def unlink_thread(
    file_id: str,
    thread_id: str,
    token_payload: Annotated[TokenPayload, Depends(web.extract_access_token)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        async with get_generation_mutex():
            await ensure_file_thread_owner(
                session,
                user_id=token_payload.user_id,
                file_id=file_id,
                thread_id=thread_id,
            )
            await _ensure_thread_idle(session, thread_id)
            await unlink_file_with_thread(
                session,
                user_id=token_payload.user_id,
                file_id=file_id,
                thread_id=thread_id,
            )
    except GenerationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return None


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
        async with get_generation_mutex():
            # Ownership before activity: a foreign file must not reveal that
            # its threads are generating.
            await ensure_file_owner(session, user_id=token_payload.user_id, file_id=file_id)
            for linked_thread_id in await get_thread_ids_for_file(session, file_id):
                await _ensure_thread_idle(session, linked_thread_id)
            await delete_user_file(session, user_id=token_payload.user_id, file_id=file_id)
    except GenerationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return None


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
    return None


__all__ = ["files_router"]
