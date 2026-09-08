from types import SimpleNamespace

from scripts.downloader import _select_model_items


MODELS = [
    {"name": "prod-small", "role": "small"},
    {"name": "embed", "role": "embedding"},
    {"name": "prod-big", "role": "big"},
    {"name": "test-small", "role": "test"},
]


def _settings(**overrides):
    values = {
        "TEST_MODE": False,
        "SMALL_MODEL": None,
        "EMBEDDING_MODEL": None,
        "BIG_MODEL": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _names(items):
    return {item["name"] for item in items}


def test_normal_mode_selects_production_tiers():
    selected = _select_model_items(MODELS, _settings())

    assert _names(selected) == {"prod-small", "embed", "prod-big"}


def test_test_mode_swaps_small_and_skips_default_big():
    selected = _select_model_items(MODELS, _settings(TEST_MODE=True))

    assert _names(selected) == {"test-small", "embed"}


def test_explicit_small_override_replaces_test_default():
    selected = _select_model_items(
        MODELS,
        _settings(TEST_MODE=True, SMALL_MODEL="prod-small"),
    )

    assert _names(selected) == {"prod-small", "embed"}


def test_explicit_big_override_is_kept_in_test_mode():
    selected = _select_model_items(
        MODELS,
        _settings(TEST_MODE=True, BIG_MODEL="prod-big"),
    )

    assert _names(selected) == {"test-small", "embed", "prod-big"}
