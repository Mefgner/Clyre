from types import SimpleNamespace
from typing import cast

from scripts.downloader import _select_model_items
from shared.pyutils.env import Settings

MODELS = [
    {"name": "prod-chat", "role": "chat"},
    {"name": "embed", "role": "embedding"},
    {"name": "test-chat", "role": "test"},
]


def _settings(**overrides) -> Settings:
    values = {
        "TEST_MODE": False,
        "CHAT_MODEL": None,
        "EMBEDDING_MODEL": None,
    }
    values.update(overrides)
    return cast(Settings, SimpleNamespace(**values))


def _names(items):
    return {item["name"] for item in items}


def test_normal_mode_selects_chat_and_embedding():
    selected = _select_model_items(MODELS, _settings())

    assert _names(selected) == {"prod-chat", "embed"}


def test_test_mode_substitutes_test_chat_model():
    selected = _select_model_items(MODELS, _settings(TEST_MODE=True))

    assert _names(selected) == {"test-chat", "embed"}


def test_explicit_chat_override_replaces_test_default():
    selected = _select_model_items(MODELS, _settings(TEST_MODE=True, CHAT_MODEL="prod-chat"))

    assert _names(selected) == {"prod-chat", "embed"}
