import asyncio
import logging
from collections.abc import AsyncGenerator
from enum import Enum

from crud.generation import get_running_generation_runs, mark_interrupted
from crud.message import delete_unwritten_assistant_rows
from db import get_session_manager
from models import GenerationRunRow

Logger = logging.getLogger(__name__)

# Late reconnects may still replay the buffered events this long after the run
# reached a terminal state. Patchable in tests.
EVENTS_GRACE_SECONDS = 30.0

# How often a running generation flushes its partial content into the reserved
# assistant message row. Patchable in tests.
PARTIAL_FLUSH_SECONDS = 1.0


async def sweep_interrupted_runs() -> int:
    """Mark orphaned running journal rows as interrupted (startup recovery).

    Also deletes assistant rows those runs reserved but never wrote: a
    NULL-content assistant turn left in place poisons every later prompt
    for its thread.
    """
    async with get_session_manager().async_session_maker() as session:
        rows: list[GenerationRunRow] = await get_running_generation_runs(session)
        for row in rows:
            mark_interrupted(row)
        if rows:
            deleted = await delete_unwritten_assistant_rows(
                session, [row.thread_id for row in rows]
            )
            if deleted:
                Logger.warning("Deleted %d unwritten assistant message(s)", deleted)
            Logger.warning("Marked %d interrupted generation run(s)", len(rows))
        await session.commit()
        return len(rows)


class GenerationStatus(str, Enum):
    RUNNING = "running"
    FINISHED = "finished"
    STOPPED = "stopped"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class GenerationConflict(RuntimeError):
    """Another generation is already active for the thread, or nothing to retry."""


class GenerationRun:
    """One decoupled chat generation owned by the runtime, not by a connection.

    Buffers every NDJSON event line at a stable integer offset so any number of
    subscribers can (re)join from an arbitrary offset exactly once. Subscribers
    wait on a condition instead of queues: the publisher can never be blocked
    or dropped by a slow consumer.
    """

    def __init__(self, thread_id: str, journal_id: str | None = None):
        self.thread_id = thread_id
        self.journal_id = journal_id
        self.status = GenerationStatus.RUNNING
        self.response = ""
        self.thinking = ""
        self.last_flush = 0.0
        self._stop_requested = False
        self._events: list[str] = []
        self._cond: asyncio.Condition = asyncio.Condition()
        self._task: asyncio.Task | None = None

    def attach_task(self, task: asyncio.Task) -> None:
        self._task = task

    def cancel(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()

    def request_stop(self) -> bool:
        """Idempotent stop: True exactly once, then False while stopping/finished.

        Cancellation is asynchronous — the task keeps flushing partial output
        for a while after cancel() — so a second stop request in that window
        must already report "not active".
        """
        if self._stop_requested or self.done:
            return False
        self._stop_requested = True
        self.cancel()
        return True

    @property
    def done(self) -> bool:
        return self.status is not GenerationStatus.RUNNING

    async def wait_done(self) -> None:
        if self._task is not None:
            await asyncio.shield(self._task)

    async def publish(self, event_line: str) -> None:
        async with self._cond:
            self._events.append(event_line)
            self._cond.notify_all()

    async def finish(self, status: GenerationStatus) -> None:
        async with self._cond:
            self.status = status
            self._cond.notify_all()

    async def subscribe(self, offset: int = 0) -> AsyncGenerator[str, None]:
        """Yield buffered events from `offset`, then follow live until terminal."""
        index = max(offset, 0)
        while True:
            async with self._cond:
                while index >= len(self._events) and not self.done:
                    await self._cond.wait()
            while index < len(self._events):
                yield self._events[index]
                index += 1
            if self.done and index >= len(self._events):
                return


_runs: dict[str, GenerationRun] = {}
_eviction_timers: dict[str, asyncio.TimerHandle] = {}


def register_run(run: GenerationRun) -> None:
    _runs[run.thread_id] = run
    # A finished run arms a delayed eviction for its thread; a new run on the
    # same thread must cancel it, or the stale timer would evict the live run.
    pending = _eviction_timers.pop(run.thread_id, None)
    if pending is not None:
        pending.cancel()


def get_run(thread_id: str) -> GenerationRun | None:
    return _runs.get(thread_id)


def remove_run(thread_id: str) -> None:
    _runs.pop(thread_id, None)


def active_run_thread_ids() -> set[str]:
    return {thread_id for thread_id, run in _runs.items() if not run.done}


def _evict_run(thread_id: str) -> None:
    _eviction_timers.pop(thread_id, None)
    remove_run(thread_id)


def schedule_eviction(run: GenerationRun) -> None:
    loop = asyncio.get_running_loop()
    stale = _eviction_timers.get(run.thread_id)
    if stale is not None:
        stale.cancel()
    _eviction_timers[run.thread_id] = loop.call_later(
        EVENTS_GRACE_SECONDS, _evict_run, run.thread_id
    )
