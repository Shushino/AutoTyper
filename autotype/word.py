"""Opt-in native Microsoft Word DOCX insertion.

This module deliberately has no top-level pywin32 imports.  Keyboard mode
must remain importable and usable when Word or pywin32 is unavailable.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


class WordPreflightError(RuntimeError):
    """Raised when Word mode cannot safely perform a native insertion."""


class _Selection(Protocol):
    Start: int
    End: int
    StoryType: int


class _Document(Protocol):
    ReadOnly: bool
    ProtectionType: int


class _WordApplication(Protocol):
    ActiveDocument: _Document
    Selection: _Selection


@dataclass(frozen=True, slots=True)
class WordPreflightResult:
    """Validated live Word context immediately before insertion."""

    application: _WordApplication
    document: _Document
    selection: _Selection


@dataclass(frozen=True, slots=True)
class WordDryRun:
    source_path: Path

    def render(self) -> str:
        return "\n".join(
            (
                "[WORD FIDELITY DRY RUN]",
                f"Source DOCX: {self.source_path}",
                "Operation: native Microsoft Word Selection.InsertFile",
                "Mode: structural insertion, not simulated typing",
                "Keyboard timing, profile, typo, progress, and hotkey settings: not applied",
                "COM: not imported or contacted",
                "",
                "Live preflight requires:",
                "  Microsoft Word already running",
                "  an editable, unprotected active document",
                "  a collapsed caret in the main document body",
                "  the caret outside a table",
                "",
                "No Word document was changed.",
            )
        )


class WordDocumentInserter:
    """Attach to an existing Word instance and insert a DOCX natively."""

    # Word constants are stable and keeping them local avoids importing the
    # generated win32com constants module during preflight.
    _WD_MAIN_TEXT_STORY = 1
    _WD_NO_PROTECTION = -1

    def __init__(
        self,
        *,
        active_object: Callable[[str], _WordApplication] | None = None,
    ) -> None:
        self._active_object = active_object

    def preflight(self, source_path: Path) -> WordPreflightResult:
        source_path = validate_word_source(source_path)
        if os.name != "nt":
            raise WordPreflightError("Word mode requires Windows and Microsoft Word.")

        active_object = self._active_object or _load_active_object()
        try:
            application = active_object("Word.Application")
        except Exception as exc:
            raise WordPreflightError(
                "Microsoft Word is not running or could not be attached to. "
                "Open Word first; AutoTyper will not launch it."
            ) from exc

        try:
            document = application.ActiveDocument
        except Exception as exc:
            raise WordPreflightError("Microsoft Word has no active document.") from exc
        if document is None:
            raise WordPreflightError("Microsoft Word has no active document.")

        try:
            if bool(document.ReadOnly):
                raise WordPreflightError("The active Word document is read-only.")
        except WordPreflightError:
            raise
        except Exception as exc:
            raise WordPreflightError("Could not determine whether the active document is editable.") from exc

        try:
            if int(document.ProtectionType) != self._WD_NO_PROTECTION:
                raise WordPreflightError("The active Word document is protected.")
        except WordPreflightError:
            raise
        except Exception as exc:
            raise WordPreflightError("Could not determine whether the active document is protected.") from exc

        try:
            selection = application.Selection
            if selection is None:
                raise WordPreflightError("Microsoft Word has no active selection.")
            if int(selection.Start) != int(selection.End):
                raise WordPreflightError("Select a collapsed insertion point; selected text will not be replaced.")
            if int(selection.StoryType) != self._WD_MAIN_TEXT_STORY:
                raise WordPreflightError("The insertion point must be in the main document body, not a header, footer, or text box.")
            if _selection_is_in_table(selection):
                raise WordPreflightError("The insertion point must not be inside a Word table.")
        except WordPreflightError:
            raise
        except Exception as exc:
            raise WordPreflightError("Could not validate the active Word insertion point.") from exc

        return WordPreflightResult(application=application, document=document, selection=selection)

    def insert(self, source_path: Path) -> WordPreflightResult:
        # Fetch the selection immediately before the operation; callers must
        # not retain a stale selection while doing unrelated work.
        context = self.preflight(source_path.expanduser().resolve())
        try:
            context.selection.InsertFile(
                str(source_path),
                ConfirmConversions=False,
                Link=False,
                Attachment=False,
            )
        except Exception as exc:
            raise WordPreflightError(
                "Microsoft Word failed while inserting the DOCX. Content may be partially inserted; "
                "use Word's Undo (Ctrl+Z) if needed."
            ) from exc
        return context


def _load_active_object() -> Callable[[str], _WordApplication]:
    try:
        from win32com.client import GetActiveObject
    except ImportError as exc:
        raise WordPreflightError(
            "Word mode requires pywin32. Install it with 'python -m pip install pywin32'."
        ) from exc
    return GetActiveObject


def validate_word_source(source_path: Path) -> Path:
    """Validate and return an absolute, structurally recognizable DOCX path."""
    resolved = source_path.expanduser()
    if not resolved.exists():
        raise WordPreflightError(f"Word input file does not exist: {resolved}")
    if not resolved.is_file():
        raise WordPreflightError(f"Word input path is not a file: {resolved}")
    if resolved.suffix.lower() != ".docx":
        raise WordPreflightError("Word mode accepts an existing .docx file only; TXT and plain text are unsupported.")
    try:
        with zipfile.ZipFile(resolved) as archive:
            names = set(archive.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise WordPreflightError(f"Word input is not a valid DOCX package: {resolved}") from exc
    if "[Content_Types].xml" not in names or "word/document.xml" not in names:
        raise WordPreflightError(f"Word input is not a valid DOCX package: {resolved}")
    return resolved.resolve()


def _selection_is_in_table(selection: _Selection) -> bool:
    """Read Word's table context without requiring generated COM constants."""
    try:
        information = selection.Information
        # wdWithInTable == 12.
        return bool(information(12))
    except Exception as exc:
        raise WordPreflightError("Could not determine whether the insertion point is inside a Word table.") from exc
