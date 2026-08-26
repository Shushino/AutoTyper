from __future__ import annotations

from typing import Callable

import threading
import time

from autotype.actions import KeyPress, Pause, TypeText
from autotype.config import TypingConfig
from autotype.controller import RunController, RunState
from autotype.executors import MockExecutor


def _make_fake_clock() -> tuple[list[float], Callable[[float], None], Callable[[], float]]:
    current = {"value": 0.0}
    sleep_calls: list[float] = []

    def sleep_fn(duration: float) -> None:
        sleep_calls.append(duration)
        current["value"] += duration

    def monotonic_fn() -> float:
        return current["value"]

    return sleep_calls, sleep_fn, monotonic_fn


def test_controller_runs_actions_and_returns_to_idle() -> None:
    executor = MockExecutor()
    controller = RunController(executor=executor, config=TypingConfig(words_per_minute=120, countdown_seconds=0))

    result = controller.run([TypeText("ab"), Pause(0.0), KeyPress("ENTER")], countdown_seconds=0)

    assert result.state == RunState.IDLE
    assert result.actions_executed == 3
    assert result.characters_typed == 2
    assert executor.calls == [("type_text", "a"), ("type_text", "b"), ("press_key", "ENTER")]


def test_explicit_pause_actions_cause_controller_sleeps() -> None:
    executor = MockExecutor()
    sleep_calls, sleep_fn, monotonic_fn = _make_fake_clock()
    controller = RunController(
        executor=executor,
        config=TypingConfig(words_per_minute=120, countdown_seconds=0, poll_interval_seconds=0.05),
        sleep_fn=sleep_fn,
        monotonic_fn=monotonic_fn,
    )

    result = controller.run([Pause(0.2)], countdown_seconds=0)

    assert result.state == RunState.IDLE
    assert sleep_calls
    assert sum(sleep_calls) >= 0.2


def test_typetext_does_not_add_hidden_timing() -> None:
    executor = MockExecutor()
    sleep_calls, sleep_fn, monotonic_fn = _make_fake_clock()
    controller = RunController(
        executor=executor,
        config=TypingConfig(words_per_minute=120, countdown_seconds=0, poll_interval_seconds=0.05),
        sleep_fn=sleep_fn,
        monotonic_fn=monotonic_fn,
    )

    result = controller.run([TypeText("abc")], countdown_seconds=0)

    assert result.state == RunState.IDLE
    assert sleep_calls == []
    assert executor.calls == [("type_text", "a"), ("type_text", "b"), ("type_text", "c")]


def test_pause_and_resume_are_stateful() -> None:
    executor = MockExecutor()
    controller = RunController(executor=executor, config=TypingConfig(words_per_minute=300, countdown_seconds=0))

    controller.request_pause()
    assert controller.state == RunState.IDLE

    controller._transition(RunState.RUNNING, allowed_from={RunState.IDLE})
    controller.request_pause()
    assert controller.state == RunState.PAUSED
    controller.request_resume()
    assert controller.state == RunState.RUNNING


def test_stop_transitions_to_stopped_from_running() -> None:
    executor = MockExecutor()
    controller = RunController(
        executor=executor,
        config=TypingConfig(words_per_minute=20, countdown_seconds=0, poll_interval_seconds=0.01),
    )

    started = threading.Event()

    def run_controller() -> None:
        started.set()
        controller.run([Pause(0.2)], countdown_seconds=0)

    thread = threading.Thread(target=run_controller)
    thread.start()
    started.wait(timeout=1)
    time.sleep(0.02)
    controller.request_stop()
    thread.join(timeout=2)

    assert controller.state == RunState.STOPPED
    assert executor.calls == []


def test_stop_during_countdown_is_respected() -> None:
    executor = MockExecutor()
    controller = RunController(executor=executor, config=TypingConfig(words_per_minute=120, countdown_seconds=0.2))

    thread = threading.Thread(target=lambda: controller.run([TypeText("hello")]))
    thread.start()
    time.sleep(0.05)
    controller.request_stop()
    thread.join(timeout=2)

    assert controller.state == RunState.STOPPED
    assert executor.calls == []
