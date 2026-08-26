from __future__ import annotations

import argparse
import os
from pathlib import Path

from .behaviour import apply_human_behaviour, render_dry_run
from .behaviour.profiles import PROFILES
from .config import HotkeyConfig, TypingConfig
from .controller import RunController, RunState
from .executors import WindowsExecutor
from .hotkeys import WindowsHotkeyMonitor
from .planner import build_actions_from_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autotype", description="Windows text typing automation")
    parser.add_argument("text", nargs="?", help="Text to type")
    parser.add_argument("--file", type=Path, help="Read text from a file")
    parser.add_argument("--speed", type=float, default=40.0, help="Typing speed in words per minute")
    parser.add_argument("--countdown", type=float, default=5.0, help="Countdown before typing starts")
    parser.add_argument("--profile", choices=sorted(PROFILES), default="natural", help="Human behaviour profile")
    parser.add_argument("--seed", type=int, help="Seed for deterministic timing variation")
    parser.add_argument("--typo-rate", type=_typo_rate, default=0.0, help="Typo rate between 0.0 and 0.10")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions instead of typing")
    parser.add_argument("--pause-key", default="F8", help="Hotkey for pause/resume")
    parser.add_argument("--stop-key", default="F12", help="Hotkey for emergency stop")
    parser.add_argument("--poll-interval", type=float, default=0.05, help="Hotkey polling interval in seconds")
    return parser


def read_input_text(args: argparse.Namespace) -> str:
    if args.file is not None:
        return args.file.read_text(encoding="utf-8")
    if args.text is not None:
        return args.text
    raise SystemExit("Provide either text or --file.")


def _typo_rate(value: str) -> float:
    rate = float(value)
    if not 0.0 <= rate <= 0.10:
        raise argparse.ArgumentTypeError("--typo-rate must be between 0.0 and 0.10")
    return rate


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    text = read_input_text(args)
    typing_config = TypingConfig(
        words_per_minute=args.speed,
        countdown_seconds=args.countdown,
        poll_interval_seconds=args.poll_interval,
    )
    hotkey_config = HotkeyConfig(pause_key=args.pause_key, stop_key=args.stop_key)
    actions = build_actions_from_text(text)

    if args.dry_run:
        print(
            render_dry_run(
                actions,
                profile=args.profile,
                wpm=args.speed,
                typo_rate=args.typo_rate,
                seed=args.seed,
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
        print(message)

    executor = WindowsExecutor()
    controller = RunController(executor=executor, config=typing_config, status_callback=status_callback)
    monitor = WindowsHotkeyMonitor(
        controller=controller,
        pause_key=hotkey_config.pause_key,
        stop_key=hotkey_config.stop_key,
        poll_interval_seconds=typing_config.poll_interval_seconds,
    )

    monitor.start()
    try:
        result = controller.run(behavioural_actions, countdown_seconds=typing_config.countdown_seconds)
    finally:
        monitor.close()

    if result.state == RunState.STOPPED:
        return 130
    return 0
