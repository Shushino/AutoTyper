"""Immutable source plan for experimental COM-assisted visible Word typing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class HybridRun:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False


@dataclass(frozen=True, slots=True)
class HybridListSpec:
    kind: str  # "bullet" or "number"
    group_id: int


@dataclass(frozen=True, slots=True)
class HybridParagraph:
    runs: tuple[HybridRun, ...]
    style_name: str | None = None
    alignment: int | None = None
    left_indent: float | None = None
    first_line_indent: float | None = None
    line_spacing: float | None = None
    list_spec: HybridListSpec | None = None


@dataclass(frozen=True, slots=True)
class HybridCell:
    paragraphs: tuple[HybridParagraph, ...]


@dataclass(frozen=True, slots=True)
class HybridTable:
    rows: tuple[tuple[HybridCell, ...], ...]
    column_widths: tuple[float | None, ...] = ()


@dataclass(frozen=True, slots=True)
class HybridUnsupported:
    kind: str
    detail: str


HybridBlock: TypeAlias = HybridParagraph | HybridTable


@dataclass(frozen=True, slots=True)
class HybridDocumentPlan:
    source_path: Path
    blocks: tuple[HybridBlock, ...]
    unsupported: tuple[HybridUnsupported, ...] = ()

    @property
    def paragraph_count(self) -> int:
        return sum(isinstance(block, HybridParagraph) for block in self.blocks)

    @property
    def table_count(self) -> int:
        return sum(isinstance(block, HybridTable) for block in self.blocks)

    @property
    def cell_count(self) -> int:
        return sum(len(row) for block in self.blocks if isinstance(block, HybridTable) for row in block.rows)

    @property
    def run_count(self) -> int:
        return sum(
            len(paragraph.runs)
            for paragraph in _iter_paragraphs(self.blocks)
        )

    @property
    def list_count(self) -> int:
        return sum(paragraph.list_spec is not None for paragraph in _iter_paragraphs(self.blocks))

    def require_supported(self) -> None:
        if self.unsupported:
            details = "; ".join(f"{item.kind}: {item.detail}" for item in self.unsupported)
            raise ValueError(f"Hybrid mode cannot safely reproduce this DOCX: {details}")


def _iter_paragraphs(blocks: tuple[HybridBlock, ...]):
    for block in blocks:
        if isinstance(block, HybridParagraph):
            yield block
        else:
            for row in block.rows:
                for cell in row:
                    yield from cell.paragraphs
