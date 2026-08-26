from __future__ import annotations

from .actions import Action, TypeText


def build_actions_from_text(text: str) -> list[Action]:
    """Convert raw source text into the planner's clean action stream."""
    if not text:
        return []
    return [TypeText(text=text)]
