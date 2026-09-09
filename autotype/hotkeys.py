from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes
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

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
LLKHF_INJECTED = 0x00000010
WM_QUIT = 0x0012

_HHOOK = ctypes.c_void_p
_WPARAM = wintypes.WPARAM
_LPARAM = wintypes.LPARAM
_LRESULT = ctypes.c_ssize_t
_HOOKPROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, _WPARAM, _LPARAM)


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


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", getattr(wintypes, "ULONG_PTR", ctypes.c_size_t)),
    ]


class WindowsSuppressingHotkeyMonitor:
    """Hybrid-only hotkey monitor that consumes its control keys."""

    def __init__(
        self,
        controller: RunController,
        pause_key: str = "F8",
        stop_key: str = "F12",
        poll_interval_seconds: float = 0.05,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self.controller = controller
        self.pause_key = pause_key
        self.stop_key = stop_key
        self.poll_interval_seconds = poll_interval_seconds
        self._pause_vk = _resolve_vk(pause_key)
        self._stop_vk = _resolve_vk(stop_key)
        self._stop_event = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._hook = None
        self._callback = None
        self._error: BaseException | None = None
        self._error_code: int | None = None
        self._pause_down = False
        self._stop_down = False

    def start(self) -> None:
        if os.name != "nt":
            raise OSError("WindowsSuppressingHotkeyMonitor requires Windows")
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._ready.clear()
        self._error = None
        self._error_code = None
        self._pause_down = False
        self._stop_down = False
        self._thread = threading.Thread(target=self._run, name="autotype-hybrid-hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)
        if self._error is not None:
            error = self._error
            self.close()
            detail = ""
            if self._error_code is not None:
                detail = f" (Win32 error {self._error_code})"
            raise OSError(f"Could not install the Hybrid keyboard suppression hook{detail}.") from error
        if self._hook is None:
            self.close()
            raise OSError("Could not install the Hybrid keyboard suppression hook.")

    def close(self) -> None:
        self._stop_event.set()
        if self._thread_id is not None and os.name == "nt":
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                _configure_win32_api(user32)
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._thread_id = None
        self._hook = None
        self._callback = None

    def _run(self) -> None:
        user32 = None
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            _configure_win32_api(user32)
            kernel32.GetCurrentThreadId.argtypes = []
            kernel32.GetCurrentThreadId.restype = wintypes.DWORD
            self._thread_id = kernel32.GetCurrentThreadId()

            @_HOOKPROC
            def callback(code, message, data):
                return self._handle_hook_event(code, message, data, user32)

            self._callback = callback
            self._hook = self._install_hook(user32, callback)
            self._ready.set()
            message = wintypes.MSG()
            while not self._stop_event.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
        except BaseException as exc:
            self._error = exc
            self._ready.set()
        finally:
            if self._hook and user32 is not None:
                user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
            self._ready.set()

    def _install_hook(self, user32, callback):
        hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, callback, None, 0)
        if hook:
            return hook
        self._error_code = int(ctypes.get_last_error())
        raise OSError(
            self._error_code,
            f"SetWindowsHookExW failed with Win32 error {self._error_code}.",
        )

    def _handle_hook_event(self, code, message, data, user32) -> int:
        if code >= 0 and message in {WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP}:
            event = ctypes.cast(data, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            if not (event.flags & LLKHF_INJECTED):
                key = int(event.vkCode)
                is_down = message in {WM_KEYDOWN, WM_SYSKEYDOWN}
                if key in {self._pause_vk, self._stop_vk}:
                    if is_down:
                        if key == self._pause_vk and not self._pause_down:
                            self.controller.toggle_pause()
                            self._pause_down = True
                        elif key == self._stop_vk and not self._stop_down:
                            self.controller.request_stop()
                            self._stop_down = True
                    elif key == self._pause_vk:
                        self._pause_down = False
                    else:
                        self._stop_down = False
                    return 1
        return int(user32.CallNextHookEx(self._hook, code, message, data))


def _configure_win32_api(user32) -> None:
    """Set pointer-safe signatures for every Win32 API used by the hook."""

    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = _HHOOK
    user32.CallNextHookEx.argtypes = [_HHOOK, ctypes.c_int, _WPARAM, _LPARAM]
    user32.CallNextHookEx.restype = _LRESULT
    user32.UnhookWindowsHookEx.argtypes = [_HHOOK]
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, _WPARAM, _LPARAM]
    user32.PostThreadMessageW.restype = wintypes.BOOL
