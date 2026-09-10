from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from .actions import Action, TypeText
from .behaviour import apply_human_behaviour, render_dry_run
from .behaviour.profiles import PROFILES
from .config import (
    AppSettings,
    ConfigError,
    DEFAULT_SETTINGS,
    HotkeyConfig,
    TypingConfig,
    DEFAULT_PAUSE_KEY,
    DEFAULT_STOP_KEY,
    default_config_path,
    load_settings,
    save_settings,
)
from .controller import RunController, RunState
from .executors import WindowsExecutor
from .hotkeys import WindowsHotkeyMonitor
from .input import InputError, load_input_content, resolve_input_path
from .hybrid_input import HybridInputError, load_hybrid_plan
from .hybrid_runner import HybridRunError, HybridRunner
from .hybrid_word import HybridWordAdapter
from .focus import WordFocusGuard
from .planner import build_actions_from_content
from .word import WordDocumentInserter, WordDryRun, WordPreflightError, validate_word_source


CLI_EPILOG = """Examples:
  autotype "Hello world" --dry-run --seed 1234
  autotype --file sample.txt --countdown 0
  autotype --file sample.docx --dry-run --profile natural --seed 1234
  autotype --file lists.docx --dry-run --profile natural --seed 1234
  autotype --file lists.docx --countdown 5 --progress
  autotype --file lists.docx --target word --dry-run
  autotype --file lists.docx --target word
  autotype --show-config
  autotype --speed 110 --save-config --config .pytest-tmp/custom_config.json

Hotkeys during live runs:
  PAUSE/BREAK toggles pause and resume
  CTRL+PAUSE/BREAK stops the current run
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autotype",
        description="Windows document automation: simulated keyboard typing or native Word DOCX insertion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=CLI_EPILOG,
    )
    parser.add_argument("text", nargs="?", help="Text to type or an existing .txt/.docx file path")
    parser.add_argument("--file", type=Path, help="Read text from a .txt or .docx file with DOCX normalization")
    parser.add_argument("--target", choices=("keyboard", "word", "hybrid"), default="keyboard", help="Execution target (default: keyboard): simulated typing, native Word insertion, or experimental hybrid typing")
    parser.add_argument("--config", type=Path, default=argparse.SUPPRESS, help="Read and write settings from a JSON config file")
    parser.add_argument("--speed", type=float, default=argparse.SUPPRESS, help="Typing speed in words per minute")
    parser.add_argument("--countdown", type=float, default=argparse.SUPPRESS, help="Countdown before typing starts")
    parser.add_argument("--profile", choices=sorted(PROFILES), default=argparse.SUPPRESS, help="Human behaviour profile")
    parser.add_argument("--seed", type=int, help="Seed for deterministic timing variation")
    parser.add_argument("--typo-rate", type=_typo_rate, default=argparse.SUPPRESS, help="Typo rate between 0.0 and 0.10")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions instead of typing")
    progress_group = parser.add_mutually_exclusive_group()
    progress_group.add_argument("--progress", dest="progress", action="store_true", default=argparse.SUPPRESS, help="Show live progress while typing")
    progress_group.add_argument("--no-progress", dest="progress", action="store_false", default=argparse.SUPPRESS, help="Disable live progress while typing")
    parser.add_argument("--show-config", action="store_true", help="Print the effective configuration and exit")
    parser.add_argument("--save-config", action="store_true", help="Save the effective configuration and exit")
    parser.add_argument("--pause-key", default=DEFAULT_PAUSE_KEY, help="Hotkey for pause/resume (default: PAUSE)")
    parser.add_argument("--stop-key", default=DEFAULT_STOP_KEY, help="Hotkey for emergency stop (default: CTRL+PAUSE)")
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


def _settings_from_namespace(args: argparse.Namespace, base: AppSettings) -> AppSettings:
    overrides: dict[str, object] = {}
    for field_name in ("profile", "speed", "typo_rate", "countdown", "progress"):
        if hasattr(args, field_name):
            overrides[field_name] = getattr(args, field_name)
    if not overrides:
        return base
    return base.with_overrides(**overrides)


def _load_configured_settings(args: argparse.Namespace) -> tuple[AppSettings, Path | None]:
    explicit_config = getattr(args, "config", None)
    if explicit_config is not None:
        loaded = load_settings(explicit_config, allow_missing=args.save_config)
        if loaded is None:
            return DEFAULT_SETTINGS, explicit_config.expanduser()
        return loaded, explicit_config.expanduser()

    try:
        config_path = default_config_path()
    except ConfigError:
        return DEFAULT_SETTINGS, None

    loaded = load_settings(config_path, allow_missing=True)
    if loaded is None:
        return DEFAULT_SETTINGS, config_path
    return loaded, config_path


def _effective_settings(args: argparse.Namespace) -> tuple[AppSettings, Path | None]:
    base_settings, config_path = _load_configured_settings(args)
    return _settings_from_namespace(args, base_settings), config_path


def _print_effective_config(settings: AppSettings) -> None:
    print(json.dumps(settings.to_json_dict(), indent=2, sort_keys=True))


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
    try:
        settings, config_path = _effective_settings(args)

        if args.save_config:
            target_path = getattr(args, "config", None)
            if target_path is None:
                target_path = config_path or default_config_path()
            save_settings(target_path, settings)
            print(f"Saved configuration to {target_path.expanduser()}")

        if args.show_config:
            _print_effective_config(settings)
            return 0

        if args.save_config:
            return 0
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc

    if args.target == "word":
        return _run_word_target(args)
    if args.target == "hybrid":
        return _run_hybrid_target(args, settings)

    content = read_input_content(args)
    typing_config = TypingConfig(
        words_per_minute=settings.speed,
        countdown_seconds=settings.countdown,
        poll_interval_seconds=args.poll_interval,
    )
    hotkey_config = HotkeyConfig(pause_key=args.pause_key, stop_key=args.stop_key)
    actions = build_actions_from_content(content)

    if args.dry_run:
        print(
            render_dry_run(
                actions,
                profile=settings.profile,
                wpm=settings.speed,
                typo_rate=settings.typo_rate,
                seed=args.seed,
                input_kind=content.source_kind,
            )
        )
        return 0

    behavioural_actions = apply_human_behaviour(
        actions,
        profile=settings.profile,
        wpm=settings.speed,
        typo_rate=settings.typo_rate,
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
    progress_tracker = ProgressTracker(actions=behavioural_actions, enabled=settings.progress)

    monitor.start()
    try:
        result = controller.run(progress_tracker, countdown_seconds=typing_config.countdown_seconds)
    finally:
        monitor.close()

    progress_tracker.finish(result.state)

    if result.state == RunState.STOPPED:
        return 130
    return 0


def _run_word_target(args: argparse.Namespace) -> int:
    source_path = resolve_input_path(args.text, args.file)
    if source_path is None:
        raise SystemExit("Word mode requires an existing .docx path via --file or the positional argument.")
    source_path = source_path.expanduser()
    if source_path.suffix.lower() != ".docx":
        raise SystemExit("Word mode accepts an existing .docx file only; TXT and plain text are unsupported.")

    if args.dry_run:
        try:
            # Dry run validates the source package but intentionally never
            # imports pywin32 or contacts Word.
            print(WordDryRun(source_path=validate_word_source(source_path)).render())
            return 0
        except WordPreflightError as exc:
            raise SystemExit(str(exc)) from exc

    print("[Word mode] Native DOCX insertion — not simulated typing.")
    print("[Word mode] Keyboard-only settings are accepted for compatibility but are not applied.")
    try:
        def report_preflight(_: object) -> None:
            print("[Word mode] Checking destination: Word is running, the active document is editable, and the caret is valid.")
            print(f"[Word mode] Inserting {source_path.name}...")

        WordDocumentInserter().insert(source_path, on_preflight=report_preflight)
    except WordPreflightError as exc:
        raise SystemExit(str(exc)) from exc
    print("[Word mode] Native insertion complete. The document was not saved automatically.")
    return 0


def _run_hybrid_target(args: argparse.Namespace, settings: AppSettings) -> int:
    source_path = resolve_input_path(args.text, args.file)
    if source_path is None:
        raise SystemExit("Hybrid mode requires an existing .docx path via --file or the positional argument.")
    try:
        plan = load_hybrid_plan(source_path)
    except HybridInputError as exc:
        raise SystemExit(str(exc)) from exc

    if args.dry_run:
        print(_render_hybrid_dry_run(plan))
        return 0

    print("[Hybrid mode] Experimental COM-assisted visible typing.")
    if settings.typo_rate > 0:
        print("[Hybrid mode] Typos are corrected immediately within the current text run.")
    print("[Hybrid mode] Checking destination...")
    try:
        runner = HybridRunner(
            adapter=HybridWordAdapter(),
            focus_guard=WordFocusGuard(),
            executor=WindowsExecutor(),
            typing_config=TypingConfig(
                words_per_minute=settings.speed,
                countdown_seconds=settings.countdown,
                poll_interval_seconds=args.poll_interval,
            ),
            profile=settings.profile,
            seed=args.seed,
            typo_rate=settings.typo_rate,
            pause_key=args.pause_key,
            stop_key=args.stop_key,
        )
        result = runner.run(plan)
    except (HybridRunError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"[Hybrid mode] Complete: {result.completed_targets} typed segments. The document was not saved automatically.")
    return 0


def _render_hybrid_dry_run(plan) -> str:
    unsupported = "none" if not plan.unsupported else "; ".join(f"{item.kind}: {item.detail}" for item in plan.unsupported)
    return "\n".join(
        (
            "[HYBRID DRY RUN]",
            f"Source DOCX: {plan.source_path}",
            "Mode: experimental COM-assisted visible typing, not native InsertFile",
            f"Blocks: {len(plan.blocks)}",
            f"Paragraphs: {plan.paragraph_count}",
            f"Runs: {plan.run_count}",
            f"Lists: {plan.list_count}",
            f"Tables: {plan.table_count}",
            f"Cells: {plan.cell_count}",
            f"Unsupported: {unsupported}",
            "Workflow: COM creates supported structures and formatting; Windows keyboard input types text visibly.",
            "COM: not imported or contacted",
            "No Word document was changed.",
        )
    )
