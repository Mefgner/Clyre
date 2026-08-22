"""Unit tests for the decoupled-generation registry (no HTTP, no DB)."""

import asyncio
import json

import pytest

import services.generation as generation_module
from services.generation import (
    GenerationRun,
    GenerationStatus,
    get_run,
    register_run,
    remove_run,
    schedule_eviction,
)


def _line(n: int) -> str:
    return json.dumps({"n": n}) + "\n"


async def _collect(iterator, limit=None, timeout=2.0):
    items = []

    async def _consume():
        async for item in iterator:
            items.append(item)
            if limit is not None and len(items) >= limit:
                break

    await asyncio.wait_for(_consume(), timeout)
    return items


async def test_subscribe_replays_buffer_from_offset_zero():
    run = GenerationRun("t1")
    for n in range(3):
        await run.publish(_line(n))
    await run.finish(GenerationStatus.FINISHED)

    collected = [line async for line in run.subscribe(0)]
    assert collected == [_line(0), _line(1), _line(2)]


async def test_subscribe_mid_offset_yields_tail_only():
    run = GenerationRun("t2")
    for n in range(3):
        await run.publish(_line(n))
    await run.finish(GenerationStatus.FINISHED)

    collected = [line async for line in run.subscribe(2)]
    assert collected == [_line(2)]


async def test_subscribe_offset_beyond_buffer_after_done_yields_nothing():
    run = GenerationRun("t3")
    await run.publish(_line(0))
    await run.finish(GenerationStatus.FINISHED)

    assert [line async for line in run.subscribe(10)] == []


async def test_subscribe_follows_live_events_until_terminal():
    run = GenerationRun("t4")
    consumer = asyncio.create_task(_collect(run.subscribe(0)))

    await asyncio.sleep(0.01)
    await run.publish(_line(1))
    await asyncio.sleep(0.01)
    await run.publish(_line(2))
    await asyncio.sleep(0.01)
    await run.finish(GenerationStatus.FINISHED)

    await asyncio.wait_for(consumer, timeout=2)
    assert consumer.result() == [_line(1), _line(2)]
    assert run.done


async def test_cancel_cancels_attached_task_and_is_noop_when_done():
    run = GenerationRun("t5")

    async def hang():
        await asyncio.sleep(60)

    task = asyncio.create_task(hang())
    run.attach_task(task)
    await asyncio.sleep(0)
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)

    run.cancel()

    await run.finish(GenerationStatus.STOPPED)
    run.cancel()


async def test_registry_accessors_and_eviction(monkeypatch):
    monkeypatch.setattr(generation_module, "EVENTS_GRACE_SECONDS", 0.05)
    run = GenerationRun("t6")
    register_run(run)
    assert get_run("t6") is run

    schedule_eviction(run)
    remove_run("t6")
    assert get_run("t6") is None

    register_run(run)
    schedule_eviction(run)
    await asyncio.sleep(generation_module.EVENTS_GRACE_SECONDS + 0.1)
    assert get_run("t6") is None


async def test_register_run_cancels_pending_eviction(monkeypatch):
    """A stale eviction timer from a finished run must not evict a newer run
    registered on the same thread within the grace window."""
    monkeypatch.setattr(generation_module, "EVENTS_GRACE_SECONDS", 0.05)
    first = GenerationRun("t7")
    register_run(first)
    await first.finish(GenerationStatus.FINISHED)
    schedule_eviction(first)

    second = GenerationRun("t7")
    register_run(second)
    await asyncio.sleep(generation_module.EVENTS_GRACE_SECONDS + 0.1)
    assert get_run("t7") is second

    await second.finish(GenerationStatus.FINISHED)
    schedule_eviction(second)
    await asyncio.sleep(generation_module.EVENTS_GRACE_SECONDS + 0.1)
    assert get_run("t7") is None
