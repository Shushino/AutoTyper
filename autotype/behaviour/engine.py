from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..actions import Action, KeyPress, Pause, TypeText
from .profiles import BehaviourProfile, get_profile
from .timing import character_pause_seconds, estimate_total_duration
from .typos import TypoSummary, _apply_typo_behaviour_with_summary


@dataclass(frozen=True, slots=True)
class DryRunSummary:
    input_kind: str
    character_count: int
    action_count: int
    typo_injections: int
    typo_corrections: int
    formatting_toggles: int
    estimated_duration: float


@dataclass(frozen=True, slots=True)
class BehaviourPreview:
    profile: str
    wpm: float
    typo_rate: float
    seed: int | None
    actions: tuple[Action, ...]
    summary: DryRunSummary
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
    typo_actions, _ = _apply_typo_behaviour_with_summary(actions, selected_profile, typo_rate, rng)
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
    input_kind: str = "plain text",
) -> BehaviourPreview:
    source_actions = tuple(actions)
    display_input_kind = _format_input_kind(input_kind)
    selected_profile = get_profile(profile)
    rng = random.Random(seed)
    typo_actions, typo_summary = _apply_typo_behaviour_with_summary(source_actions, selected_profile, typo_rate, rng)
    transformed: list[Action] = []
    for action in typo_actions:
        if isinstance(action, TypeText):
            transformed.extend(_expand_text(action.text, selected_profile, wpm, rng))
        else:
            transformed.append(action)
    transformed_tuple = tuple(transformed)
    pauses = [action.seconds for action in transformed if isinstance(action, Pause)]
    character_count = sum(len(action.text) for action in source_actions if isinstance(action, TypeText))
    formatting_toggles = sum(
        1
        for action in transformed_tuple
        if isinstance(action, KeyPress) and action.key in {"CTRL+B", "CTRL+I", "CTRL+U"}
    )
    summary = DryRunSummary(
        input_kind=display_input_kind,
        character_count=character_count,
        action_count=len(transformed_tuple),
        typo_injections=typo_summary.injections,
        typo_corrections=typo_summary.corrections,
        formatting_toggles=formatting_toggles,
        estimated_duration=estimate_total_duration(pauses),
    )
    return BehaviourPreview(
        profile=get_profile(profile).name,
        wpm=wpm,
        typo_rate=typo_rate,
        seed=seed,
        actions=transformed_tuple,
        summary=summary,
        estimated_duration=summary.estimated_duration,
    )


def render_dry_run(
    actions: Sequence[Action],
    profile: str = "natural",
    wpm: float = 45.0,
    typo_rate: float = 0.0,
    seed: int | None = None,
    input_kind: str = "plain text",
    max_action_lines: int = 120,
) -> str:
    preview = build_preview(actions, profile=profile, wpm=wpm, typo_rate=typo_rate, seed=seed, input_kind=input_kind)
    lines = [
        "[DRY RUN]",
        "Summary:",
        f"  Input kind: {preview.summary.input_kind}",
        f"  Characters: {preview.summary.character_count}",
        f"  Actions: {preview.summary.action_count}",
        f"  Typos injected: {preview.summary.typo_injections}",
        f"  Typos corrected: {preview.summary.typo_corrections}",
        f"  Formatting toggles: {preview.summary.formatting_toggles}",
        f"  Estimated duration: {preview.summary.estimated_duration:.3f}s",
        "",
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


def _format_input_kind(input_kind: str) -> str:
    normalized = input_kind.strip().lower()
    if normalized in {"", "text", "plain text"}:
        return "plain text"
    return normalized.upper()
