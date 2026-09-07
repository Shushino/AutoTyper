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
- bold, italic, underline, paragraph alignment, basic indentation, and basic
  line spacing;
- single-level native bullet and numbered lists created through Word COM;
- rectangular, unmerged tables with one paragraph in each cell;
- visible character-by-character typing with configured profile, speed, and
  pauses.

Hybrid intentionally disables typo injection for now. Existing delayed typo
correction can move the Word caret beyond a bounded target, so it is not safe
until a cursor-local correction implementation is proven.

## What it does not support

Hybrid rejects a source before modifying Word when it finds inline images,
non-empty headers/footers, nested or merged tables, or multi-paragraph table
cells. It does not promise custom styles/templates, advanced font fidelity,
nested/custom lists, sections/page setup, shapes, text boxes, comments,
tracked changes, macros, bookmarks, or arbitrary-DOCX/pixel-perfect fidelity.

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
