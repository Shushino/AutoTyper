from __future__ import annotations

import statistics

from autotype.actions import KeyPress, Pause, TypeText
from autotype.behaviour import apply_human_behaviour
from autotype.behaviour.engine import build_preview, render_dry_run


def _extract_pause_durations(actions):
    return [action.seconds for action in actions if isinstance(action, Pause)]


def _extract_typed_text(actions):
    return "".join(action.text for action in actions if isinstance(action, TypeText))


def _paired_timing(actions):
    pairs = []
    for index in range(0, len(actions), 2):
        text_action = actions[index]
        pause_action = actions[index + 1]
        assert isinstance(text_action, TypeText)
        assert isinstance(pause_action, Pause)
        pairs.append((text_action.text, pause_action.seconds))
    return pairs


def test_same_seed_is_exactly_deterministic() -> None:
    source = [TypeText("Hello! This is a test."), Pause(0.25), KeyPress("ENTER")]

    first = apply_human_behaviour(source, profile="natural", wpm=45, seed=1234)
    second = apply_human_behaviour(source, profile="natural", wpm=45, seed=1234)

    assert first == second
    assert source == [TypeText("Hello! This is a test."), Pause(0.25), KeyPress("ENTER")]


def test_different_seeds_change_timing_sequence() -> None:
    source = [TypeText("The quick brown fox jumps over the lazy dog." * 12)]

    first = apply_human_behaviour(source, profile="natural", wpm=45, seed=1)
    second = apply_human_behaviour(source, profile="natural", wpm=45, seed=2)

    assert first != second


def test_profiles_show_broad_speed_and_variance_ordering() -> None:
    source = [TypeText(("The quick brown fox jumps over the lazy dog. " * 40).strip())]

    precise = apply_human_behaviour(source, profile="precise", wpm=45, seed=99)
    natural = apply_human_behaviour(source, profile="natural", wpm=45, seed=99)
    careful = apply_human_behaviour(source, profile="careful", wpm=45, seed=99)
    fast = apply_human_behaviour(source, profile="fast", wpm=45, seed=99)

    precise_pauses = _extract_pause_durations(precise)
    natural_pauses = _extract_pause_durations(natural)
    careful_pauses = _extract_pause_durations(careful)
    fast_pauses = _extract_pause_durations(fast)

    assert sum(precise_pauses) < sum(natural_pauses) < sum(careful_pauses)
    assert sum(fast_pauses) < sum(natural_pauses)
    assert statistics.pstdev(precise_pauses) < statistics.pstdev(natural_pauses) < statistics.pstdev(careful_pauses)


def test_punctuation_and_newlines_add_longer_pauses() -> None:
    source = [TypeText(("a,a;a:a.a?a!\n" * 20).strip())]
    actions = apply_human_behaviour(source, profile="natural", wpm=45, seed=7)
    pairs = _paired_timing(actions)

    delays_by_character: dict[str, list[float]] = {}
    for character, delay in pairs:
        delays_by_character.setdefault(character, []).append(delay)

    letter_delay = statistics.mean(delays_by_character["a"])
    comma_delay = statistics.mean(delays_by_character[","])
    semicolon_delay = statistics.mean(delays_by_character[";"])
    colon_delay = statistics.mean(delays_by_character[":"])
    sentence_delay = statistics.mean(delays_by_character["."])
    question_delay = statistics.mean(delays_by_character["?"])
    exclamation_delay = statistics.mean(delays_by_character["!"])

    assert letter_delay < comma_delay < semicolon_delay
    assert letter_delay < colon_delay
    assert letter_delay < sentence_delay
    assert letter_delay < question_delay
    assert letter_delay < exclamation_delay

    newline_source = [TypeText(("a\n" * 20).strip())]
    newline_actions = apply_human_behaviour(newline_source, profile="natural", wpm=45, seed=7)
    newline_pairs = _paired_timing(newline_actions)
    newline_delays = [delay for character, delay in newline_pairs if character == "\n"]
    assert statistics.mean(newline_delays) > sentence_delay


def test_existing_pause_and_keypress_actions_remain_in_order() -> None:
    source = [Pause(0.5), KeyPress("ENTER"), TypeText("Hi")]
    actions = apply_human_behaviour(source, profile="precise", wpm=60, seed=42)

    assert actions[0] == Pause(0.5)
    assert actions[1] == KeyPress("ENTER")
    assert _extract_typed_text(actions[2:]) == "Hi"


def test_dry_run_preview_reports_profile_and_duration() -> None:
    source = [TypeText("Hi")]
    rendered = render_dry_run(source, profile="precise", wpm=60, typo_rate=0.0, seed=5)
    preview = build_preview(source, profile="precise", wpm=60, typo_rate=0.0, seed=5)

    assert "[DRY RUN]" in rendered
    assert "Profile: precise" in rendered
    assert "Speed: 60 WPM" in rendered
    assert "Typo rate: 0.000" in rendered
    assert "Seed: 5" in rendered
    assert "TypeText('H')" in rendered
    assert "Pause(" in rendered
    assert "Estimated total duration:" in rendered
    assert list(preview.actions) == apply_human_behaviour(source, profile="precise", wpm=60, typo_rate=0.0, seed=5)


def test_preview_uses_the_same_action_schedule_as_execution() -> None:
    source = [TypeText("The quick brown fox")]
    preview = build_preview(source, profile="careful", wpm=45, typo_rate=0.05, seed=41)
    execution_actions = apply_human_behaviour(source, profile="careful", wpm=45, typo_rate=0.05, seed=41)

    assert preview.actions == tuple(execution_actions)
