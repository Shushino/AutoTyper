from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class TypeText:
    text: str

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("TypeText.text must not be empty")


@dataclass(frozen=True, slots=True)
class Pause:
    seconds: float

    def __post_init__(self) -> None:
        if self.seconds < 0:
            raise ValueError("Pause.seconds must be non-negative")


@dataclass(frozen=True, slots=True)
class KeyPress:
    key: str

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("KeyPress.key must not be empty")


Action: TypeAlias = TypeText | Pause | KeyPress
