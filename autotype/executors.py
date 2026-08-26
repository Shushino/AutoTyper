from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Protocol


class ActionExecutor(Protocol):
    def type_text(self, text: str) -> None:
        ...

    def press_key(self, key: str) -> None:
        ...


@dataclass
class MockExecutor:
    calls: list[tuple[str, str]] = field(default_factory=list)

    def type_text(self, text: str) -> None:
        self.calls.append(("type_text", text))

    def press_key(self, key: str) -> None:
        self.calls.append(("press_key", key))


if os.name == "nt":  # pragma: no branch - Windows-only executor
    _USER32 = ctypes.WinDLL("user32", use_last_error=True)
else:  # pragma: no cover - non-Windows import safety
    _USER32 = None


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
ULONG_PTR = getattr(wintypes, "ULONG_PTR", ctypes.c_size_t)

VK_RETURN = 0x0D
VK_TAB = 0x09
VK_SPACE = 0x20
VK_BACK = 0x08
VK_ESCAPE = 0x1B
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_HOME = 0x24
VK_END = 0x23
VK_DELETE = 0x2E

_VK_MAP: dict[str, int] = {
    "ENTER": VK_RETURN,
    "RETURN": VK_RETURN,
    "TAB": VK_TAB,
    "SPACE": VK_SPACE,
    "BACKSPACE": VK_BACK,
    "ESC": VK_ESCAPE,
    "ESCAPE": VK_ESCAPE,
    "LEFT": VK_LEFT,
    "UP": VK_UP,
    "RIGHT": VK_RIGHT,
    "DOWN": VK_DOWN,
    "HOME": VK_HOME,
    "END": VK_END,
    "DELETE": VK_DELETE,
}

_MODIFIER_KEYS: dict[str, int] = {
    "SHIFT": VK_SHIFT,
    "CTRL": VK_CONTROL,
    "CONTROL": VK_CONTROL,
    "ALT": VK_MENU,
    "MENU": VK_MENU,
}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", INPUTUNION)]


if _USER32 is not None:  # pragma: no branch - Windows-only configuration
    _USER32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    _USER32.SendInput.restype = wintypes.UINT


class WindowsExecutor:
    def __init__(self) -> None:
        if _USER32 is None:
            raise OSError("WindowsExecutor requires Windows")

    def type_text(self, text: str) -> None:
        for character in text:
            if character in {"\r", "\n"}:
                self.press_key("ENTER")
            elif character == "\t":
                self.press_key("TAB")
            else:
                self._send_unicode_character(character)

    def press_key(self, key: str) -> None:
        parts = [part.strip() for part in key.split("+") if part.strip()]
        if len(parts) > 1:
            self._send_chord(parts)
            return
        vk = _resolve_vk(parts[0] if parts else key)
        self._send_vk(vk)

    def _send_unicode_character(self, character: str) -> None:
        code_point = ord(character)
        self._send_input(INPUT_KEYBOARD, 0, code_point, KEYEVENTF_UNICODE)
        self._send_input(INPUT_KEYBOARD, 0, code_point, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)

    def _send_vk(self, vk: int) -> None:
        self._send_input(INPUT_KEYBOARD, vk, 0, 0)
        self._send_input(INPUT_KEYBOARD, vk, 0, KEYEVENTF_KEYUP)

    def _send_chord(self, parts: list[str]) -> None:
        modifiers = [_resolve_modifier_key(part) for part in parts[:-1]]
        main_key = _resolve_vk(parts[-1])

        for modifier in modifiers:
            self._send_input(INPUT_KEYBOARD, modifier, 0, 0)
        try:
            self._send_vk(main_key)
        finally:
            for modifier in reversed(modifiers):
                self._send_input(INPUT_KEYBOARD, modifier, 0, KEYEVENTF_KEYUP)

    def _send_input(self, input_type: int, vk: int, scan: int, flags: int) -> None:
        input_event = INPUT(
            type=input_type,
            u=INPUTUNION(
                ki=KEYBDINPUT(
                    wVk=vk,
                    wScan=scan,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        ctypes.set_last_error(0)
        result = _USER32.SendInput(1, ctypes.byref(input_event), ctypes.sizeof(INPUT))
        if result != 1:
            last_error = ctypes.get_last_error()
            if last_error:
                raise OSError(
                    last_error,
                    f"SendInput failed for vk={vk} scan={scan} flags={flags}",
                )
            raise OSError(f"SendInput failed for vk={vk} scan={scan} flags={flags}")


def _resolve_vk(key: str) -> int:
    normalized = key.strip().upper()
    if normalized in _VK_MAP:
        return _VK_MAP[normalized]
    if len(normalized) == 1:
        return ord(normalized)
    if normalized.startswith("F") and normalized[1:].isdigit():
        number = int(normalized[1:])
        if 1 <= number <= 24:
            return 0x70 + (number - 1)
    raise ValueError(f"Unsupported key: {key!r}")


def _resolve_modifier_key(key: str) -> int:
    normalized = key.strip().upper()
    try:
        return _MODIFIER_KEYS[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported modifier key: {key!r}") from exc
