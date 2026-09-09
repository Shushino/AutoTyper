"""Coordinator for COM-created Word structures and visible keyboard typing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import zlib

from .behaviour import apply_human_behaviour
from .actions import KeyPress
from .config import TypingConfig
from .controller import RunController, RunResult, RunState
from .executors import ActionExecutor
from .focus import FocusError, WordFocusGuard
from .hybrid_model import HybridDocumentPlan, HybridParagraph, HybridTable
from .hybrid_word import HybridWordAdapter, HybridWordError
from .hotkeys import WindowsSuppressingHotkeyMonitor


class HybridRunError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HybridRunResult:
    completed_targets: int
    last_target: str | None


class HybridRunner:
    def __init__(
        self,
        *,
        adapter: HybridWordAdapter,
        focus_guard: WordFocusGuard,
        executor: ActionExecutor,
        typing_config: TypingConfig,
        profile: str,
        seed: int | None,
        typo_rate: float = 0.0,
        pause_key: str = "F8",
        stop_key: str = "F12",
        hotkey_monitor_factory=WindowsSuppressingHotkeyMonitor,
        controller_factory=RunController,
        status: Callable[[str], None] = print,
    ) -> None:
        self._adapter = adapter
        self._focus = focus_guard
        self._executor = executor
        self._config = typing_config
        self._profile = profile
        self._seed = seed
        self._typo_rate = typo_rate
        self._pause_key = pause_key
        self._stop_key = stop_key
        self._hotkey_monitor_factory = hotkey_monitor_factory
        self._controller_factory = controller_factory
        self._status = status

    def run(self, plan: HybridDocumentPlan) -> HybridRunResult:
        try:
            plan.require_supported()
        except ValueError as exc:
            raise HybridRunError(str(exc)) from exc
        try:
            context = self._adapter.preflight()
        except HybridWordError as exc:
            raise HybridRunError(self._failure_message(None, exc)) from exc
        self._status("✓ Microsoft Word detected")
        self._status("✓ Active document is editable")
        self._status("✓ Caret is in the main document body")
        self._status("[Hybrid mode] Building document structure...")
        completed = 0
        last: str | None = None
        blocks = plan.blocks
        for block_index, block in enumerate(blocks, start=1):
            try:
                if isinstance(block, HybridParagraph):
                    last = f"paragraph {block_index}"
                    self._adapter.prepare_paragraph(context, block)
                    completed += self._type_paragraph(context, block, last, completed == 0)
                    if block_index < len(blocks):
                        self._adapter.advance_paragraph(context)
                else:
                    table = self._adapter.create_table(context, block)
                    for row_index, row in enumerate(block.rows, start=1):
                        for column_index, cell in enumerate(row, start=1):
                            last = f"table {block_index}, cell {row_index},{column_index}"
                            self._adapter.prepare_cell(context, table, row_index, column_index, cell)
                            completed += self._type_paragraph(context, cell.paragraphs[0], last, completed == 0)
                    if block_index < len(blocks):
                        self._adapter.move_after_table(context, table)
            except (HybridWordError, FocusError, HybridRunError, OSError) as exc:
                raise HybridRunError(self._failure_message(last, exc)) from exc
        return HybridRunResult(completed, last)

    def _type_paragraph(self, context, paragraph: HybridParagraph, target: str, first: bool) -> int:
        completed = 0
        for run_index, run in enumerate(paragraph.runs, start=1):
            if not run.text:
                continue
            self._adapter.prepare_run(context, run)
            if first and completed == 0:
                self._run_focus_handoff()
            self._focus.ensure_word_foreground()
            lease = self._capture_lease(context, target)
            actions = apply_human_behaviour(
                run_to_actions(run.text),
                profile=self._profile,
                wpm=self._config.words_per_minute,
                typo_rate=self._typo_rate,
                seed=_segment_seed(self._seed, target, run_index),
                correction_policy="immediate",
            )
            self._validate_actions(actions)
            if completed == 0:
                self._status(f"[Hybrid mode] Typing {target}...")
            resume_check = {"required": False, "paused": False}

            def status_callback(state: RunState, _: str) -> None:
                if state == RunState.PAUSED:
                    resume_check["paused"] = True
                elif state == RunState.RUNNING and resume_check["paused"]:
                    resume_check["required"] = True

            executor = _ResumeCheckedExecutor(self._executor, self._adapter, context, self._focus, resume_check, lease, run)
            controller = self._controller_factory(executor=executor, config=self._config, status_callback=status_callback)
            monitor = self._hotkey_monitor_factory(
                controller=controller,
                pause_key=self._pause_key,
                stop_key=self._stop_key,
                poll_interval_seconds=self._config.poll_interval_seconds,
            )
            try:
                monitor.start()
                result = controller.run(actions, countdown_seconds=0)
            finally:
                monitor.close()
            if result.state == RunState.STOPPED:
                raise HybridRunError("Hybrid typing was stopped by the emergency stop control.")
            completed += 1
        return completed

    def _run_focus_handoff(self) -> None:
        countdown = self._config.countdown_seconds
        if countdown <= 0:
            return

        self._status("[Hybrid mode] Switch to the Word document and leave it in the foreground.")

        def status_callback(state: RunState, message: str) -> None:
            if state == RunState.COUNTDOWN and message != "Countdown":
                self._status(f"Countdown: {message}")

        controller = self._controller_factory(
            executor=self._executor,
            config=self._config,
            status_callback=status_callback,
        )
        monitor = self._hotkey_monitor_factory(
            controller=controller,
            pause_key=self._pause_key,
            stop_key=self._stop_key,
            poll_interval_seconds=self._config.poll_interval_seconds,
        )
        try:
            monitor.start()
            result: RunResult = controller.run((), countdown_seconds=countdown)
        finally:
            monitor.close()
        if result.state == RunState.STOPPED:
            raise HybridRunError("Hybrid focus handoff was stopped by the emergency stop control.")

    def _capture_lease(self, context, target: str):
        capture = getattr(self._adapter, "capture_run_lease", None)
        if capture is None:
            return None
        return capture(context, target)

    @staticmethod
    def _validate_actions(actions) -> None:
        navigation_keys = {
            "LEFT", "RIGHT", "UP", "DOWN", "HOME", "END",
            "PAGEUP", "PAGEDOWN", "CTRL+LEFT", "CTRL+RIGHT",
            "CTRL+SHIFT+LEFT", "CTRL+SHIFT+RIGHT",
            "SHIFT+LEFT", "SHIFT+RIGHT", "CTRL+A",
        }
        for action in actions:
            if not isinstance(action, KeyPress):
                continue
            key = action.key.upper()
            parts = set(key.split("+"))
            if key != "BACKSPACE" and parts.intersection({"BACKSPACE", "DELETE"}):
                raise HybridRunError(
                    f"Hybrid generated unsafe cursor-modifying action {action.key!r}; refusing to execute this segment."
                )
            if key in navigation_keys or parts.intersection({"LEFT", "RIGHT", "UP", "DOWN", "HOME", "END"}):
                raise HybridRunError(
                    f"Hybrid generated unsafe cursor-navigation action {action.key!r}; refusing to execute this segment."
                )

    @staticmethod
    def _failure_message(last: str | None, exc: Exception) -> str:
        target = last or "the initial destination"
        return f"Hybrid mode stopped near {target}. The document may be partially modified; inspect it and use Word's Undo (Ctrl+Z) manually if needed. {exc}"


def run_to_actions(text: str):
    from .actions import TypeText
    return [TypeText(text)]


def _segment_seed(seed: int | None, target: str, run_index: int) -> int | None:
    if seed is None:
        return None
    return zlib.crc32(f"{seed}:{target}:{run_index}".encode("utf-8"))


class _ResumeCheckedExecutor:
    def __init__(self, delegate: ActionExecutor, adapter: HybridWordAdapter, context, focus: WordFocusGuard, resume_check, lease, run) -> None:
        self._delegate = delegate
        self._adapter = adapter
        self._context = context
        self._focus = focus
        self._resume_check = resume_check
        self._lease = lease
        self._run = run

    def type_text(self, text: str) -> None:
        self._revalidate_if_needed()
        self._delegate.type_text(text)
        if self._lease is not None:
            self._lease.record_text(text)

    def press_key(self, key: str) -> None:
        self._revalidate_if_needed()
        if self._lease is not None and key.upper() == "BACKSPACE":
            self._lease.record_backspace()
        self._delegate.press_key(key)

    def _revalidate_if_needed(self) -> None:
        if self._resume_check["required"]:
            self._focus.ensure_word_foreground()
            if self._lease is not None:
                self._adapter.resume_run(self._context, self._lease, self._run)
            else:
                self._adapter.revalidate(self._context)
            self._resume_check["required"] = False
