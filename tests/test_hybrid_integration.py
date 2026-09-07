"""Opt-in live smoke test for experimental hybrid typing.

This test intentionally requires a user-started Word instance and must never
run in ordinary CI or test suites.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from autotype.config import TypingConfig
from autotype.executors import WindowsExecutor
from autotype.focus import WordFocusGuard
from autotype.hybrid_model import HybridDocumentPlan, HybridParagraph, HybridRun
from autotype.hybrid_runner import HybridRunner
from autotype.hybrid_word import HybridWordAdapter


@pytest.mark.word_integration
def test_hybrid_types_a_simple_paragraph_into_a_disposable_word_document() -> None:
    if os.name != "nt":
        pytest.skip("Hybrid integration requires Windows")
    if importlib.util.find_spec("win32com") is None:
        pytest.skip("pywin32 is not installed")
    if os.environ.get("AUTOTYPER_HYBRID_INTEGRATION") != "1":
        pytest.skip("Set AUTOTYPER_HYBRID_INTEGRATION=1 to opt in")

    from win32com.client import GetActiveObject

    try:
        application = GetActiveObject("Word.Application")
    except Exception:
        pytest.skip("Microsoft Word is not already running")

    target = application.Documents.Add()
    try:
        target.Activate()
        target.Range(0, 0).Select()
        plan = HybridDocumentPlan(Path("integration.docx"), (HybridParagraph((HybridRun("Hybrid smoke test", bold=True),)),))
        result = HybridRunner(
            adapter=HybridWordAdapter(),
            focus_guard=WordFocusGuard(),
            executor=WindowsExecutor(),
            typing_config=TypingConfig(words_per_minute=1000, countdown_seconds=0),
            profile="precise",
            seed=1,
            status=lambda _: None,
        ).run(plan)
        assert result.completed_targets == 1
        assert "Hybrid smoke test" in str(target.Content.Text)
    finally:
        target.Close(SaveChanges=0)
