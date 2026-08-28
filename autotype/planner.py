from __future__ import annotations

from .actions import Action, TypeText
from .input import DocumentContent


def build_actions_from_text(text: str) -> list[Action]:
    """Convert raw source text into the planner's clean action stream."""
    if not text:
        return []
    return [TypeText(text=text)]


def build_actions_from_content(content: DocumentContent) -> list[Action]:
    """Convert normalized document content into source-intent actions."""
    if content.source_kind == "docx":
        return content.to_actions()
    return build_actions_from_text(content.to_text())
