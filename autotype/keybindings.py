"""Portable parsing and validation for AutoTyper hotkey bindings."""

from __future__ import annotations

from dataclasses import dataclass


_FUNCTION_KEYS = {f"F{number}": 0x6F + number for number in range(1, 25)}
_LETTER_KEYS = {chr(ord("A") + offset): 0x41 + offset for offset in range(26)}
_DIGIT_KEYS = {str(number): 0x30 + number for number in range(10)}
_NAMED_KEYS = {
    "PAUSE": 0x13,
    "BREAK": 0x13,
    "ENTER": 0x0D,
    "TAB": 0x09,
    "SPACE": 0x20,
    "BACKSPACE": 0x08,
    "ESC": 0x1B,
    "DELETE": 0x2E,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
}

VK_MAP: dict[str, int] = {
    **_FUNCTION_KEYS,
    **_LETTER_KEYS,
    **_DIGIT_KEYS,
    **_NAMED_KEYS,
}
MODIFIER_VK = {"CTRL": 0x11, "ALT": 0x12, "SHIFT": 0x10}
MODIFIER_NAMES = frozenset(MODIFIER_VK)
MODIFIER_EVENT_VK = {
    0x11: "CTRL", 0xA2: "CTRL", 0xA3: "CTRL",
    0x12: "ALT", 0xA4: "ALT", 0xA5: "ALT",
    0x10: "SHIFT", 0xA0: "SHIFT", 0xA1: "SHIFT",
}


@dataclass(frozen=True, slots=True)
class HotkeyBinding:
    key: str
    vk: int
    modifiers: frozenset[str]


def parse_hotkey_binding(value: str) -> HotkeyBinding:
    if not isinstance(value, str):
        raise ValueError(f"Hotkey binding must be a string: {value!r}")
    parts = [part.strip().upper() for part in value.split("+")]
    if not value.strip() or any(not part for part in parts):
        raise ValueError(f"Invalid hotkey binding: {value!r}")
    base = parts[-1]
    modifiers = parts[:-1]
    if base in MODIFIER_NAMES or base not in VK_MAP:
        raise ValueError(f"Unsupported hotkey binding: {value!r}")
    if len(set(modifiers)) != len(modifiers) or any(item not in MODIFIER_NAMES for item in modifiers):
        raise ValueError(f"Invalid hotkey modifiers: {value!r}")
    return HotkeyBinding("PAUSE" if base == "BREAK" else base, VK_MAP[base], frozenset(modifiers))


def same_binding(left: HotkeyBinding, right: HotkeyBinding) -> bool:
    return left.vk == right.vk and left.modifiers == right.modifiers


def risky_binding_reason(binding: HotkeyBinding) -> str | None:
    if binding.key in _LETTER_KEYS:
        return "letter keys and letter chords can conflict with normal editing shortcuts or generated keyboard input"
    if binding.key in {"ENTER", "TAB", "SPACE", "BACKSPACE"}:
        return f"{binding.key} can be part of normal typing and may conflict with generated keyboard input"
    if binding.key in {"DELETE", "ESC", "HOME", "END", "PAGEUP", "PAGEDOWN", "LEFT", "UP", "RIGHT", "DOWN"}:
        return f"{binding.key} is a normal editing/navigation key"
    return None
