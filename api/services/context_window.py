from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from models import Message
from pipelines.inference import ContextLimitExceeded, get_output_reserve
from services.chat_context import AttachedFile, build_chat_context


@dataclass(frozen=True, slots=True)
class ContextWindow:
    """Exact prompt selection plus the metadata exposed on the NDJSON stream."""

    prompt: list[dict[str, str]]
    included_messages: int
    omitted_messages: int
    first_included_order: int
    prompt_tokens: int
    slot_tokens: int
    reserved_output_tokens: int
    measured_exactly: bool = True


def _visible_messages(messages: Sequence[Message]) -> list[Message]:
    visible = [
        message
        for message in messages
        if message.role != "system"
        and not (message.role == "assistant" and message.inline_value is None)
    ]
    return sorted(visible, key=lambda message: message.order)


def _complete_suffix_turns(messages: Sequence[Message]) -> list[tuple[Message, Message]]:
    """Return the contiguous suffix of complete user+assistant turns."""
    turns_reversed: list[tuple[Message, Message]] = []
    index = len(messages) - 1
    if index >= 0 and messages[index].role == "user":
        index -= 1

    while index >= 1:
        assistant = messages[index]
        user = messages[index - 1]
        if assistant.role != "assistant" or user.role != "user":
            break
        turns_reversed.append((user, assistant))
        index -= 2

    turns_reversed.reverse()
    return turns_reversed


def _flatten_turns(turns: Sequence[tuple[Message, Message]]) -> list[Message]:
    return [message for turn in turns for message in turn]


async def select_context_window(
    history: Sequence[Message],
    current: Message,
    attached_files: Sequence[AttachedFile],
    *,
    base_prompt: str,
    inference: Any,
    enable_thinking: bool | None,
) -> ContextWindow:
    """Select the largest continuous suffix of complete historical turns that fits.

    The mandatory minimum is always system prompt + selected files + current request +
    the configured output reserve. Every production boundary is measured from the actual
    chat-template prompt and target-model tokenizer; persisted token counts are never used.
    """
    if current.role != "user":
        raise ValueError("Current context-window message must have role=user")

    visible = _visible_messages(history)
    turns = _complete_suffix_turns(visible)
    reserve = get_output_reserve()

    render_prompt = getattr(inference, "render_prompt", None)
    count_prompt_tokens = getattr(inference, "count_prompt_tokens", None)
    get_slot_context_tokens = getattr(inference, "get_slot_context_tokens", None)
    exact_interfaces = all(
        callable(interface)
        for interface in (render_prompt, count_prompt_tokens, get_slot_context_tokens)
    )

    slot_tokens: int | None = None
    if exact_interfaces:
        slot_tokens = await get_slot_context_tokens()
    observed_slot: list[int | None] = [slot_tokens]

    async def measure(
        candidate_history: Sequence[Message],
    ) -> tuple[list[dict[str, str]], int, bool]:
        prompt = build_chat_context(
            [*candidate_history, current], attached_files, base_prompt=base_prompt
        )
        if exact_interfaces:
            rendered = await render_prompt(prompt, enable_thinking)
            prompt_tokens = await count_prompt_tokens(rendered)
            assert slot_tokens is not None
            return prompt, prompt_tokens, prompt_tokens + reserve <= slot_tokens

        # Compatibility for existing unit-test doubles only. Production LLMPipeline always
        # exposes the exact interfaces above and never approximates selection.
        check_token_budget = getattr(inference, "check_token_budget")
        try:
            prompt_tokens = await check_token_budget(prompt, enable_thinking)
        except ContextLimitExceeded as exc:
            observed_slot[0] = exc.slot_tokens
            return prompt, exc.prompt_tokens, False
        return prompt, prompt_tokens, True

    minimum_prompt, minimum_tokens, minimum_fits = await measure([])
    if not minimum_fits:
        effective_slot = observed_slot[0] or max(minimum_tokens, 1)
        raise ContextLimitExceeded(minimum_tokens, effective_slot, reserve)

    low = 0
    high = len(turns)
    cache: dict[int, tuple[list[dict[str, str]], int]] = {0: (minimum_prompt, minimum_tokens)}
    while low < high:
        middle = (low + high + 1) // 2
        candidate_messages = _flatten_turns(turns[-middle:])
        prompt, prompt_tokens, fits = await measure(candidate_messages)
        if fits:
            cache[middle] = (prompt, prompt_tokens)
            low = middle
        else:
            high = middle - 1

    selected_turns = turns[-low:] if low else []
    selected_messages = _flatten_turns(selected_turns)
    if low not in cache:
        prompt, prompt_tokens, fits = await measure(selected_messages)
        if not fits:  # pragma: no cover - binary-search invariant
            raise RuntimeError("Context-window selector ended on a non-fitting boundary")
        cache[low] = (prompt, prompt_tokens)

    prompt, prompt_tokens = cache[low]
    included_messages = len(selected_messages) + 1
    omitted_messages = len(visible) + 1 - included_messages
    first_included_order = selected_messages[0].order if selected_messages else current.order
    effective_slot = observed_slot[0] or (prompt_tokens + reserve)

    return ContextWindow(
        prompt=prompt,
        included_messages=included_messages,
        omitted_messages=omitted_messages,
        first_included_order=first_included_order,
        prompt_tokens=prompt_tokens,
        slot_tokens=effective_slot,
        reserved_output_tokens=reserve,
        measured_exactly=exact_interfaces,
    )
