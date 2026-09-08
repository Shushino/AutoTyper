"""COM structure adapter for experimental hybrid typing.

This adapter never launches, closes, saves, or rolls back Microsoft Word.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Callable

from .hybrid_model import HybridCell, HybridParagraph, HybridRun, HybridTable
from .word import WordPreflightError, _load_active_object, _selection_is_in_table


class HybridWordError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HybridWordContext:
    application: object
    document: object
    selection: object


class HybridWordAdapter:
    _WD_MAIN_TEXT_STORY = 1
    _WD_NO_PROTECTION = -1
    _WD_COLLAPSE_END = 0

    def __init__(self, *, active_object: Callable[[str], object] | None = None) -> None:
        self._active_object = active_object
        self._active_list_group_id: int | None = None

    def preflight(self) -> HybridWordContext:
        if os.name != "nt":
            raise HybridWordError("Hybrid mode requires Windows and Microsoft Word.")
        try:
            active_object = self._active_object or _load_active_object()
        except WordPreflightError as exc:
            raise HybridWordError(str(exc)) from exc
        try:
            application = active_object("Word.Application")
        except Exception as exc:
            raise HybridWordError(
                "Could not attach to the running Microsoft Word instance. AutoTyper will not launch it. "
                "If Word is already open, a Windows privilege-level mismatch is a likely cause; "
                "open both Word and AutoTyper normally (without Administrator elevation)."
            ) from exc
        try:
            document = application.ActiveDocument
            selection = application.Selection
        except Exception as exc:
            raise HybridWordError("Microsoft Word has no active document or selection.") from exc
        if document is None or selection is None:
            raise HybridWordError("Microsoft Word has no active document or selection.")
        try:
            if bool(document.ReadOnly):
                raise HybridWordError("The active Word document is read-only.")
            if int(document.ProtectionType) != self._WD_NO_PROTECTION:
                raise HybridWordError("The active Word document is protected.")
            if int(selection.Start) != int(selection.End):
                raise HybridWordError("Select a collapsed insertion point; hybrid mode will not replace selected text.")
            if int(selection.StoryType) != self._WD_MAIN_TEXT_STORY:
                raise HybridWordError("The insertion point must be in the main document body.")
            if _selection_is_in_table(selection):
                raise HybridWordError("The initial insertion point must not be inside a Word table.")
        except HybridWordError:
            raise
        except Exception as exc:
            raise HybridWordError("Could not validate the active Word destination.") from exc
        self._active_list_group_id = None
        return HybridWordContext(application, document, selection)

    def prepare_paragraph(self, context: HybridWordContext, paragraph: HybridParagraph) -> None:
        selection = self._selection(context)
        self._apply_paragraph(selection, paragraph)
        self._apply_list_context(selection, paragraph.list_spec)

    def revalidate(self, context: HybridWordContext) -> None:
        """Confirm the same live destination remains available after a pause."""
        selection = self._selection(context)
        try:
            if bool(context.document.ReadOnly) or int(context.document.ProtectionType) != self._WD_NO_PROTECTION:
                raise HybridWordError("The active Word document is no longer editable.")
            if int(selection.StoryType) != self._WD_MAIN_TEXT_STORY:
                raise HybridWordError("The hybrid typing target is no longer in the main document body.")
        except HybridWordError:
            raise
        except Exception as exc:
            raise HybridWordError("Could not revalidate the Word destination after pause.") from exc

    def prepare_run(self, context: HybridWordContext, run: HybridRun) -> None:
        selection = self._selection(context)
        font = selection.Font
        font.Bold = run.bold
        font.Italic = run.italic
        font.Underline = run.underline

    def advance_paragraph(self, context: HybridWordContext) -> None:
        self._selection(context).TypeParagraph()

    def create_table(self, context: HybridWordContext, table: HybridTable) -> object:
        rows = len(table.rows)
        columns = len(table.rows[0]) if table.rows else 0
        if not rows or not columns:
            raise HybridWordError("Hybrid mode cannot create an empty table.")
        try:
            self._reset_list_context(context)
            for index, width in enumerate(table.column_widths, start=1):
                if width is None:
                    continue
                numeric_width = float(width)
                if not math.isfinite(numeric_width) or not 0 <= numeric_width <= 1584:
                    raise HybridWordError(
                        f"Hybrid table column {index} has invalid width {width!r} pt; Word accepts 0 to 1584 pt."
                    )
            insertion_range = self._table_insertion_range(context)
            created = context.document.Tables.Add(insertion_range, rows, columns)
            for index, width in enumerate(table.column_widths, start=1):
                if width is not None:
                    created.Columns.Item(index).Width = float(width)
            self._apply_table_grid(created)
            return created
        except HybridWordError:
            raise
        except Exception as exc:
            detail = self._com_error_detail(exc)
            raise HybridWordError(f"Microsoft Word failed while creating a hybrid table: {detail}") from exc

    def prepare_cell(self, context: HybridWordContext, table: object, row: int, column: int, cell: HybridCell) -> None:
        if len(cell.paragraphs) != 1:
            raise HybridWordError("Hybrid mode supports one paragraph per table cell only.")
        try:
            target = table.Cell(row, column).Range.Duplicate
            target.End = target.End - 1  # Exclude Word's end-of-cell marker.
            target.Collapse(self._WD_COLLAPSE_END)
            target.Select()
        except Exception as exc:
            raise HybridWordError(f"Could not target hybrid table cell {row},{column}.") from exc
        self.prepare_paragraph(context, cell.paragraphs[0])

    def move_after_table(self, context: HybridWordContext, table: object) -> None:
        try:
            target = table.Range.Duplicate
            target.Collapse(self._WD_COLLAPSE_END)
            target.Select()
            self._selection(context).TypeParagraph()
            self._active_list_group_id = None
        except Exception as exc:
            raise HybridWordError("Could not create the paragraph after a hybrid table.") from exc

    @staticmethod
    def _selection(context: HybridWordContext):
        selection = context.application.Selection
        if selection is None:
            raise HybridWordError("The active Word document changed during hybrid typing.")
        selected_document = selection.Document
        if selected_document is not context.document:
            selected_name = getattr(selected_document, "FullName", getattr(selected_document, "Name", None))
            expected_name = getattr(context.document, "FullName", getattr(context.document, "Name", None))
            if selected_name != expected_name:
                raise HybridWordError("The active Word document changed during hybrid typing.")
        return selection

    def _apply_list_context(self, selection: object, list_spec) -> None:
        list_format = selection.Range.ListFormat
        if list_spec is None:
            self._reset_list_format(list_format)
            return
        if list_spec.group_id == self._active_list_group_id:
            return
        self._reset_list_format(list_format)
        if list_spec.kind == "bullet":
            list_format.ApplyBulletDefault()
        else:
            self._start_numbered_list(list_format)
        self._active_list_group_id = list_spec.group_id

    def _start_numbered_list(self, list_format: object) -> None:
        """Apply the default numbered template as a fresh Word list."""
        try:
            list_format.ApplyNumberDefault()
            list_format.ApplyListTemplate(list_format.ListTemplate, False)
        except Exception as exc:
            detail = self._com_error_detail(exc)
            raise HybridWordError(
                f"Microsoft Word failed while restarting a hybrid numbered list at 1: {detail}"
            ) from exc

    def _reset_list_context(self, context: HybridWordContext) -> None:
        if self._active_list_group_id is None:
            return
        self._reset_list_format(self._selection(context).Range.ListFormat)

    def _reset_list_format(self, list_format: object) -> None:
        if self._active_list_group_id is not None:
            list_format.RemoveNumbers()
            self._active_list_group_id = None

    @staticmethod
    def _apply_table_grid(table: object) -> None:
        try:
            table.Borders.Enable = True
        except Exception as exc:
            detail = HybridWordAdapter._com_error_detail(exc)
            raise HybridWordError(f"Microsoft Word failed while applying the hybrid table grid: {detail}") from exc

    def _table_insertion_range(self, context: HybridWordContext):
        """Return a fresh, collapsed range suitable for Tables.Add."""
        selection = self._selection(context)
        try:
            if int(selection.StoryType) != self._WD_MAIN_TEXT_STORY:
                raise HybridWordError("A hybrid table must be inserted in the main document body.")
            if int(selection.Start) != int(selection.End):
                raise HybridWordError("A hybrid table requires a collapsed insertion point.")
            if _selection_is_in_table(selection):
                raise HybridWordError("A hybrid table cannot be inserted inside an existing Word table.")
            insertion_range = selection.Range.Duplicate
            insertion_range.Collapse(self._WD_COLLAPSE_END)
            return insertion_range
        except HybridWordError:
            raise
        except WordPreflightError as exc:
            raise HybridWordError(str(exc)) from exc
        except Exception as exc:
            raise HybridWordError("Could not establish a valid Word range for hybrid table insertion.") from exc

    @staticmethod
    def _com_error_detail(exc: Exception) -> str:
        details: list[str] = []
        message = str(exc).strip()
        if message:
            details.append(message)
        excepinfo = getattr(exc, "excepinfo", None)
        if excepinfo:
            for item in excepinfo:
                if isinstance(item, str) and item.strip() and item not in details:
                    details.append(item.strip())
        hresult = getattr(exc, "hresult", None)
        if hresult is not None:
            value = str(hresult).strip()
            if value and value not in details:
                details.append(f"HRESULT {value}")
        return "; ".join(details) or repr(exc)

    @staticmethod
    def _apply_paragraph(selection: object, paragraph: HybridParagraph) -> None:
        try:
            if paragraph.style_name is not None:
                selection.Style = paragraph.style_name
            fmt = selection.ParagraphFormat
            if paragraph.alignment is not None:
                fmt.Alignment = paragraph.alignment
            if paragraph.left_indent is not None:
                fmt.LeftIndent = paragraph.left_indent
            if paragraph.first_line_indent is not None:
                fmt.FirstLineIndent = paragraph.first_line_indent
            if paragraph.line_spacing is not None:
                fmt.LineSpacing = paragraph.line_spacing
        except Exception as exc:
            raise HybridWordError("Could not establish hybrid paragraph formatting.") from exc
