"""Live e2e for the decoupled-generation pub/sub core (`GenerationRun`) against
the real model: multi-subscriber fan-out, unsubscribe tolerance, offset replay.

These semantics are only reachable at the service level today — POST /api/chat/
stream always starts a NEW generation and cannot re-attach to a live run (see
docs/known-issues.md). Requires the e2e docker stack.
"""

import asyncio

import pytest
from conftest import AuthContext
from helpers import assert_stream_contract, parse_line

import db
from services.chatting import ChattingService
from services.generation import GenerationRun, GenerationStatus

pytestmark = pytest.mark.e2e

# Enough tokens that subscribers can join/leave while the run is still live.
PROMPT = "Count slowly from one to ten in English words."


async def _start_generation(auth: AuthContext) -> GenerationRun:
    service = ChattingService()
    maker = db.get_session_manager().async_session_maker
    async with maker() as session:
        return await service.start_generation(session, None, auth.user_id, PROMPT)


async def _drain(stream) -> list[str]:
    collected: list[str] = []
    async for line in stream:
        collected.append(line)
    return collected


async def _read_first_lines(run: GenerationRun, count: int) -> list[str]:
    """Subscribe, take `count` lines, then unsubscribe (abandon the stream)."""
    stream = run.subscribe(0)
    collected: list[str] = []
    try:
        async for line in stream:
            collected.append(line)
            if len(collected) >= count:
                break
    finally:
        await stream.aclose()
    return collected


async def test_concurrent_subscribers_receive_identical_streams(app_client, auth: AuthContext):
    run = await _start_generation(auth)
    lines_a, lines_b = await asyncio.gather(
        _drain(run.subscribe(0)),
        _drain(run.subscribe(0)),
    )
    assert lines_a == lines_b
    assert_stream_contract([parse_line(line) for line in lines_a])

    await run.wait_done()
    assert run.status is GenerationStatus.FINISHED


async def test_unsubscribe_and_rejoin_from_offset(app_client, auth: AuthContext):
    run = await _start_generation(auth)

    early = await _read_first_lines(run, 3)
    assert parse_line(early[0])["event"] == "user_message_insert"

    await run.wait_done()
    assert run.status is GenerationStatus.FINISHED

    full = await _drain(run.subscribe(0))
    assert len(full) > 3
    # The abandoned consumer saw a byte-identical prefix of the buffered stream.
    assert full[: len(early)] == early
    assert_stream_contract([parse_line(line) for line in full])

    # Late join near the end replays exactly the terminal pair.
    tail = await _drain(run.subscribe(len(full) - 2))
    assert [parse_line(line)["event"] for line in tail] == [
        "assistant_message_insert",
        "done",
    ]
