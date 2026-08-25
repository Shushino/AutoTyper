from __future__ import annotations

import ctypes
import os

import pytest

from autotype.executors import (
    HARDWAREINPUT,
    INPUT,
    KEYBDINPUT,
    KEYEVENTF_KEYUP,
    KEYEVENTF_UNICODE,
    MOUSEINPUT,
    WindowsExecutor,
)


@pytest.mark.skipif(os.name != "nt", reason="Windows ctypes layout is only defined on Windows")
def test_win32_input_struct_sizes_match_64bit_layout() -> None:
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(KEYBDINPUT) == 24
        assert ctypes.sizeof(MOUSEINPUT) == 32
        assert ctypes.sizeof(HARDWAREINPUT) == 8
        assert ctypes.sizeof(INPUT) == 40


def test_unicode_character_injection_uses_scan_code_and_unicode_flags(monkeypatch) -> None:
    executor = WindowsExecutor.__new__(WindowsExecutor)
    calls: list[tuple[int, int, int, int]] = []

    def fake_send_input(input_type: int, vk: int, scan: int, flags: int) -> None:
        calls.append((input_type, vk, scan, flags))

    monkeypatch.setattr(executor, "_send_input", fake_send_input)

    executor._send_unicode_character("H")

    assert calls == [
        (1, 0, ord("H"), KEYEVENTF_UNICODE),
        (1, 0, ord("H"), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP),
    ]
