from __future__ import annotations

import math
import random

from .profiles import BehaviourProfile


SENTENCE_ENDERS = {".", "?", "!"}


def baseline_seconds_per_character(wpm: float, profile: BehaviourProfile) -> float:
    if wpm <= 0:
        raise ValueError("wpm must be positive")
    return (60.0 / (wpm * 5.0)) * profile.speed_multiplier


def sample_character_delay(rng: random.Random, wpm: float, profile: BehaviourProfile) -> float:
    baseline = baseline_seconds_per_character(wpm, profile)
    stddev = baseline * profile.jitter_stddev
    if stddev > 0:
        delay = rng.gauss(baseline, stddev)
    else:
        delay = baseline
    return clamp(delay, profile.min_character_delay, profile.max_character_delay)


def sample_word_boundary_delay(rng: random.Random, profile: BehaviourProfile) -> float:
    if profile.word_boundary_variation <= 0:
        return 0.0
    spread = max(profile.word_boundary_variation * 0.35, 0.005)
    return clamp(rng.gauss(profile.word_boundary_variation, spread), 0.0, profile.word_boundary_variation * 3.0)


def punctuation_delay(character: str, profile: BehaviourProfile) -> float:
    if character == ",":
        return profile.comma_pause
    if character == ";":
        return profile.semicolon_pause
    if character == ":":
        return profile.colon_pause
    if character in SENTENCE_ENDERS:
        return profile.sentence_pause
    if character == "\n":
        return profile.newline_pause
    return 0.0


def maybe_sample_thinking_pause(
    rng: random.Random,
    profile: BehaviourProfile,
    character: str,
    next_character: str | None,
) -> float:
    if character not in SENTENCE_ENDERS and character != "\n":
        return 0.0
    if next_character is not None and next_character.isspace():
        return 0.0
    if rng.random() >= profile.thinking_pause_probability:
        return 0.0
    if profile.thinking_pause_max == 0:
        return 0.0
    return rng.uniform(profile.thinking_pause_min, profile.thinking_pause_max)


def character_pause_seconds(
    rng: random.Random,
    wpm: float,
    profile: BehaviourProfile,
    character: str,
    next_character: str | None,
) -> float:
    total = sample_character_delay(rng, wpm, profile)
    total += punctuation_delay(character, profile)
    if character == " ":
        total += sample_word_boundary_delay(rng, profile)
    total += maybe_sample_thinking_pause(rng, profile, character, next_character)
    return max(total, 0.001)


def estimate_total_duration(pauses: list[float]) -> float:
    return sum(pauses)


def clamp(value: float, minimum: float, maximum: float) -> float:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value
