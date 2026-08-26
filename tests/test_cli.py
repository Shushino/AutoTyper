from __future__ import annotations

from autotype.cli import build_parser, main


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
    assert args.pause_key == "F7"
    assert args.stop_key == "F11"


def test_dry_run_cli_returns_success(capsys) -> None:
    exit_code = main([
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
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[DRY RUN]" in captured.out
    assert "Profile: precise" in captured.out
    assert "Typo rate: 0.000" in captured.out
    assert "Seed: 7" in captured.out
    assert "TypeText('h')" in captured.out
    assert "Pause(" in captured.out
    assert "Estimated total duration:" in captured.out
