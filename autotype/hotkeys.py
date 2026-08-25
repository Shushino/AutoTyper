from __future__ import annotations

import ctypes
import os
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .controller import RunController


if os.name == "nt":
    _USER32 = ctypes.windll.user32
else:  # pragma: no cover - non-Windows import safety
    _USER32 = None


_VK_MAP: dict[str, int] = {
    "F1": 0x70,
    "F2": 0x71,
    "F3": 0x72,
    "F4": 0x73,
    "F5": 0x74,
    "F6": 0x75,
    "F7": 0x76,
    "F8": 0x77,
    "F9": 0x78,
    "F10": 0x79,
    "F11": 0x7A,
    "F12": 0x7B,
    "F13": 0x7C,
    "F14": 0x7D,
    "F15": 0x7E,
    "F16": 0x7F,
    "F17": 0x80,
    "F18": 0x81,
    "F19": 0x82,
    "F20": 0x83,
    "F21": 0x84,
    "F22": 0x85,
    "F23": 0x86,
    "F24": 0x87,
}


def _resolve_vk(key: str) -> int:
    normalized = key.strip().upper()
    if normalized not in _VK_MAP:
        raise ValueError(f"Unsupported hotkey: {key!r}")
    return _VK_MAP[normalized]


@dataclass
class WindowsHotkeyMonitor:
    controller: RunController
    pause_key: str = "F8"
    stop_key: str = "F12"
    poll_interval_seconds: float = 0.05

    def __post_init__(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._pause_vk = _resolve_vk(self.pause_key)
        self._stop_vk = _resolve_vk(self.stop_key)

    def start(self) -> None:
        if os.name != "nt":
            raise OSError("WindowsHotkeyMonitor requires Windows")
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="autotype-hotkeys", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        pause_was_down = False
        stop_was_down = False

        while not self._stop_event.is_set():
            pause_down = bool(_USER32.GetAsyncKeyState(self._pause_vk) & 0x8000)
            stop_down = bool(_USER32.GetAsyncKeyState(self._stop_vk) & 0x8000)

            if pause_down and not pause_was_down:
                self.controller.toggle_pause()
            if stop_down and not stop_was_down:
                self.controller.request_stop()

            pause_was_down = pause_down
            stop_was_down = stop_down
            time.sleep(self.poll_interval_seconds)
