"""Foreground-process guard for keyboard injection into Word."""

from __future__ import annotations

import ctypes
import os


class FocusError(RuntimeError):
    pass


class WordFocusGuard:
    def __init__(self, is_word_foreground=None) -> None:
        self._is_word_foreground = is_word_foreground or _is_word_foreground

    def ensure_word_foreground(self) -> None:
        if not self._is_word_foreground():
            raise FocusError("Microsoft Word is no longer the foreground application; hybrid typing stopped before the next segment.")


def _is_word_foreground() -> bool:
    if os.name != "nt":
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    process_id = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    if not process_id.value:
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, process_id.value)
    if not handle:
        return False
    try:
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return False
        return buffer.value.lower().endswith("\\winword.exe")
    finally:
        kernel32.CloseHandle(handle)
