"""Shared NDJSON-stream helpers for live e2e tests."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

CHUNK_EVENTS = ("new_chunk", "new_thinking_chunk")


def parse_line(line: str) -> dict[str, Any]:
    return json.loads(line)


async def iter_events(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    async for line in response.aiter_lines():
        line = line.strip()
        if line:
            yield parse_line(line)


async def drain_events(response: httpx.Response) -> list[dict[str, Any]]:
    return [event async for event in iter_events(response)]


@asynccontextmanager
async def open_stream(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> AsyncIterator[httpx.Response]:
    async with client.stream(
        "POST", url, headers=headers, json=json_body, params=params
    ) as response:
        assert response.status_code == 200, await response.aread()
        yield response


def chunk_texts(events: list[dict[str, Any]], event_name: str) -> str:
    return "".join(event["chunk"] or "" for event in events if event["event"] == event_name)


def assert_stream_contract(events: list[dict[str, Any]]) -> str:
    """Pin the NDJSON wire contract; returns the thread id of the run."""
    assert events, "stream produced no events"
    first = events[0]
    assert first["event"] == "user_message_insert"
    assert first["chunk"] is None
    thread_id = first["threadId"]
    assert thread_id

    last_pair = events[-2:]
    assert [event["event"] for event in last_pair] == [
        "assistant_message_insert",
        "done",
    ]
    assert last_pair[0]["threadId"] == thread_id
    assert last_pair[1] == {"chunk": None, "event": "done", "threadId": None}

    for event in events[1:-2]:
        assert event["event"] in CHUNK_EVENTS
        assert isinstance(event["chunk"], str)
        assert event["threadId"] is None
    return thread_id
