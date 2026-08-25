# AutoType

AutoType is a Windows-only Python project for controlled keyboard automation.

## Current Milestone

Milestone 1 adds a human-behaviour timing layer on top of the Milestone 0 text typer.

What it now does:

- plain-text typing
- text-file input
- typed action model with `TypeText`, `Pause`, and `KeyPress`
- configurable typing speed
- countdown
- pause and resume
- emergency stop
- dry-run output with behavior timing
- CLI entry point
- mock executor for tests
- four behavior profiles: `precise`, `natural`, `careful`, `fast`
- deterministic timing with `--seed`

## Safety

AutoType never starts typing automatically on launch.
Live automation requires an explicit run command.

Emergency stop is available during countdown, during pauses, and while typing.

## Install

```bash
python -m pip install -e .[dev]
```

## Run

Dry run:

```bash
autotype "Hello world" --dry-run --profile natural --seed 1234
```

Live typing:

```bash
autotype "Hello world" --countdown 5 --speed 40 --profile natural
```

Or type text from a file:

```bash
autotype --file text.txt
```

## Hotkeys

- `F8` toggles pause and resume
- `F12` stops the current run

## Profiles

- `precise`: consistent and close to the requested WPM
- `natural`: default everyday mode
- `careful`: slower with more hesitation
- `fast`: quicker with less hesitation

## Timing Controls

- `--profile` chooses the timing profile
- `--seed` makes the behavior engine deterministic for a given input
- `--speed` sets the target words per minute

## Tests

```bash
pytest
```

## Limitations

Milestone 1 still does not include:

- DOCX parsing
- PPTX support
- formatting
- typo generation
- Word-specific automation
- corrections
- clipboard automation
- OCR
- GUI

Those belong to future milestones.

## Roadmap

1. Milestone 1: human behaviour engine
2. Future milestones: typo simulation, corrections, document parsing, formatting, and richer application support
