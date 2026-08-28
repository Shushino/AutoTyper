from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from .actions import Action, TypeText
from .behaviour import apply_human_behaviour, render_dry_run
from .behaviour.profiles import PROFILES
from .config import HotkeyConfig, TypingConfig
from .controller import RunController, RunState
from .executors import WindowsExecutor
from .hotkeys import WindowsHotkeyMonitor
from .input import InputError, load_input_content
from .planner import build_actions_from_content


CLI_EPILOG = """Examples:
  autotype "Hello world" --dry-run --seed 1234
  autotype --file sample.txt --countdown 0
  autotype --file sample.docx --dry-run --profile natural --seed 1234
  autotype --file lists.docx --dry-run --profile natural --seed 1234
  autotype --file lists.docx --countdown 5 --progress

Hotkeys during live runs:
  F8 toggles pause and resume
  F12 stops the current run
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autotype",
        description="Windows text typing automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CLI_EPILOG,
    )
    parser.add_argument("text", nargs="?", help="Text to type or an existing .txt/.docx file path")
    parser.add_argument("--file", type=Path, help="Read text from a .txt or .docx file with DOCX normalization")
    parser.add_argument("--speed", type=float, default=40.0, help="Typing speed in words per minute")
    parser.add_argument("--countdown", type=float, default=5.0, help="Countdown before typing starts")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="natural", help="Human behaviour profile")
    parser.add_argument("--seed", type=int, help="Seed for deterministic timing variation")
    parser.add_argument("--typo-rate", type=_typo_rate, default=0.0, help="Typo rate between 0.0 and 0.10")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions instead of typing")
    parser.add_argument("--progress", action="store_true", help="Show live progress while typing")
    parser.add_argument("--pause-key", default="F8", help="Hotkey for pause/resume")
    parser.add_argument("--stop-key", default="F12", help="Hotkey for emergency stop")
    parser.add_argument("--poll-interval", type=float, default=0.05, help="Hotkey polling interval in seconds")
    return parser


def read_input_text(args: argparse.Namespace) -> str:
    try:
        return load_input_content(args.text, args.file).to_text()
    except InputError as exc:
        raise SystemExit(str(exc)) from exc


def read_input_content(args: argparse.Namespace):
    try:
        return load_input_content(args.text, args.file)
    except InputError as exc:
        raise SystemExit(str(exc)) from exc


def _typo_rate(value: str) -> float:
    rate = float(value)
    if not 0.0 <= rate <= 0.10:
        raise argparse.ArgumentTypeError("--typo-rate must be between 0.0 and 0.10")
    return rate


def _format_live_status(state: RunState, message: str) -> str:
    if state == RunState.COUNTDOWN:
        return f"Countdown: {message}"
    if state == RunState.RUNNING:
        return "Running"
    if state == RunState.PAUSED:
        return "Paused"
    if state == RunState.STOPPED:
        return "Stopped"
    if state == RunState.IDLE:
        return "Finished"
    return message


@dataclass(slots=True)
class ProgressTracker:
    actions: Sequence[Action]
    enabled: bool
    emit_fn: Callable[[str], None] = print
    monotonic_fn: Callable[[], float] = time.monotonic
    report_interval_seconds: float = 1.0
    _completed_actions: int = field(init=False, default=0)
    _completed_characters: int = field(init=False, default=0)
    _pending_action: Action | None = field(init=False, default=None)
    _started_at: float = field(init=False)
    _last_report_at: float = field(init=False)
    _iterator_index: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        now = self.monotonic_fn()
        self._started_at = now
        self._last_report_at = now

    def __iter__(self) -> "ProgressTracker":
        return self

    def __next__(self) -> Action:
        if not self.enabled:
            return self._next_passthrough()

        if self._pending_action is not None:
            self._commit_pending_action()

        if self._iterator_index >= len(self.actions):
            raise StopIteration

        action = self.actions[self._iterator_index]
        self._iterator_index += 1
        self._pending_action = action
        return action

    def finish(self, state: RunState) -> None:
        if not self.enabled:
            return
        elapsed = self.monotonic_fn() - self._started_at
        state_label = "finished" if state == RunState.IDLE else state.name.lower()
        self.emit_fn(
            "Progress: "
            f"{self._completed_actions}/{len(self.actions)} actions, "
            f"{self._completed_characters}/{self.total_characters} chars, "
            f"elapsed {elapsed:.1f}s ({state_label})"
        )

    @property
    def total_characters(self) -> int:
        return sum(len(action.text) for action in self.actions if isinstance(action, TypeText))

    def _next_passthrough(self) -> Action:
        if self._iterator_index >= len(self.actions):
            raise StopIteration
        action = self.actions[self._iterator_index]
        self._iterator_index += 1
        return action

    def _commit_pending_action(self) -> None:
        action = self._pending_action
        if action is None:
            return
        self._completed_actions += 1
        if isinstance(action, TypeText):
            self._completed_characters += len(action.text)
        self._pending_action = None
        self._maybe_emit_progress()

    def _maybe_emit_progress(self) -> None:
        now = self.monotonic_fn()
        if now - self._last_report_at < self.report_interval_seconds:
            return
        self._last_report_at = now
        elapsed = now - self._started_at
        self.emit_fn(
            "Progress: "
            f"{self._completed_actions}/{len(self.actions)} actions, "
            f"{self._completed_characters}/{self.total_characters} chars, "
            f"elapsed {elapsed:.1f}s"
        )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    content = read_input_content(args)
    typing_config = TypingConfig(
        words_per_minute=args.speed,
        countdown_seconds=args.countdown,
        poll_interval_seconds=args.poll_interval,
    )
    hotkey_config = HotkeyConfig(pause_key=args.pause_key, stop_key=args.stop_key)
    actions = build_actions_from_content(content)

    if args.dry_run:
        print(
            render_dry_run(
                actions,
                profile=args.profile,
                wpm=args.speed,
                typo_rate=args.typo_rate,
                seed=args.seed,
                input_kind=content.source_kind,
            )
        )
        return 0

    behavioural_actions = apply_human_behaviour(
        actions,
        profile=args.profile,
        wpm=args.speed,
        typo_rate=args.typo_rate,
        seed=args.seed,
    )

    if os.name != "nt":
        raise SystemExit("Live typing requires Windows.")

    def status_callback(state: RunState, message: str) -> None:
        print(_format_live_status(state, message))

    executor = WindowsExecutor()
    controller = RunController(executor=executor, config=typing_config, status_callback=status_callback)
    monitor = WindowsHotkeyMonitor(
        controller=controller,
        pause_key=hotkey_config.pause_key,
        stop_key=hotkey_config.stop_key,
        poll_interval_seconds=typing_config.poll_interval_seconds,
    )
    progress_tracker = ProgressTracker(actions=behavioural_actions, enabled=args.progress)

    monitor.start()
    try:
        result = controller.run(progress_tracker, countdown_seconds=typing_config.countdown_seconds)
    finally:
        monitor.close()

    progress_tracker.finish(result.state)

    if result.state == RunState.STOPPED:
        return 130
    return 0
