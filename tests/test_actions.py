import pytest

from autotype.actions import KeyPress, Pause, TypeText
from autotype.planner import build_actions_from_text, render_dry_run
from autotype.config import TypingConfig


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


def test_dry_run_renders_timing_information() -> None:
    summary = render_dry_run([TypeText("hello"), Pause(0.25), KeyPress("ENTER")], TypingConfig(words_per_minute=60))
    rendered = summary.render()
    assert rendered.startswith("[DRY RUN]")
    assert 'TypeText("hello")' in rendered
    assert "Pause(0.250s)" in rendered
    assert 'KeyPress("ENTER")' in rendered
    assert "Estimated total delay:" in rendered
