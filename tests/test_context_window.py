import pytest

from models import Message
from pipelines.inference import ContextLimitExceeded
from services.context_window import select_context_window


def _message(role: str, order: int, content: str) -> Message:
    return Message(
        role=role,
        order=order,
        inline_value=content,
        thinking_value=None,
        hash="",
        user_id="test-user",
        thread_id="test-thread",
    )


class ExactBudgetFake:
    def __init__(self, slot_tokens: int):
        self.slot_tokens = slot_tokens
        self.rendered_histories: list[list[dict[str, str]]] = []

    async def render_prompt(self, history, enable_thinking=None):
        self.rendered_histories.append(list(history))
        return "\n".join(message["content"] for message in history)

    async def count_prompt_tokens(self, prompt: str):
        return len(prompt.split())

    async def get_slot_context_tokens(self):
        return self.slot_tokens


async def test_selector_keeps_largest_suffix_of_complete_turns(monkeypatch):
    monkeypatch.setattr("services.context_window.get_output_reserve", lambda: 4)
    history = [
        _message("user", 0, "old user words"),
        _message("assistant", 1, "old assistant words"),
        _message("user", 2, "recent user words"),
        _message("assistant", 3, "recent assistant words"),
    ]
    current = _message("user", 4, "current request now")
    fake = ExactBudgetFake(slot_tokens=18)

    window = await select_context_window(
        history,
        current,
        [],
        base_prompt="system prompt",
        inference=fake,
        enable_thinking=False,
    )

    assert [message["content"] for message in window.prompt] == [
        "system prompt",
        "recent user words",
        "recent assistant words",
        "current request now",
    ]
    assert window.included_messages == 3
    assert window.omitted_messages == 2
    assert window.first_included_order == 2
    assert window.prompt_tokens == 11
    assert window.slot_tokens == 18
    assert window.reserved_output_tokens == 4
    assert len(fake.rendered_histories) >= 2


async def test_selector_rejects_when_mandatory_minimum_does_not_fit(monkeypatch):
    monkeypatch.setattr("services.context_window.get_output_reserve", lambda: 4)
    current = _message("user", 0, "current request now")

    with pytest.raises(ContextLimitExceeded) as exc_info:
        await select_context_window(
            [],
            current,
            [],
            base_prompt="system prompt",
            inference=ExactBudgetFake(slot_tokens=8),
            enable_thinking=False,
        )

    assert exc_info.value.prompt_tokens == 5
    assert exc_info.value.slot_tokens == 8
    assert exc_info.value.reserve == 4
