from __future__ import annotations

import random

from autotype.actions import KeyPress, Pause, TypeText
from autotype.behaviour import apply_human_behaviour
from autotype.behaviour.profiles import get_profile
from autotype.behaviour.typos import (
    QWERTY_ADJACENCY,
    apply_typo_behaviour,
    build_adjacent_typo,
    build_delayed_correction,
    build_double_char_typo,
    build_immediate_correction,
    build_transposition_typo,
)


class TextBufferSimulator:
    def __init__(self) -> None:
        self._buffer: list[str] = []
        self._cursor = 0
        self._selection: tuple[int, int] | None = None

    @property
    def text(self) -> str:
        return "".join(self._buffer)

    def apply(self, actions) -> None:
        for action in actions:
            if isinstance(action, TypeText):
                self._insert(action.text)
            elif isinstance(action, Pause):
                continue
            elif isinstance(action, KeyPress):
                self._press(action.key)
            else:  # pragma: no cover - defensive guard
                raise TypeError(f"Unsupported action: {type(action)!r}")

    def _insert(self, text: str) -> None:
        self._clear_selection_if_needed()
        for character in text:
            self._buffer.insert(self._cursor, character)
            self._cursor += 1

    def _press(self, key: str) -> None:
        normalized = key.upper()
        if normalized == "BACKSPACE":
            self._backspace()
        elif normalized == "LEFT":
            self._move_left()
        elif normalized == "RIGHT":
            self._move_right()
        elif normalized == "END":
            self._cursor = len(self._buffer)
            self._selection = None
        elif normalized == "CTRL+LEFT":
            self._ctrl_left()
        elif normalized == "CTRL+RIGHT":
            self._ctrl_right()
        elif normalized == "SHIFT+LEFT":
            self._shift_left()
        elif normalized == "CTRL+SHIFT+LEFT":
            self._ctrl_shift_left()
        elif normalized in {"CTRL+B", "CTRL+I", "CTRL+U"}:
            return
        else:  # pragma: no cover - defensive guard
            raise ValueError(f"Unsupported simulated key: {key!r}")

    def _backspace(self) -> None:
        if self._selection is not None:
            start, end = self._selection
            del self._buffer[start:end]
            self._cursor = start
            self._selection = None
            return
        if self._cursor == 0:
            return
        del self._buffer[self._cursor - 1]
        self._cursor -= 1

    def _move_left(self) -> None:
        if self._selection is not None:
            self._cursor = self._selection[0]
            self._selection = None
            return
        if self._cursor > 0:
            self._cursor -= 1

    def _move_right(self) -> None:
        if self._selection is not None:
            self._cursor = self._selection[1]
            self._selection = None
            return
        if self._cursor < len(self._buffer):
            self._cursor += 1

    def _ctrl_left(self) -> None:
        if self._selection is not None:
            self._cursor = self._selection[0]
            self._selection = None
        while self._cursor > 0 and self._buffer[self._cursor - 1].isspace():
            self._cursor -= 1
        while self._cursor > 0 and not self._buffer[self._cursor - 1].isspace():
            self._cursor -= 1

    def _ctrl_right(self) -> None:
        if self._selection is not None:
            self._cursor = self._selection[1]
            self._selection = None
        while self._cursor < len(self._buffer) and not self._buffer[self._cursor].isspace():
            self._cursor += 1
        while self._cursor < len(self._buffer) and self._buffer[self._cursor].isspace():
            self._cursor += 1

    def _shift_left(self) -> None:
        if self._cursor == 0:
            return
        if self._selection is None:
            self._selection = (self._cursor - 1, self._cursor)
            self._cursor -= 1
            return
        start, end = self._selection
        if self._cursor == start and start > 0:
            self._selection = (start - 1, end)
            self._cursor -= 1

    def _ctrl_shift_left(self) -> None:
        if self._cursor == 0:
            return
        start = self._cursor
        while start > 0 and self._buffer[start - 1].isspace():
            start -= 1
        while start > 0 and not self._buffer[start - 1].isspace():
            start -= 1
        self._selection = (start, self._cursor)
        self._cursor = start

    def _clear_selection_if_needed(self) -> None:
        if self._selection is None:
            return
        start, end = self._selection
        del self._buffer[start:end]
        self._cursor = start
        self._selection = None


def _count_keypress(actions, key: str) -> int:
    return sum(1 for action in actions if isinstance(action, KeyPress) and action.key == key)


def test_zero_typo_rate_leaves_source_actions_untouched() -> None:
    source = [TypeText("hello"), Pause(0.25), KeyPress("ENTER")]
    transformed = apply_typo_behaviour(source, get_profile("natural"), 0.0, random.Random(1))

    assert transformed == source


def test_typo_generation_is_seed_deterministic() -> None:
    source = [TypeText("the quick brown fox jumps over the lazy dog " * 10)]

    first = apply_human_behaviour(source, profile="natural", wpm=45, typo_rate=0.10, seed=1234)
    second = apply_human_behaviour(source, profile="natural", wpm=45, typo_rate=0.10, seed=1234)
    third = apply_human_behaviour(source, profile="natural", wpm=45, typo_rate=0.10, seed=1235)

    assert first == second
    assert first != third


def test_qwerty_adjacency_map_is_valid_for_adjacent_typos() -> None:
    mutation = build_adjacent_typo("hello", random.Random(5))

    assert len(mutation.mutated_word) == len(mutation.word)
    differences = [
        index
        for index, (original, mutated) in enumerate(zip(mutation.word, mutation.mutated_word, strict=True))
        if original != mutated
    ]
    assert len(differences) == 1
    index = differences[0]
    assert mutation.mutated_word[index].lower() in QWERTY_ADJACENCY[mutation.word[index].lower()]


def test_double_character_typo_duplicates_one_letter() -> None:
    mutation = build_double_char_typo("hello", random.Random(7))

    assert len(mutation.mutated_word) == len(mutation.word) + 1
    assert mutation.word == mutation.mutated_word[: mutation.index + 1] + mutation.mutated_word[mutation.index + 2 :]


def test_transposition_typo_swaps_adjacent_in_word_letters() -> None:
    mutation = build_transposition_typo("friend", random.Random(11))

    assert len(mutation.mutated_word) == len(mutation.word)
    assert mutation.mutated_word[: mutation.index] == mutation.word[: mutation.index]
    assert mutation.mutated_word[mutation.index] == mutation.word[mutation.index + 1]
    assert mutation.mutated_word[mutation.index + 1] == mutation.word[mutation.index]
    assert mutation.mutated_word[mutation.index + 2 :] == mutation.word[mutation.index + 2 :]


def test_immediate_correction_uses_backspace() -> None:
    mutation = build_adjacent_typo("hello", random.Random(13))
    actions = build_immediate_correction(mutation)

    assert any(isinstance(action, KeyPress) and action.key == "BACKSPACE" for action in actions)


def test_delayed_correction_uses_navigation_actions() -> None:
    mutation = build_adjacent_typo("hello", random.Random(17))
    actions = build_delayed_correction(mutation)

    assert any(isinstance(action, KeyPress) and action.key == "CTRL+SHIFT+LEFT" for action in actions)
    assert any(isinstance(action, KeyPress) and action.key == "END" for action in actions)


def test_final_text_integrity_is_preserved_after_typos_and_corrections() -> None:
    source_text = "The quick brown fox jumps over the lazy dog. " * 6
    actions = apply_human_behaviour(
        [TypeText(source_text)],
        profile="careful",
        wpm=45,
        typo_rate=0.10,
        seed=2024,
    )

    simulator = TextBufferSimulator()
    simulator.apply(actions)

    assert simulator.text == source_text
    assert _count_keypress(actions, "BACKSPACE") > 0
    assert _count_keypress(actions, "CTRL+SHIFT+LEFT") > 0


def test_profile_changes_typo_and_correction_mix() -> None:
    source_text = ("alpha beta gamma delta epsilon zeta eta theta iota kappa " * 20).strip()
    source = [TypeText(source_text)]

    precise = apply_human_behaviour(source, profile="precise", wpm=45, typo_rate=0.10, seed=99)
    careful = apply_human_behaviour(source, profile="careful", wpm=45, typo_rate=0.10, seed=99)

    assert _count_keypress(careful, "CTRL+SHIFT+LEFT") >= _count_keypress(precise, "CTRL+SHIFT+LEFT")
