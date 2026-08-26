from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..actions import Action, KeyPress, Pause, TypeText
from .profiles import BehaviourProfile, get_profile
from .timing import character_pause_seconds, estimate_total_duration
from .typos import apply_typo_behaviour


@dataclass(frozen=True, slots=True)
class BehaviourPreview:
    profile: str
    wpm: float
    typo_rate: float
    seed: int | None
    actions: tuple[Action, ...]
    estimated_duration: float


def apply_human_behaviour(
    actions: Iterable[Action],
    profile: str = "natural",
    wpm: float = 45.0,
    typo_rate: float = 0.0,
    seed: int | None = None,
) -> list[Action]:
    selected_profile = get_profile(profile)
    rng = random.Random(seed)
    typo_actions = apply_typo_behaviour(actions, selected_profile, typo_rate, rng)
    expanded: list[Action] = []
    for action in typo_actions:
        if isinstance(action, TypeText):
            expanded.extend(_expand_text(action.text, selected_profile, wpm, rng))
        else:
            expanded.append(action)
    return expanded


def _expand_text(
    text: str,
    profile: BehaviourProfile,
    wpm: float,
    rng: random.Random,
) -> list[Action]:
    expanded: list[Action] = []
    for index, character in enumerate(text):
        next_character = text[index + 1] if index + 1 < len(text) else None
        expanded.append(TypeText(character))
        expanded.append(Pause(character_pause_seconds(rng, wpm, profile, character, next_character)))
    return expanded


def build_preview(
    actions: Iterable[Action],
    profile: str = "natural",
    wpm: float = 45.0,
    typo_rate: float = 0.0,
    seed: int | None = None,
) -> BehaviourPreview:
    transformed = tuple(apply_human_behaviour(actions, profile=profile, wpm=wpm, typo_rate=typo_rate, seed=seed))
    pauses = [action.seconds for action in transformed if isinstance(action, Pause)]
    return BehaviourPreview(
        profile=get_profile(profile).name,
        wpm=wpm,
        typo_rate=typo_rate,
        seed=seed,
        actions=transformed,
        estimated_duration=estimate_total_duration(pauses),
    )


def render_dry_run(
    actions: Sequence[Action],
    profile: str = "natural",
    wpm: float = 45.0,
    typo_rate: float = 0.0,
    seed: int | None = None,
    max_action_lines: int = 120,
) -> str:
    preview = build_preview(actions, profile=profile, wpm=wpm, typo_rate=typo_rate, seed=seed)
    lines = [
        "[DRY RUN]",
        f"Profile: {preview.profile}",
        f"Speed: {preview.wpm:g} WPM",
        f"Typo rate: {preview.typo_rate:.3f}",
    ]
    if preview.seed is not None:
        lines.append(f"Seed: {preview.seed}")
    lines.append("")

    visible_actions = preview.actions[:max_action_lines]
    for action in visible_actions:
        if isinstance(action, TypeText):
            lines.append(f'TypeText({action.text!r})')
        elif isinstance(action, Pause):
            lines.append(f"Pause({action.seconds:.3f}s)")
        elif isinstance(action, KeyPress):
            lines.append(f"KeyPress({action.key!r})")
        else:  # pragma: no cover - defensive guard
            lines.append(f"{type(action).__name__}")

    if len(preview.actions) > max_action_lines:
        remaining = len(preview.actions) - max_action_lines
        lines.append(f"... truncated {remaining} additional actions ...")

    lines.append("")
    lines.append(f"Estimated total duration: {preview.estimated_duration:.3f}s")
    return "\n".join(lines)
