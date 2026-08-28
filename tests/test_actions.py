import pytest

from autotype.actions import KeyPress, Pause, TypeText
from autotype.planner import build_actions_from_text


def test_type_text_rejects_empty_text() -> None:
    with pytest.raises(ValueError):
        TypeText("")


def test_pause_rejects_negative_duration() -> None:
    with pytest.raises(ValueError):
        Pause(-0.1)


def test_key_press_rejects_empty_key() -> None:
    with pytest.raises(ValueError):
        KeyPress("")


def test_build_actions_from_text_returns_single_type_text_action() -> None:
    actions = build_actions_from_text("hello")
    assert actions == [TypeText("hello")]
