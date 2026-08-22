from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import GenerationRunRow
from utils import timing


async def create_generation_run(
    session: AsyncSession, thread_id: str, user_id: str
) -> GenerationRunRow:
    row = GenerationRunRow(thread_id=thread_id, user_id=user_id, status="running")
    session.add(row)
    return row


async def finish_generation_run(
    session: AsyncSession, run: GenerationRunRow, status: str
) -> None:
    run.status = status
    run.update_time = timing.get_utc_now()
    session.add(run)


async def get_running_generation_runs(session: AsyncSession) -> list[GenerationRunRow]:
    result = await session.execute(
        select(GenerationRunRow).where(GenerationRunRow.status == "running")
    )
    return list(result.scalars().all())


async def get_running_run_thread_ids(session: AsyncSession, user_id: str) -> list[str]:
    result = await session.execute(
        select(GenerationRunRow.thread_id).where(
            GenerationRunRow.user_id == user_id, GenerationRunRow.status == "running"
        )
    )
    return list(result.scalars().all())


async def get_running_run_for_thread(
    session: AsyncSession, thread_id: str
) -> GenerationRunRow | None:
    result = await session.execute(
        select(GenerationRunRow).where(
            GenerationRunRow.thread_id == thread_id, GenerationRunRow.status == "running"
        )
    )
    return result.scalars().first()


def mark_interrupted(run: GenerationRunRow) -> None:
    run.status = "interrupted"
    run.update_time = timing.get_utc_now()


__all__ = [
    "create_generation_run",
    "finish_generation_run",
    "get_running_generation_runs",
    "get_running_run_for_thread",
    "get_running_run_thread_ids",
    "mark_interrupted",
]
