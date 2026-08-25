# AutoType

AutoType is a Windows-only Python project for controlled keyboard automation.

Milestone 0 is intentionally small:

- plain-text typing
- keyboard input abstraction
- configurable typing speed
- countdown
- pause and resume
- emergency stop
- dry-run output
- CLI entry point
- mock executor for tests

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
autotype "Hello world" --dry-run
```

Live typing:

```bash
autotype "Hello world" --countdown 5 --speed 40
```

Or type text from a file:

```bash
autotype --file text.txt
```

## Hotkeys

- `F8` toggles pause and resume
- `F12` stops the current run

## Tests

```bash
pytest
```

## Limitations

Milestone 0 does not include:

- DOCX parsing
- PPTX support
- formatting
- typo generation
- human behaviour profiles
- Word-specific automation

## Roadmap

1. Milestone 0: basic text typer
2. Milestone 1: human behaviour engine
3. Milestone 2: typo and correction engine
4. Later milestones: document parsing, formatting, and richer execution
