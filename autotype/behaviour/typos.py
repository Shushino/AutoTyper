from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable

from ..actions import Action, KeyPress, TypeText
from .profiles import BehaviourProfile


QWERTY_ADJACENCY: dict[str, tuple[str, ...]] = {
    "a": ("q", "w", "s", "z"),
    "b": ("v", "g", "h", "n"),
    "c": ("x", "d", "f", "v"),
    "d": ("s", "e", "r", "f", "c", "x"),
    "e": ("w", "s", "d", "r"),
    "f": ("d", "r", "t", "g", "v", "c"),
    "g": ("f", "t", "y", "h", "b", "v"),
    "h": ("g", "y", "u", "j", "n", "b"),
    "i": ("u", "j", "k", "o"),
    "j": ("h", "u", "i", "k", "m", "n"),
    "k": ("j", "i", "o", "l", "m"),
    "l": ("k", "o", "p"),
    "m": ("n", "j", "k"),
    "n": ("b", "h", "j", "m"),
    "o": ("i", "k", "l", "p"),
    "p": ("o", "l"),
    "q": ("w", "a"),
    "r": ("e", "d", "f", "t"),
    "s": ("a", "w", "e", "d", "x", "z"),
    "t": ("r", "f", "g", "y"),
    "u": ("y", "h", "j", "i"),
    "v": ("c", "f", "g", "b"),
    "w": ("q", "a", "s", "e"),
    "x": ("z", "s", "d", "c"),
    "y": ("t", "g", "h", "u"),
    "z": ("a", "s", "x"),
}


@dataclass(frozen=True, slots=True)
class TypoMutation:
    kind: str
    word: str
    mutated_word: str
    index: int


def apply_typo_behaviour(
    actions: Iterable[Action],
    profile: BehaviourProfile,
    typo_rate: float,
    rng: random.Random,
) -> list[Action]:
    if typo_rate <= 0:
        return list(actions)

    expanded: list[Action] = []
    for action in actions:
        if isinstance(action, TypeText):
            expanded.extend(_expand_type_text(action.text, profile, typo_rate, rng))
        else:
            expanded.append(action)
    return expanded


def _expand_type_text(
    text: str,
    profile: BehaviourProfile,
    typo_rate: float,
    rng: random.Random,
) -> list[Action]:
    transformed: list[Action] = []
    for chunk, is_word in _split_text_chunks(text):
        if not is_word:
            transformed.append(TypeText(chunk))
            continue
        transformed.extend(_expand_word(chunk, profile, typo_rate, rng))
    return transformed


def _expand_word(
    word: str,
    profile: BehaviourProfile,
    typo_rate: float,
    rng: random.Random,
) -> list[Action]:
    effective_rate = min(0.10, max(0.0, typo_rate) * profile.typo_rate_multiplier)
    if len(word) < 2 or rng.random() >= effective_rate:
        return [TypeText(word)]

    mutation = _choose_typo_mutation(word, rng)
    if mutation is None:
        return [TypeText(word)]

    if rng.random() < profile.immediate_correction_probability:
        return _build_immediate_correction(mutation)
    return _build_delayed_correction(mutation)


def _choose_typo_mutation(word: str, rng: random.Random) -> TypoMutation | None:
    builders = []
    if _has_adjacent_typo_candidate(word):
        builders.append(_build_adjacent_typo)
    if len(word) >= 1:
        builders.append(_build_double_char_typo)
    if len(word) >= 2:
        builders.append(_build_transposition_typo)
    if not builders:
        return None
    return rng.choice(builders)(word, rng)


def _build_immediate_correction(mutation: TypoMutation) -> list[Action]:
    word = mutation.word
    if mutation.kind == "adjacent":
        prefix = word[: mutation.index]
        intended = word[mutation.index]
        suffix = word[mutation.index + 1 :]
        wrong = mutation.mutated_word[mutation.index]
        actions: list[Action] = []
        if prefix:
            actions.append(TypeText(prefix))
        actions.append(TypeText(wrong))
        actions.append(KeyPress("BACKSPACE"))
        actions.append(TypeText(intended + suffix))
        return actions

    if mutation.kind == "double":
        prefix = word[: mutation.index + 1]
        suffix = word[mutation.index + 1 :]
        extra = mutation.mutated_word[mutation.index + 1]
        actions = []
        if prefix:
            actions.append(TypeText(prefix))
        actions.append(TypeText(extra))
        actions.append(KeyPress("BACKSPACE"))
        if suffix:
            actions.append(TypeText(suffix))
        return actions

    if mutation.kind == "transpose":
        prefix = word[: mutation.index]
        corrected_pair = word[mutation.index : mutation.index + 2]
        suffix = word[mutation.index + 2 :]
        swapped_pair = mutation.mutated_word[mutation.index : mutation.index + 2]
        actions = []
        if prefix:
            actions.append(TypeText(prefix))
        actions.append(TypeText(swapped_pair))
        actions.append(KeyPress("BACKSPACE"))
        actions.append(KeyPress("BACKSPACE"))
        actions.append(TypeText(corrected_pair + suffix))
        return actions

    raise ValueError(f"Unknown typo kind: {mutation.kind!r}")


def _build_delayed_correction(mutation: TypoMutation) -> list[Action]:
    return [
        TypeText(mutation.mutated_word),
        KeyPress("CTRL+SHIFT+LEFT"),
        KeyPress("BACKSPACE"),
        TypeText(mutation.word),
        KeyPress("END"),
    ]


def _split_text_chunks(text: str) -> list[tuple[str, bool]]:
    if not text:
        return []

    chunks: list[tuple[str, bool]] = []
    current = [text[0]]
    current_is_word = text[0].isalpha()

    for character in text[1:]:
        is_word = character.isalpha()
        if is_word == current_is_word:
            current.append(character)
            continue
        chunks.append(("".join(current), current_is_word))
        current = [character]
        current_is_word = is_word

    chunks.append(("".join(current), current_is_word))
    return chunks


def _has_adjacent_typo_candidate(word: str) -> bool:
    return any(character.lower() in QWERTY_ADJACENCY for character in word)


def _build_adjacent_typo(word: str, rng: random.Random) -> TypoMutation:
    candidates = [index for index, character in enumerate(word) if character.lower() in QWERTY_ADJACENCY]
    if not candidates:
        raise ValueError("word does not have an adjacent-key typo candidate")

    index = rng.choice(candidates)
    original = word[index]
    replacement_pool = QWERTY_ADJACENCY[original.lower()]
    replacement = rng.choice(replacement_pool)
    if original.isupper():
        replacement = replacement.upper()

    mutated_word = word[:index] + replacement + word[index + 1 :]
    return TypoMutation(kind="adjacent", word=word, mutated_word=mutated_word, index=index)


def _build_double_char_typo(word: str, rng: random.Random) -> TypoMutation:
    index = rng.randrange(len(word))
    mutated_word = word[: index + 1] + word[index] + word[index + 1 :]
    return TypoMutation(kind="double", word=word, mutated_word=mutated_word, index=index)


def _build_transposition_typo(word: str, rng: random.Random) -> TypoMutation:
    index = rng.randrange(len(word) - 1)
    mutated_word = word[:index] + word[index + 1] + word[index] + word[index + 2 :]
    return TypoMutation(kind="transpose", word=word, mutated_word=mutated_word, index=index)


build_adjacent_typo = _build_adjacent_typo
build_double_char_typo = _build_double_char_typo
build_transposition_typo = _build_transposition_typo
build_immediate_correction = _build_immediate_correction
build_delayed_correction = _build_delayed_correction


__all__ = [
    "QWERTY_ADJACENCY",
    "TypoMutation",
    "apply_typo_behaviour",
    "build_adjacent_typo",
    "build_delayed_correction",
    "build_double_char_typo",
    "build_immediate_correction",
    "build_transposition_typo",
]
