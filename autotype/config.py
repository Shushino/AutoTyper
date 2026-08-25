from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TypingConfig:
    words_per_minute: float = 40.0
    countdown_seconds: float = 5.0
    poll_interval_seconds: float = 0.05

    def __post_init__(self) -> None:
        if self.words_per_minute <= 0:
            raise ValueError("words_per_minute must be positive")
        if self.countdown_seconds < 0:
            raise ValueError("countdown_seconds must be non-negative")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")

    @property
    def seconds_per_character(self) -> float:
        return 60.0 / (self.words_per_minute * 5.0)


@dataclass(frozen=True, slots=True)
class HotkeyConfig:
    pause_key: str = "F8"
    stop_key: str = "F12"

    def __post_init__(self) -> None:
        if not self.pause_key:
            raise ValueError("pause_key must not be empty")
        if not self.stop_key:
            raise ValueError("stop_key must not be empty")
