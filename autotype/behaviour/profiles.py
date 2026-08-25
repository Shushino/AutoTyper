from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BehaviourProfile:
    name: str
    speed_multiplier: float
    jitter_stddev: float
    min_character_delay: float
    max_character_delay: float
    comma_pause: float
    semicolon_pause: float
    colon_pause: float
    sentence_pause: float
    newline_pause: float
    word_boundary_variation: float
    thinking_pause_probability: float
    thinking_pause_min: float
    thinking_pause_max: float

    def __post_init__(self) -> None:
        if self.speed_multiplier <= 0:
            raise ValueError("speed_multiplier must be positive")
        if self.jitter_stddev < 0:
            raise ValueError("jitter_stddev must be non-negative")
        if self.min_character_delay <= 0:
            raise ValueError("min_character_delay must be positive")
        if self.max_character_delay < self.min_character_delay:
            raise ValueError("max_character_delay must be at least min_character_delay")
        if self.word_boundary_variation < 0:
            raise ValueError("word_boundary_variation must be non-negative")
        if not 0 <= self.thinking_pause_probability <= 1:
            raise ValueError("thinking_pause_probability must be between 0 and 1")
        if self.thinking_pause_min < 0:
            raise ValueError("thinking_pause_min must be non-negative")
        if self.thinking_pause_max < self.thinking_pause_min:
            raise ValueError("thinking_pause_max must be at least thinking_pause_min")


PROFILES: dict[str, BehaviourProfile] = {
    "precise": BehaviourProfile(
        name="precise",
        speed_multiplier=1.0,
        jitter_stddev=0.05,
        min_character_delay=0.03,
        max_character_delay=0.15,
        comma_pause=0.03,
        semicolon_pause=0.05,
        colon_pause=0.05,
        sentence_pause=0.08,
        newline_pause=0.12,
        word_boundary_variation=0.01,
        thinking_pause_probability=0.01,
        thinking_pause_min=0.10,
        thinking_pause_max=0.20,
    ),
    "natural": BehaviourProfile(
        name="natural",
        speed_multiplier=1.0,
        jitter_stddev=0.14,
        min_character_delay=0.025,
        max_character_delay=0.24,
        comma_pause=0.05,
        semicolon_pause=0.08,
        colon_pause=0.08,
        sentence_pause=0.13,
        newline_pause=0.18,
        word_boundary_variation=0.03,
        thinking_pause_probability=0.04,
        thinking_pause_min=0.18,
        thinking_pause_max=0.50,
    ),
    "careful": BehaviourProfile(
        name="careful",
        speed_multiplier=1.12,
        jitter_stddev=0.22,
        min_character_delay=0.03,
        max_character_delay=0.32,
        comma_pause=0.07,
        semicolon_pause=0.11,
        colon_pause=0.11,
        sentence_pause=0.18,
        newline_pause=0.25,
        word_boundary_variation=0.05,
        thinking_pause_probability=0.08,
        thinking_pause_min=0.28,
        thinking_pause_max=0.85,
    ),
    "fast": BehaviourProfile(
        name="fast",
        speed_multiplier=0.82,
        jitter_stddev=0.10,
        min_character_delay=0.02,
        max_character_delay=0.18,
        comma_pause=0.03,
        semicolon_pause=0.05,
        colon_pause=0.05,
        sentence_pause=0.07,
        newline_pause=0.11,
        word_boundary_variation=0.015,
        thinking_pause_probability=0.02,
        thinking_pause_min=0.12,
        thinking_pause_max=0.28,
    ),
}


def get_profile(name: str) -> BehaviourProfile:
    normalized = name.strip().lower()
    try:
        return PROFILES[normalized]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Unknown behaviour profile: {name!r}") from exc
