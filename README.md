# AutoType

AutoType is a Windows-only Python project for controlled keyboard automation.

## Current Milestone

Milestone 12 adds an opt-in native Microsoft Word fidelity target while preserving the keyboard target.

Action flow:

- planner creates clean source-intent actions
- behavior engine first adds deterministic typos and corrections
- the timing layer expands the resulting source-intent stream into a timed action schedule
- controller executes the resulting actions in order

What it now does:

- plain-text typing
- `.txt` and `.docx` input
- DOCX paragraph and merged-cell-aware table extraction
- DOCX bulleted and numbered list normalization
- direct DOCX run formatting for bold, italic, underline, all caps, small caps, superscript, and subscript
- typed action model with `TypeText`, `Pause`, and `KeyPress`
- configurable typing speed
- configurable typo simulation with deterministic seeds
- countdown
- pause and resume
- emergency stop
- dry-run output with behavior timing
- dry-run summaries with counts for characters, actions, typos, and formatting toggles
- clearer live status output
- optional progress output during live runs
- persistent user configuration with CLI override support
- CLI entry point
- mock executor for tests
- four behavior profiles: `precise`, `natural`, `careful`, `fast`
- deterministic timing with `--seed`
- opt-in native Word DOCX insertion with `--target word`

## Safety

AutoType never starts typing automatically on launch.
Live automation requires an explicit run command.

Emergency stop is available during countdown, during pauses, and while typing.

## Install

```bash
python -m pip install -e .[dev]
```

DOCX parsing uses `python-docx`, which is included as a runtime dependency.

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

Execution targets:

```bash
# Default: human-like keyboard typing into the focused application
autotype --file input.docx --target keyboard

# Native insertion into an already-running, active Microsoft Word document
autotype --file input.docx --target word
```

Word fidelity mode requires Windows, Microsoft Word already running, and a
collapsed caret in the editable main document body. It inserts the original
DOCX natively; it does not type character-by-character, apply timing, or
introduce typos. Timing, profile, typo, progress, and hotkey settings are not
applied in this mode. AutoTyper does not launch Word, save the document, or
change Word's AutoCorrect/AutoFormat settings.

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
- `--typo-rate` enables deterministic typo simulation from `0.0` to `0.10`
- `--file` reads from an explicit `.txt` or `.docx` file
- `--progress` shows lightweight live progress during execution
- `--no-progress` disables live progress explicitly
- `--config` loads or saves JSON configuration
- `--show-config` prints the effective configuration and exits
- `--save-config` writes the effective configuration and exits

## Configuration

AutoTyper reads configuration from `%APPDATA%\AutoTyper\config.json` when present.

Supported persisted settings:

- `profile`
- `speed`
- `typo_rate`
- `countdown`
- `progress`

Precedence is:

1. explicit CLI value
2. saved configuration value
3. built-in default

`--show-config` prints the effective merged configuration.
`--save-config` validates the effective configuration and writes it back atomically.
`--config` can point to an alternate JSON file when you want to load or save settings somewhere else.

## Input Normalization

- Plain strings stay plain strings.
- Existing `.txt` and `.docx` paths passed positionally are treated as files.
- DOCX paragraphs and tables are normalized into canonical text using newline and tab separators; merged cell continuations remain empty grid slots instead of duplicating anchor text.
- DOCX bulleted and numbered lists are normalized into canonical typed prefixes with consistent indentation; Word's default Symbol bullet is emitted as the portable Unicode bullet `U+2022`.
- `--target word` bypasses this lossy keyboard normalization and inserts the source DOCX as native Word content, preserving the fixture's native lists, tables, merges, styles, and supported formatting.
- Direct DOCX run formatting is preserved in the action stream using existing `KeyPress` toggles. Supported effects are bold, italic, underline, all caps, small caps, superscript, and subscript.
- Blank paragraphs become empty lines in the normalized content stream.
- Images, headers, footers, and full style inheritance are still ignored.

## Action Streams

AutoType uses three layers:

1. source intent: `TypeText`, `Pause`, and `KeyPress`
2. behavior expansion: typo/correction simulation plus human-like timing
3. execution: the controller and executor translate the final schedule into Windows input

Dry-run output shows the final behavior-expanded action stream, so the preview matches what the controller would execute.
For DOCX files, formatting toggles appear as `KeyPress('CTRL+B')`, `KeyPress('CTRL+I')`, `KeyPress('CTRL+U')`, `KeyPress('CTRL+SHIFT+A')`, `KeyPress('CTRL+SHIFT+K')`, `KeyPress('CTRL+SHIFT+EQUALS')`, and `KeyPress('CTRL+SHIFT+MINUS')` around the formatted spans.
The dry-run summary also shows the input kind, character count, action count, typo counts, formatting toggle count, and estimated duration.

## Live Output

- `Countdown` shows the remaining countdown time before typing starts
- `Running` shows that live typing is active
- `Paused` shows that typing is paused by hotkey
- `Finished` shows that the run completed normally
- `Stopped` shows that the run was interrupted with the emergency stop hotkey

## Tests

```bash
pytest
```

## Limitations

Direct run-level support is limited to the formatting effects listed above. Full style inheritance and parameterized font properties are not included:

- PPTX support
- clipboard automation
- OCR
- GUI
- full Word style inheritance
- strikethrough, highlighting, font name, font size, font colour, underline variants, and other font effects

Word fidelity mode is fixture-focused rather than arbitrary-DOCX or
pixel-perfect reproduction. It does not promise custom-template conflict
resolution, bookmark insertion, or unsupported objects such as images,
headers/footers, sections, comments, tracked changes, macros, and shapes.

Formatting shortcuts target desktop Word on Windows, require the target document to have focus, and may vary with Word version or keyboard layout. The `EQUALS` action represents the Windows `VK_OEM_PLUS` key for superscript, and `MINUS` represents `VK_OEM_MINUS` for subscript.

Those belong to future milestones.

## Roadmap

1. Milestone 1: human behaviour engine
2. Milestone 2: typo and correction engine
3. Milestone 7: basic DOCX lists
4. Milestone 8: lightweight persistent configuration
5. Milestone 9: direct DOCX character formatting expansion
6. Future milestones: richer application support beyond the fixture-focused Word target
