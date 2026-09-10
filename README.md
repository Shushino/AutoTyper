# AutoType

AutoType is a Windows-only Python project for controlled keyboard automation.

## Current Milestone

M14.11.2 is the current shipped checkpoint. It preserves the original keyboard
target, the native Word target, and the experimental Hybrid target while adding
bounded-local Hybrid corrections and persistent hotkey settings.

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
- experimental COM-assisted visible Word typing with `--target hybrid`

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

# Experimental: create supported Word structures, then type source text visibly
autotype --file input.docx --target hybrid
```

Word fidelity mode requires Windows, Microsoft Word already running, and a
collapsed caret in the editable main document body. It inserts the original
DOCX natively; it does not type character-by-character, apply timing, or
introduce typos. Timing, profile, typo, progress, and hotkey settings are not
applied in this mode. AutoTyper does not launch Word, save the document, or
change Word's AutoCorrect/AutoFormat settings. See [Word mode](docs/word-mode.md)
for the normal-privilege workflow and troubleshooting.

| Target | Default | Use it for | DOCX structure |
| --- | --- | --- | --- |
| `keyboard` | Yes | Portable, human-like simulated typing and the broadest behaviour-engine coverage | Lossy linearized text/action stream; tables become text |
| `word` | No | Highest structural/formatting fidelity for a source DOCX | Word natively inserts paragraphs, lists, tables, merges, and supported styles |
| `hybrid` | No | Visible typing into constrained native Word structures | COM-created paragraphs, lists, formatting, and simple bordered tables |

Hybrid mode is experimental and Windows/Word-only. It creates supported native
Word structures through COM, then types the source text visibly through the
keyboard executor. It is not proof of human authorship and does not guarantee
arbitrary DOCX or pixel-perfect fidelity. It currently supports normal and
built-in heading paragraphs; paragraph alignment, indentation, and basic line
spacing; logical single-level bullet and numbered lists; and rectangular,
unmerged tables with deterministic visible borders. Direct run-level support
includes bold, italic, underline, font name, point size, explicit RGB colour,
superscript, subscript, and strikethrough. Hybrid also provides human timing,
pause/resume, emergency stop, and bounded-local immediate typo correction.
See
[Hybrid mode](docs/hybrid-mode.md) for prerequisites, recovery, and limits.

## Hotkeys

- `PAUSE/BREAK` toggles pause and resume
- `CTRL+PAUSE/BREAK` stops the current run

Some laptops expose Pause/Break only through an Fn-layer. Custom bindings can
still be supplied with `--pause-key` and `--stop-key`, or persisted in
`%APPDATA%\\AutoTyper\\config.json`. F8 and F12 are no longer the defaults
because Word uses them for useful editing commands. Risky custom bindings are
allowed but produce a warning; keyboard polling cannot distinguish a matching
AutoTyper-generated keystroke from a user's hotkey.

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
- `--target hybrid` is experimental and accepts existing `.docx` inputs only
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
- `hotkeys.pause` and `hotkeys.stop`

Saved configuration uses schema version 2. The hotkey values are strings such
as `PAUSE`, `F9`, or `CTRL+SHIFT+F9`.

Precedence is:

1. explicit CLI value
2. saved configuration value
3. built-in default

`--show-config` prints the effective merged configuration.
`--save-config` validates the effective configuration and writes it back atomically.
`--config` can point to an alternate JSON file when you want to load or save settings somewhere else.

For example, `autotype --pause-key F9 --stop-key CTRL+SHIFT+F9 --save-config`
persists custom controls. CLI hotkey values apply only to that invocation unless
`--save-config` is also supplied.

## Input Normalization

- Plain strings stay plain strings.
- Existing `.txt` and `.docx` paths passed positionally are treated as files.
- DOCX paragraphs and tables are normalized into canonical text using newline and tab separators; merged cell continuations remain empty grid slots instead of duplicating anchor text.
- DOCX bulleted and numbered lists are normalized into canonical typed prefixes with consistent indentation; Word's default Symbol bullet is emitted as the portable Unicode bullet `U+2022`.
- `--target word` bypasses this lossy keyboard normalization and inserts the source DOCX as native Word content, preserving the fixture's native lists, tables, merges, styles, and supported formatting.
- Direct DOCX run formatting is preserved in the keyboard action stream using existing `KeyPress` toggles. Keyboard mode supports bold, italic, underline, all caps, small caps, superscript, and subscript; Hybrid has its separate COM run-formatting contract described above.
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

The three targets have intentionally different fidelity boundaries. Keyboard
mode linearizes DOCX structure and does not reproduce native tables or styles.
Word mode is fixture-focused rather than an arbitrary-DOCX or pixel-perfect
guarantee; custom-template/style conflict resolution and unsupported Word
objects are outside its contract.

Hybrid rejects or excludes inline images, non-empty headers/footers, nested or
merged tables, and multi-paragraph table cells. It supports only simple,
single-level built-in lists and one paragraph per supported table cell. It does
not reconstruct theme or automatic font colours, custom styles/templates,
advanced typography, sections/page setup, shapes, text boxes, comments,
tracked changes, macros, bookmarks, or arbitrary layout fidelity.

Hybrid corrections are bounded to the active text run. Delayed corrections,
word navigation, selection-based replacement, and corrections crossing run,
paragraph, or table-cell boundaries are not implemented. Hybrid does not use
the clipboard, mouse coordinates, ribbon automation, image recognition,
automatic saving, or automatic rollback. If it stops after a partial document
change, inspect the document and use Word's Undo (`Ctrl+Z`) manually.

Formatting shortcuts target desktop Word on Windows, require the target document to have focus, and may vary with Word version or keyboard layout. The `EQUALS` action represents the Windows `VK_OEM_PLUS` key for superscript, and `MINUS` represents `VK_OEM_MINUS` for subscript.

Those belong to future milestones.

## Roadmap

Shipped through M14.11.2:

- M1–M2: human behaviour, timing, typo, and correction foundations
- M7–M9: DOCX normalization, lists, and direct keyboard formatting
- M12–M13: native Word insertion and Word workflow documentation
- M14–M14.3: experimental Hybrid structures, focus safety, and measurement conversion
- M14.4–M14.7: table borders, list isolation/restarts, font typography, and character effects
- M14.9–M14.10.2: Hybrid bounded-local typos, owned-caret pause/resume, safe controls, and hook ABI fixes
- M14.11–M14.11.2: bounded-local multi-character corrections and persistent hotkey configuration

Future work:

- Optional M14.12: delayed/navigation-based Hybrid typo correction, subject to a safe bounded-caret design
- PPTX support remains future design work
