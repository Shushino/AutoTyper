"""Source-intent action types for AutoType.

These actions describe what the user wants typed, not how timing or execution
should behave.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class TypeText:
    """Emit this text exactly as written."""

    text: str

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("TypeText.text must not be empty")


@dataclass(frozen=True, slots=True)
class Pause:
    """Wait for the given duration in seconds."""

    seconds: float

    def __post_init__(self) -> None:
        if self.seconds < 0:
            raise ValueError("Pause.seconds must be non-negative")


@dataclass(frozen=True, slots=True)
class KeyPress:
    """Emit a logical key press such as ENTER or F12."""

    key: str

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("KeyPress.key must not be empty")


Action: TypeAlias = TypeText | Pause | KeyPress
