from __future__ import annotations

import ctypes
import pytest

from autotype.hotkeys import (
    LLKHF_INJECTED,
    WH_KEYBOARD_LL,
    WM_KEYDOWN,
    WM_KEYUP,
    WindowsSuppressingHotkeyMonitor,
    WindowsHotkeyMonitor,
    _HHOOK,
    _LPARAM,
    _WPARAM,
    _KBDLLHOOKSTRUCT,
    _configure_win32_api,
    _parse_binding,
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


def test_hybrid_hook_consumes_pause_and_ctrl_pause_without_forwarding() -> None:
    controller = _Controller()
    user32 = _User32()
    monitor = WindowsSuppressingHotkeyMonitor(controller)

    assert monitor._handle_hook_event(0, WM_KEYDOWN, _keyboard_event(monitor._pause_vk), user32) == 1
    assert monitor._handle_hook_event(0, WM_KEYUP, _keyboard_event(monitor._pause_vk), user32) == 1
    assert monitor._handle_hook_event(0, WM_KEYDOWN, _keyboard_event(0xA2), user32) == 37
    assert monitor._handle_hook_event(0, WM_KEYDOWN, _keyboard_event(monitor._stop_vk), user32) == 1
    assert monitor._handle_hook_event(0, WM_KEYUP, _keyboard_event(monitor._stop_vk), user32) == 1
    assert monitor._handle_hook_event(0, WM_KEYUP, _keyboard_event(0xA2), user32) == 37
    assert controller.toggles == 1
    assert controller.stops == 1
    assert user32.forwarded == 2


def test_default_hook_forwards_old_f8_and_f12() -> None:
    controller = _Controller()
    user32 = _User32()
    monitor = WindowsSuppressingHotkeyMonitor(controller)

    assert monitor._handle_hook_event(0, WM_KEYDOWN, _keyboard_event(0x77), user32) == 37
    assert monitor._handle_hook_event(0, WM_KEYDOWN, _keyboard_event(0x7B), user32) == 37
    assert controller.toggles == 0
    assert controller.stops == 0


def test_polling_monitor_requires_exact_pause_chord(monkeypatch: pytest.MonkeyPatch) -> None:
    states = {0x13: 0x8000, 0x11: 0}

    class User32:
        @staticmethod
        def GetAsyncKeyState(vk):
            return states.get(vk, 0)

    import autotype.hotkeys as hotkeys
    monkeypatch.setattr(hotkeys, "_USER32", User32())
    monitor = WindowsHotkeyMonitor(_Controller())
    assert monitor._binding_down(monitor._pause_binding) is True
    states[0x11] = 0x8000
    assert monitor._binding_down(monitor._pause_binding) is False
    assert monitor._binding_down(monitor._stop_binding) is True


def test_binding_parser_preserves_f9_and_modifier_chord() -> None:
    pause = _parse_binding("f9")
    stop = _parse_binding("CTRL+SHIFT+F9")

    assert pause.key == "F9"
    assert pause.modifiers == frozenset()
    assert stop.key == "F9"
    assert stop.modifiers == frozenset({"CTRL", "SHIFT"})


@pytest.mark.parametrize("value", ["", "CTRL++F9", "CTRL+CTRL+F9", "CTRL+UNKNOWN"])
def test_binding_parser_rejects_invalid_bindings(value: str) -> None:
    with pytest.raises(ValueError):
        _parse_binding(value)


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
