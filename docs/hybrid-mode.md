# Hybrid mode (experimental)

Hybrid mode is the experimental third AutoType target:

```text
DOCX source → Word COM creates supported structure → keyboard types text visibly
```

It is neither a clipboard paste nor proof that a human authored the document.
It is a constrained automation workflow for Windows and an already-running
desktop Microsoft Word instance.

## Prerequisites and safe workflow

1. Open Word normally, without Administrator elevation.
2. Open an editable, unprotected destination document and place a collapsed
   caret in its main document body, outside a table.
3. Open AutoType from a normal, non-Administrator terminal under the same user.
4. Keep Word as the foreground application throughout visible typing. Hybrid
   does not activate arbitrary windows when focus is lost.
5. Review the source without contacting Word:

   ```text
   autotype --file source.docx --target hybrid --dry-run
   ```

6. Run the experimental workflow:

   ```text
   autotype --file source.docx --target hybrid
   ```

If Word is open but attachment fails, a privilege-level mismatch is a likely
possibility. Reopen both Word and AutoType normally before retrying.

## What it supports

- normal paragraphs and built-in Heading styles where available;
- paragraph alignment, basic indentation, and exact point line spacing;
- direct run-level bold, italic, underline, font name, point size, explicit RGB
  colour, superscript, subscript, and strikethrough;
- single-level native bullet and numbered lists, with logical list isolation and
  numbered groups restarting at 1;
- rectangular, unmerged tables with one paragraph per cell, supported source
  widths, and deterministic visible borders;
- visible character-by-character typing with configured profile, speed, seed,
  pauses, `PAUSE`/`CTRL+PAUSE` controls, and persistent custom hotkeys;
- bounded-local immediate typo correction. A wrong local sequence may be
  corrected with local Backspace and retyping, but the correction remains inside
  the active Hybrid run.

## What it does not support

Hybrid rejects a source before modifying Word when it finds inline images,
non-empty headers/footers, nested or merged tables, or multi-paragraph table
cells. It does not promise custom styles/templates, theme or automatic font
colours, advanced typography, nested/custom lists, sections/page setup, shapes,
text boxes, comments, tracked changes, macros, bookmarks, or arbitrary-DOCX/
pixel-perfect fidelity.

Hybrid corrections do not use delayed navigation, word selection, or
selection-based replacement. Corrections cannot cross a run, paragraph, or
table-cell boundary. Those richer delayed/navigation-based corrections remain
optional future work and are not part of the shipped M14.11.2 behavior.

The default controls are `PAUSE` for pause/resume and `CTRL+PAUSE` for
emergency stop. Values can be persisted as `hotkeys.pause` and `hotkeys.stop`
in configuration schema version 2 or overridden per invocation with
`--pause-key` and `--stop-key`; precedence is CLI, then config, then defaults.
For laptops without a dedicated Pause/Break key, an example is `F9` and
`CTRL+SHIFT+F9`. Risky bindings remain allowed but produce a warning because
keyboard polling cannot distinguish matching generated input. F8 and F12 are
not the defaults because Word uses them for useful editing commands.

## Safety and recovery

Hybrid attaches only to Word already running. It never launches, closes, quits,
or saves Word; it does not modify global Word settings, use the clipboard,
automate Undo, use mouse coordinates, click the ribbon, or use image/UI
automation for targeting.

If COM fails, the destination changes, or Word loses foreground focus, Hybrid
stops before the next typing segment where possible and reports its last target.
The document may be partially modified. Inspect it and use Word's **Undo**
(`Ctrl+Z`) manually if needed; AutoType never performs automatic rollback.

Dry-run builds and summarizes the hybrid plan only. It does not import or
contact pywin32/COM and cannot change any Word document.
