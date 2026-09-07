# Word mode

Word mode is an opt-in Windows workflow for inserting a source `.docx` with
Microsoft Word's native `Selection.InsertFile` operation. It is separate from
the default keyboard target: it does not type character-by-character, apply
human timing, simulate typos, or use the keyboard behaviour pipeline.

## Normal-privilege workflow

1. Close any stale Word windows and open Microsoft Word normally, without
   choosing **Run as administrator**.
2. Open or create the destination document in that Word instance. Make sure it
   is editable and unprotected.
3. Place a collapsed caret in the main document body, outside a table. Do not
   leave text selected, and do not place the caret in a header, footer, text
   box, or other story.
4. Open the terminal normally as the same Windows user, also without
   Administrator elevation.
5. Validate without touching Word:

   ```text
   autotype --file source.docx --target word --dry-run
   ```

6. Run the native insertion:

   ```text
   autotype --file source.docx --target word
   ```

Word and AutoTyper should normally run at the same privilege level. If Word is
already open but attachment fails, a privilege-level mismatch is a likely
troubleshooting possibility; reopen both normally before trying again.

## What the modes do

`keyboard` remains the default and is portable to supported keyboard hosts. It
normalizes DOCX content into a lossy text/action stream, including linearized
tables, then applies timing and optional typo behaviour.

`word` validates an existing `.docx`, attaches only to an already-running Word
instance, and lets Word reproduce native paragraphs, lists, tables, merged
cells, and supported styles. Keyboard-only options remain accepted for CLI
compatibility but are ignored. Word mode never launches, closes, quits, or
automatically saves Word; it does not change AutoCorrect or AutoFormat and
does not use the clipboard.

Dry-run validates the source package and prints the planned native operation.
It does not import or contact COM/pywin32 and cannot change a Word document.

## Recovery and limits

`InsertFile` is a native Word operation. If Word reports an insertion failure,
content may have been partially inserted. Use Word's **Undo** (`Ctrl+Z`); AutoTyper
does not attempt an automatic rollback.

The fidelity contract is focused on the supplied capability fixture and common
native Word structures. It is not a pixel-perfect or arbitrary-DOCX guarantee.
Custom-template or custom-style conflicts are not resolved. Images, headers,
footers, sections, comments, tracked changes, macros, shapes, bookmarks, and
other excluded objects are outside this milestone.
