from __future__ import annotations

from pathlib import Path

import autotype.cli as cli_module
from docx import Document

from autotype.cli import build_parser, main
from autotype.executors import MockExecutor


def _write_table_docx(path: Path) -> None:
    document = Document()
    document.add_paragraph("Intro")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "A"
    table.cell(0, 1).text = "B"
    table.cell(1, 0).text = "C"
    table.cell(1, 1).text = "D"
    document.add_paragraph("Outro")
    document.save(path)


def _write_formatted_docx(path: Path) -> None:
    document = Document()

    paragraph = document.add_paragraph()
    paragraph.add_run("Plain ")
    bold_run = paragraph.add_run("Bold")
    bold_run.bold = True
    paragraph.add_run(" ")
    italic_run = paragraph.add_run("Italic")
    italic_run.italic = True
    paragraph.add_run(" ")
    underline_run = paragraph.add_run("Underline")
    underline_run.underline = True

    table = document.add_table(rows=1, cols=1)
    table_run = table.cell(0, 0).paragraphs[0].add_run("Cell")
    table_run.bold = True

    document.save(path)


def _write_list_docx(path: Path) -> None:
    document = Document()
    document.add_paragraph("Intro")
    document.add_paragraph("Bullet", style="List Bullet")
    document.add_paragraph("Numbered", style="List Number")
    document.save(path)


def test_parser_accepts_text_and_controls() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "hello",
            "--speed",
            "55",
            "--countdown",
            "2",
            "--profile",
            "careful",
            "--seed",
            "1234",
            "--typo-rate",
            "0.05",
            "--dry-run",
            "--pause-key",
            "F7",
            "--stop-key",
            "F11",
        ]
    )

    assert args.text == "hello"
    assert args.speed == 55.0
    assert args.countdown == 2.0
    assert args.profile == "careful"
    assert args.seed == 1234
    assert args.typo_rate == 0.05
    assert args.dry_run is True
    assert args.progress is False
    assert args.pause_key == "F7"
    assert args.stop_key == "F11"


def test_parser_help_includes_examples_and_progress_flag() -> None:
    help_text = build_parser().format_help()

    assert "Examples:" in help_text
    assert "autotype \"Hello world\" --dry-run --seed 1234" in help_text
    assert "autotype --file lists.docx --dry-run --profile natural --seed 1234" in help_text
    assert "autotype --file lists.docx --countdown 5 --progress" in help_text
    assert "--progress" in help_text


def test_dry_run_cli_returns_success(capsys) -> None:
    exit_code = main(
        [
            "hello",
            "--dry-run",
            "--speed",
            "60",
            "--countdown",
            "0",
            "--profile",
            "precise",
            "--seed",
            "7",
            "--typo-rate",
            "0.0",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[DRY RUN]" in captured.out
    assert "Profile: precise" in captured.out
    assert "Typo rate: 0.000" in captured.out
    assert "Seed: 7" in captured.out
    assert "TypeText('h')" in captured.out
    assert "Pause(" in captured.out
    assert "Estimated total duration:" in captured.out
    assert "Summary:" in captured.out
    assert "Input kind: plain text" in captured.out


def test_dry_run_cli_reports_docx_summary_and_formatting(tmp_path: Path, capsys) -> None:
    path = tmp_path / "formatted.docx"
    _write_formatted_docx(path)

    exit_code = main(["--file", str(path), "--dry-run", "--speed", "60", "--countdown", "0", "--profile", "precise", "--seed", "7"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Input kind: DOCX" in captured.out
    assert "Formatting toggles: 8" in captured.out
    assert "Characters: 32" in captured.out
    assert "KeyPress('CTRL+B')" in captured.out
    assert "KeyPress('CTRL+I')" in captured.out
    assert "KeyPress('CTRL+U')" in captured.out


def test_dry_run_cli_reports_docx_list_prefixes(tmp_path: Path, capsys) -> None:
    path = tmp_path / "lists.docx"
    _write_list_docx(path)

    exit_code = main(["--file", str(path), "--dry-run", "--speed", "60", "--countdown", "0", "--profile", "precise", "--seed", "7"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Input kind: DOCX" in captured.out
    assert "TypeText('\\uf0b7')" in captured.out
    assert "TypeText('1')" in captured.out
    assert "TypeText('.')" in captured.out


def test_dry_run_cli_accepts_table_docx_positional_input(tmp_path: Path, capsys) -> None:
    path = tmp_path / "sample.docx"
    _write_table_docx(path)

    exit_code = main([str(path), "--dry-run", "--speed", "60", "--countdown", "0", "--profile", "precise", "--seed", "7"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "TypeText('I')" in captured.out
    assert "TypeText('\\t')" in captured.out
    assert "TypeText('O')" in captured.out


def test_dry_run_cli_accepts_table_docx_via_file_flag(tmp_path: Path, capsys) -> None:
    path = tmp_path / "sample.docx"
    _write_table_docx(path)

    exit_code = main(["--file", str(path), "--dry-run", "--speed", "60", "--countdown", "0", "--profile", "precise", "--seed", "7"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "TypeText('\\t')" in captured.out
    assert "TypeText('D')" in captured.out


class _DummyHotkeyMonitor:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def start(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_live_run_prints_friendly_status_and_progress(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli_module, "WindowsExecutor", MockExecutor)
    monkeypatch.setattr(cli_module, "WindowsHotkeyMonitor", _DummyHotkeyMonitor)

    exit_code = main([
        "hello",
        "--countdown",
        "0",
        "--profile",
        "precise",
        "--seed",
        "7",
        "--progress",
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Running" in captured.out
    assert "Finished" in captured.out
    assert "Progress:" in captured.out
    assert "Idle" not in captured.out
