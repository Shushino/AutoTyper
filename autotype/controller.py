from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Iterable

from .actions import Action, KeyPress, Pause, TypeText
from .config import TypingConfig
from .executors import ActionExecutor


class RunState(Enum):
    IDLE = auto()
    COUNTDOWN = auto()
    RUNNING = auto()
    PAUSED = auto()
    STOPPED = auto()


@dataclass(frozen=True, slots=True)
class RunResult:
    state: RunState
    actions_executed: int
    characters_typed: int


StatusCallback = Callable[[RunState, str], None]


class RunController:
    def __init__(
        self,
        executor: ActionExecutor,
        config: TypingConfig | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        monotonic_fn: Callable[[], float] = time.monotonic,
        status_callback: StatusCallback | None = None,
    ) -> None:
        self._executor = executor
        self._config = config or TypingConfig()
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn
        self._status_callback = status_callback

        self._state_lock = threading.Lock()
        self._state = RunState.IDLE
        self._stop_event = threading.Event()
        self._run_gate = threading.Event()
        self._run_gate.set()

    @property
    def state(self) -> RunState:
        with self._state_lock:
            return self._state

    @property
    def config(self) -> TypingConfig:
        return self._config

    def toggle_pause(self) -> None:
        if self.state == RunState.RUNNING:
            self.request_pause()
        elif self.state == RunState.PAUSED:
            self.request_resume()

    def request_pause(self) -> None:
        if self.state != RunState.RUNNING:
            return
        self._transition(RunState.PAUSED, allowed_from={RunState.RUNNING})
        self._run_gate.clear()

    def request_resume(self) -> None:
        if self.state != RunState.PAUSED:
            return
        self._run_gate.set()
        self._transition(RunState.RUNNING, allowed_from={RunState.PAUSED})

    def request_stop(self) -> None:
        self._stop_event.set()
        self._run_gate.set()
        current = self.state
        if current == RunState.IDLE or current == RunState.STOPPED:
            return
        if current != RunState.IDLE:
            self._transition(RunState.STOPPED, allowed_from={RunState.COUNTDOWN, RunState.RUNNING, RunState.PAUSED})

    def reset(self) -> None:
        with self._state_lock:
            if self._state != RunState.STOPPED:
                raise RuntimeError("reset() is only allowed after STOPPED")
            self._state = RunState.IDLE
        self._stop_event.clear()
        self._run_gate.set()

    def run(self, actions: Iterable[Action], countdown_seconds: float | None = None) -> RunResult:
        if self.state != RunState.IDLE:
            raise RuntimeError("run() requires the controller to be IDLE")

        self._stop_event.clear()
        self._run_gate.set()

        executed_actions = 0
        typed_characters = 0
        countdown = self._config.countdown_seconds if countdown_seconds is None else countdown_seconds

        if countdown > 0:
            self._transition(RunState.COUNTDOWN, allowed_from={RunState.IDLE})
            if not self._countdown(countdown):
                return RunResult(state=self.state, actions_executed=executed_actions, characters_typed=typed_characters)

        if self._stop_event.is_set():
            if self.state != RunState.STOPPED:
                self._transition(RunState.STOPPED, allowed_from={RunState.COUNTDOWN})
            return RunResult(state=self.state, actions_executed=executed_actions, characters_typed=typed_characters)

        self._transition(RunState.RUNNING, allowed_from={RunState.IDLE, RunState.COUNTDOWN})

        for action in actions:
            if self._stop_event.is_set():
                break

            if isinstance(action, TypeText):
                typed_characters += self._type_text(action.text)
            elif isinstance(action, Pause):
                if not self._sleep_with_checks(action.seconds):
                    break
            elif isinstance(action, KeyPress):
                self._executor.press_key(action.key)
            else:  # pragma: no cover - defensive guard
                raise TypeError(f"Unsupported action: {type(action)!r}")

            executed_actions += 1

        if self._stop_event.is_set():
            if self.state != RunState.STOPPED:
                self._transition(RunState.STOPPED, allowed_from={RunState.RUNNING})
        else:
            self._transition(RunState.IDLE, allowed_from={RunState.RUNNING})

        return RunResult(state=self.state, actions_executed=executed_actions, characters_typed=typed_characters)

    def _type_text(self, text: str) -> int:
        typed = 0
        for character in text:
            if self._stop_event.is_set():
                break

            self._executor.type_text(character)
            typed += 1

        return typed

    def _sleep_with_checks(self, seconds: float) -> bool:
        if seconds <= 0:
            return not self._stop_event.is_set()

        deadline = self._monotonic() + seconds
        while self._monotonic() < deadline:
            if self._stop_event.is_set():
                return False
            if self.state == RunState.PAUSED and not self._wait_for_resume():
                return False

            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break
            self._sleep(min(self._config.poll_interval_seconds, remaining))

        return not self._stop_event.is_set()

    def _countdown(self, seconds: float) -> bool:
        deadline = self._monotonic() + seconds
        next_notice = max(1, math.ceil(seconds))
        self._emit_status(RunState.COUNTDOWN, f"Starting in {next_notice}...")

        while self._monotonic() < deadline:
            if self._stop_event.is_set():
                return False
            if self.state == RunState.PAUSED and not self._wait_for_resume():
                return False

            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break

            whole_seconds = math.ceil(remaining)
            if whole_seconds != next_notice and whole_seconds > 0:
                next_notice = whole_seconds
                self._emit_status(RunState.COUNTDOWN, f"Starting in {next_notice}...")

            self._sleep(min(self._config.poll_interval_seconds, remaining))

        return not self._stop_event.is_set()

    def _wait_for_resume(self) -> bool:
        while self.state == RunState.PAUSED and not self._stop_event.is_set():
            self._run_gate.wait(timeout=self._config.poll_interval_seconds)
        return not self._stop_event.is_set()

    def _transition(self, new_state: RunState, allowed_from: set[RunState]) -> None:
        with self._state_lock:
            if self._state not in allowed_from:
                raise RuntimeError(f"Invalid transition: {self._state.name} -> {new_state.name}")
            self._state = new_state

        self._emit_status(new_state, _friendly_state_message(new_state))

    def _emit_status(self, state: RunState, message: str) -> None:
        if self._status_callback is not None:
            self._status_callback(state, message)


def _friendly_state_message(state: RunState) -> str:
    if state == RunState.IDLE:
        return "Idle"
    if state == RunState.COUNTDOWN:
        return "Countdown"
    if state == RunState.RUNNING:
        return "Running"
    if state == RunState.PAUSED:
        return "Paused"
    if state == RunState.STOPPED:
        return "Stopped"
    return state.name
