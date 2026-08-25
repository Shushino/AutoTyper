from __future__ import annotations

import json
from dataclasses import dataclass

from .actions import Action, KeyPress, Pause, TypeText
from .config import TypingConfig


def build_actions_from_text(text: str) -> list[Action]:
    if not text:
        return []
    return [TypeText(text=text)]


@dataclass(frozen=True, slots=True)
class DryRunSummary:
    lines: tuple[str, ...]

    def render(self) -> str:
        return "\n".join(self.lines)


def render_dry_run(actions: list[Action], config: TypingConfig) -> DryRunSummary:
    lines: list[str] = ["[DRY RUN]"]
    estimated_seconds = 0.0

    for action in actions:
        if isinstance(action, TypeText):
            per_char = config.seconds_per_character
            lines.append(f"TypeText({json.dumps(action.text)})")
            lines.append(f"  characters: {len(action.text)}")
            lines.append(f"  seconds_per_character: {per_char:.3f}")
            estimated_seconds += len(action.text) * per_char
        elif isinstance(action, Pause):
            lines.append(f"Pause({action.seconds:.3f}s)")
            estimated_seconds += action.seconds
        elif isinstance(action, KeyPress):
            lines.append(f"KeyPress({json.dumps(action.key)})")
        else:  # pragma: no cover - defensive guard
            raise TypeError(f"Unsupported action: {type(action)!r}")

    lines.append(f"Estimated total delay: {estimated_seconds:.3f}s")
    return DryRunSummary(lines=tuple(lines))
