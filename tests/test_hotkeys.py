from __future__ import annotations

import ctypes
import pytest

from autotype.hotkeys import (
    LLKHF_INJECTED,
    WH_KEYBOARD_LL,
    WM_KEYDOWN,
    WM_KEYUP,
    WindowsSuppressingHotkeyMonitor,
    _HHOOK,
    _LPARAM,
    _WPARAM,
    _KBDLLHOOKSTRUCT,
    _configure_win32_api,
)


class _Controller:
    def __init__(self) -> None:
        self.toggles = 0
        self.stops = 0

    def toggle_pause(self) -> None:
        self.toggles += 1

    def request_stop(self) -> None:
        self.stops += 1


class _User32:
    def __init__(self) -> None:
        self.forwarded = 0
        self.forwarded_args = None

    def CallNextHookEx(self, *_args) -> int:
        self.forwarded += 1
        self.forwarded_args = _args
        return 37


class _ApiFunction:
    def __init__(self, result=0) -> None:
        self.result = result
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.result


class _ApiUser32:
    def __init__(self) -> None:
        self.SetWindowsHookExW = _ApiFunction()
        self.CallNextHookEx = _ApiFunction()
        self.UnhookWindowsHookEx = _ApiFunction()
        self.GetMessageW = _ApiFunction()
        self.PostThreadMessageW = _ApiFunction()


class _InstallUser32:
    def __init__(self, handle: int) -> None:
        self.handle = handle
        self.arguments = None

    def SetWindowsHookExW(self, *args):
        self.arguments = args
        return self.handle


def _keyboard_event(vk: int, flags: int = 0):
    event = _KBDLLHOOKSTRUCT()
    event.vkCode = vk
    event.flags = flags
    return ctypes.pointer(event)


def test_hybrid_hook_consumes_f8_and_f12_without_forwarding() -> None:
    controller = _Controller()
    user32 = _User32()
    monitor = WindowsSuppressingHotkeyMonitor(controller)

    assert monitor._handle_hook_event(0, WM_KEYDOWN, _keyboard_event(monitor._pause_vk), user32) == 1
    assert monitor._handle_hook_event(0, WM_KEYUP, _keyboard_event(monitor._pause_vk), user32) == 1
    assert monitor._handle_hook_event(0, WM_KEYDOWN, _keyboard_event(monitor._stop_vk), user32) == 1
    assert monitor._handle_hook_event(0, WM_KEYUP, _keyboard_event(monitor._stop_vk), user32) == 1
    assert controller.toggles == 1
    assert controller.stops == 1
    assert user32.forwarded == 0


def test_hybrid_hook_ignores_key_repeat_until_keyup() -> None:
    controller = _Controller()
    user32 = _User32()
    monitor = WindowsSuppressingHotkeyMonitor(controller)

    monitor._handle_hook_event(0, WM_KEYDOWN, _keyboard_event(monitor._pause_vk), user32)
    monitor._handle_hook_event(0, WM_KEYDOWN, _keyboard_event(monitor._pause_vk), user32)
    monitor._handle_hook_event(0, WM_KEYUP, _keyboard_event(monitor._pause_vk), user32)
    monitor._handle_hook_event(0, WM_KEYDOWN, _keyboard_event(monitor._pause_vk), user32)
    assert controller.toggles == 2


def test_hybrid_hook_forwards_unrelated_and_injected_keys() -> None:
    controller = _Controller()
    user32 = _User32()
    monitor = WindowsSuppressingHotkeyMonitor(controller)

    assert monitor._handle_hook_event(0, WM_KEYDOWN, _keyboard_event(0x41), user32) == 37
    assert monitor._handle_hook_event(0, WM_KEYDOWN, _keyboard_event(monitor._pause_vk, LLKHF_INJECTED), user32) == 37
    assert controller.toggles == 0
    assert user32.forwarded == 2


def test_hybrid_hook_does_not_swallow_non_keyboard_messages() -> None:
    user32 = _User32()
    monitor = WindowsSuppressingHotkeyMonitor(_Controller())

    assert monitor._handle_hook_event(-1, WM_KEYDOWN, _keyboard_event(monitor._pause_vk), user32) == 37
    assert user32.forwarded == 1


def test_hybrid_hook_forwards_pointer_sized_lparam_unchanged() -> None:
    user32 = _User32()
    monitor = WindowsSuppressingHotkeyMonitor(_Controller())
    large_lparam = 0xFEDCBA9876543210

    assert monitor._handle_hook_event(-1, WM_KEYDOWN, large_lparam, user32) == 37
    assert user32.forwarded_args[3] == large_lparam


def test_hybrid_hook_configures_pointer_safe_win32_signatures() -> None:
    user32 = _ApiUser32()

    _configure_win32_api(user32)

    assert user32.SetWindowsHookExW.argtypes[2] is _HHOOK
    assert user32.CallNextHookEx.argtypes == [_HHOOK, ctypes.c_int, _WPARAM, _LPARAM]
    assert user32.UnhookWindowsHookEx.argtypes == [_HHOOK]


def test_hook_install_uses_null_module_and_ignores_stale_last_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monitor = WindowsSuppressingHotkeyMonitor(_Controller())
    user32 = _InstallUser32(1234)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 126)

    hook = monitor._install_hook(user32, object())

    assert hook == 1234
    assert user32.arguments[0] == WH_KEYBOARD_LL
    assert user32.arguments[2] is None
    assert monitor._error_code is None


def test_hook_install_surfaces_actual_win32_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monitor = WindowsSuppressingHotkeyMonitor(_Controller())
    user32 = _InstallUser32(0)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5)

    with pytest.raises(OSError) as error:
        monitor._install_hook(user32, object())

    assert error.value.errno == 5
    assert "Win32 error 5" in str(error.value)
    assert monitor._error_code == 5
