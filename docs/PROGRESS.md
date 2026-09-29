# TallyCraft — Progress Log

Newest entries at the top. Each session records what was done, what's next, and
any open questions.

---

## 2026-09-28 — Session 10: CI actions off Node 20 (no release)

**Done**
- `release.yml` now uses the Node 24 majors: `actions/checkout@v7`,
  `actions/setup-python@v7`, `actions/upload-artifact@v7`,
  `softprops/action-gh-release@v3`. Their release notes list no breaking changes that
  affect how this workflow uses them.
- Committed as `277723e` and pushed to main. The workflow was started by hand
  (Run workflow, main): run #5 **succeeded with no annotations**. v0.5.0's run #4 had
  shown the "Node.js 20 is deprecated" warning.
  - Tests, build, exe self-tests, and artifact upload all passed. The tag check and
    Publish GitHub Release steps were skipped, as usual for a run that isn't from a tag.
    So `action-gh-release@v3` will first run for real on the next `v*` tag.
- No release tag: nothing in the app changed.
- 302 passed, 3 skipped locally (`.venv`).

**Next**
- Check the Publish step on the next release.

---

## 2026-09-28 — Session 9: v0.5.0 (packing list polish + Etsy import; released)

**Status: released as v0.5.0** at the user's request, before a real order was available.
v0.4.0 was released first (commit aac48ef).

> **Not yet verified: importing a real Etsy order.** Connect works with the user's real
> shop (Settings shows the shop name). Import from Etsy correctly reported "no open
> orders" with no errors. There was no real order to import, so matching real
> variations, the real address format, and printing an imported order's packing list
> are untested against live data. Everything is covered by mocked tests. The user will
> check with their next order.

**Part 1: packing list polish**
- **Enter in the shipping address** now always adds a line. The Text widget binds
  Return / keypad Enter / Shift+Return and stops the event there, and a hint under the
  label says so. The user's v0.4 record really did lose the address lines after the
  first, but it couldn't be reproduced with real key events (in isolation or in the
  app). As a guard, a one-line address with no comma asks "Is that the complete
  address?" before saving.
- **Display name** per piece (pieces table column, double-click to edit), saved in
  package presets only when set; old presets load unchanged and aren't "dirty".
  Packing lists use `{{ p.display_name }}` (display name or file name);
  `{{ p.name }}` stays the file name. Different names for the same file in two
  packages → the first wins, with a warning.
- **Show dimensions in** (Settings): Inches (default) / Millimeters / Each file's
  own units, for the size under each part picture.
- **Starter template:**
  - `{%tc %}` tag cells use 1 pt text and no margins.
  - The picture is 0.5 in tall (was 0.72). That gives 8 rows on page 1 and 13 on later
    pages (was 6 / 10).
  - **The sign-off never lands alone.** Keep-with-next was tried: LibreOffice ignores it
    on table rows, and with it on every row it moves the whole table to page 2. So the
    table's last row is now one full-width, unsplittable cell holding the totals (a
    nested one-row table), footnotes, Packed by, note, and shop record. After filling,
    TallyCraft moves the last part row into it and fixes its span and widths.
  - The note box is a one-cell table, because Word hid the paragraph border's sides
    inside a cell.
  - Verified with LibreOffice and Word at 8/19/20/21/22/26 parts, and with the
    user-style long part names.
- The user's edited template in the personal folder was only read, never touched.
  Only the bundled default changed.
- The "Show dimensions in" row first landed below Save/Cancel (grid row 13); fixed
  when the Settings rows were re-laid out.

**Part 2: import orders from Etsy** (`etsy.py`, `etsy_ui.py`; SPEC §12)
- Checked against Etsy's current docs and the OpenAPI spec:
  - OAuth 2.0 with PKCE S256 at `www.etsy.com/oauth/connect`; tokens at
    `api.etsy.com/v3/public/oauth/token`.
  - `x-api-key: keystring:shared_secret`; access tokens last 1 h, refresh tokens 90 days.
  - `getShopReceipts` with `was_paid` / `was_shipped` / `was_canceled`; variations come
    as `formatted_name` / `formatted_value`.
  - The docs say callbacks must be https. Etsy's own quick-start uses
    `http://localhost:3003/oauth/redirect`, so that's the default, and only a local http
    callback can be caught.
- Scopes are **`transactions_r shops_r`** (read-only). `address_r` is only for the
  user's own addresses; receipts carry the shipping address with `transactions_r`.
- **Keys and tokens** are in `etsy_connection.json` next to settings.json:
  - encrypted with Windows DPAPI;
  - git-ignored everywhere;
  - scrubbed from every message.
- Settings > Etsy: keystring, secret (masked), callback URL, Connect/Disconnect, the
  connected shop's name, and "Forget remembered matches".
- The Connect flow:
  1. A local `http.server` listener starts, and its `state` is checked.
  2. A "waiting" window with Cancel is shown, and the browser opens.
  3. The code is traded for tokens.
  4. `users/me` and `shops/{id}` give the shop name.
- Tokens refresh automatically, including once after a 401.
- **Import from Etsy…** in the Order section:
  - Network calls run on a background thread.
  - The picker lists paid, unshipped orders and previews each item's match.
  - Items match by variation value, case-insensitive (the title is tried last); a
    remembered choice wins.
  - A dialog lists unmatched items: choose a preset or Skip, with Remember.
  - The import replaces the order (asking first) and pre-fills Create Packing List
    for that order only. Calibration stays manual.
- Errors say in plain words what's wrong: offline, expired login (offers Settings),
  Etsy down (5xx), rate limit (429 with Retry-After), or permission. Manual entry keeps
  working.

**Testing**
- **289 passed, 3 skipped** (the opt-in real-conversion and live Etsy tests).
- New: `test_etsy.py` (fake transport: PKCE, listener, tokens on disk, refresh,
  errors, secrets never in messages, parsing, matching), `test_gui_etsy.py`, and the
  display-name / dimension / Enter-key / prefill tests.
- `tests/test_etsy_live.py` is opt-in (`TALLYCRAFT_ETSY_LIVE=1` +
  `TALLYCRAFT_ETSY_DIR`) and only lists real open orders.
- New exe check `--selftest-etsy`, which confirms ssl and DPAPI are bundled; CI runs
  it too. `win32crypt` was added as a hidden import.
- `dist\_exe\TallyCraft.exe` (v0.5.0, 41 MB) passes `--selftest`, `--selftest-docx`,
  `--selftest-pdf` (LibreOffice, 8 s), and `--selftest-etsy`.
- The first full rebuild was refused by build.py: `dist\TallyCraft\settings.json` had
  changed since the last build. The user moved it out, then the full rebuild ran:
  `dist\TallyCraft\` and `TallyCraft-v0.5.0-windows.zip`, 41 MB exe. All four
  self-tests pass on it.
- **Tk startup flake** ("Can't find a usable init.tcl" / "tcl_findLibrary"), about once
  in 5–9 full runs. The user chose option (b), pytest-rerunfailures:
  - The GUI test modules rerun a test up to twice, but only for that error (the
    `only_rerun` patterns in `TK_STARTUP_FLAKE`).
  - A scratch check showed other failures are not rerun.
  - `_tk_available` retries too, so a flake can't silently skip the module.
  - Six full runs in a row were clean.
- The callback URL registered on Etsy is exactly `http://localhost:3003/oauth/redirect`
  (the user confirmed this), which is the default.
- No Word or LibreOffice processes were left running.

**Fixes after the first v0.5 test (2026-09-28)**
- **`KeyError: 'popdown'`**:
  - Opening the Units dropdown logged this error. The editor's focus check called
    `focus_get()`, and that can't look up Tk's dropdown list.
  - It now uses `gui.focused_path()` (Tk's raw focus path). That was the only
    `focus_get` in the code.
  - The test reproduces the error with the old line, and passes with the fix.
- **"Units" → "File units"**, with a tooltip on the heading and cells.
- The pieces table's Bounding Box and Area, and the preview, now convert to "Show
  dimensions in" (default inches). The user's LightBurn file shows
  14.500 × 14.250 in while its File units stay Millimeters.
- **Size sanity Warning** when changed File units make the longest side
  > 100 in or < 0.05 in: "At this unit the piece would be … Is that right?"
- 302 tests pass, 3 opt-in tests skipped.

**Testing that never touches the desktop (user request, 2026-09-28)**
- GUI tests used to show windows and grab focus. `tests/conftest.py`
  `no_windows_on_screen` (autouse) now:
  - withdraws every Tk root and toplevel as it's created;
  - turns deiconify/lift/tkraise/focus_force/grab into no-ops;
  - replaces Tk's own dialogs with errors (an unanswered messagebox or file dialog fails
    instead of appearing), and does the same for simpledialog, `webbrowser.open`, and
    `os.startfile`;
  - stubs `ttk::combobox::Post`, so dropdown lists never open.
- The app fixture fails a test if `wm stackorder` shows any mapped window.
- Key presses are tested by running the widget's own binding script (`fire_binding`),
  and in-place editors get a fake cell box. The preview draws at its requested size
  when not on screen (`PiecePreview._size`).
- New `gui` marker: `pytest -m "not gui"` (about 9 s) for day-to-day work, then the full
  suite once before reporting done. CLAUDE.md has the standing rule.
- Self-tests and sample renders open nothing visible: Word hidden, LibreOffice
  headless. Last session's screenshot script (which showed dialogs) won't be used
  again.
- Full suite: 302 passed, 3 opt-in skipped (1 automatic rerun of the Tk startup flake).

**Next**
1. With the next real Etsy order: Import from Etsy, check the matching, address, and
   order number, calibrate, and print the packing list. Report anything odd (for
   example variation names that don't match presets).
2. Move `tallycraft_error.log` out of `dist\TallyCraft\` before the next local full
   rebuild (build.py refuses while it's there). The release zip is built by CI and
   isn't affected.

---

## 2026-09-28 — Sessions 7–8: v0.4.0 (LightBurn/engrave + Word-template packing lists; released)

**Status: released as v0.4.0 (commit aac48ef).**

**Part 1: LightBurn DXF support and the engrave color rule** (`dxf_geometry.py`)
- Files are read with `ezdxf.readfile` first. `recover` is used only when a file is damaged,
  because it drops every entity of LightBurn exports (they reuse entity handles). The
  resulting ezdxf log noise is silenced.
- **Black = cut, every other color = engrave.** Colors are resolved as true color → ACI →
  BYLAYER (layer color, or the block reference's layer for layer "0") → BYBLOCK (the parent
  INSERT's color).
  - Cut colors are editable in Settings (default ACI 7 and RGB 0,0,0).
  - Engrave geometry is never stitched, never a hole, and never an error. It's drawn in the
    preview and in pictures.
  - Each row gets an Info note: "N engrave-only items drawn but not counted in weight."
  - A file with no black geometry gets an Error: "No cut (black) lines found. Check the colors
    in this file."
- **Units:** when a file doesn't state units, it's assumed to be mm (with an Info note) if it's
  a LightBurn export (R12 with `Layer_N` layers) or over 60 units across.
- Verification:
  - Across all 305 of the user's real DXFs, 300 are identical to v0.3. The other 5 are unitless
    files now assumed to be mm, all plausibly mm-sized (4–43 in as mm, versus 8–90 ft as inches).
  - The LightBurn regression file is at `tests/fixtures_private/` (copied byte-identical from
    `D:\TallyCraft - Personal Use\`, git-ignored because the repo is public). It gives
    368.30 × 361.95 mm, 79,272.7 mm² (122.87 in²), 22 cutouts totaling 20.67 in², and 151
    engrave items. A synthetic LightBurn-style file with reused handles covers CI.

**Part 2: packing lists from an editable Word template**
- docxtpl fills `templates/packing_list_template.docx`.
  - The starter template is generated by `tools/make_template.py` and bundled in the exe:
    Calibri, a clear size hierarchy, a repeating header row, rows that don't split, and
    "Page X of Y" in the footer.
  - After filling, TallyCraft restores the template's column widths (docxtpl makes every column
    equal), finding the parts table by its Alt Text.
  - Kit columns: full names → "Kit N" + legend → one per package.
  - Part pictures are 400 DPI PNGs with engrave lines drawn lighter.
- **One field list** (`FIELDS`) drives `docs/TEMPLATE_FIELDS.md`, README.txt, and Help > Packing
  List Template Fields. Tests fail if they drift.
- **Validation:** problems that break the list block it; unrecognized placeholders, including
  typos like `p.xxx` inside loops, give a warning.
- **Word-validity repair:** Word calls a document "corrupted" when a table cell has no
  paragraph. That happened when `{%p if %}` blocks emptied a cell (no order # and no date).
  Every generated file is now repaired, and the starter template keeps a paragraph there.
- **Templates:** the user's file is never replaced. The app refreshes only `templates/_default/`.
  Restore default template writes a new copy.
- Output is `.json` + `.docx` + `.pdf`. Re-print uses the current template, writes
  "(reprint …)" files, and keeps the original PDF.
- **PDF engines** (Settings > "Make PDFs with": Automatic / Word / LibreOffice):
  - LibreOffice runs headless with a throwaway profile, a 120 s timeout, and tree-kill on
    timeout.
  - LibreOffice gets `SAL_DISABLE_PRINTERLIST` / `SAL_DISABLE_DEFAULTPRINTER`, set for the child
    process only.
  - Conversion runs in a background thread with a progress window.
  - On failure the .docx is kept and the message says why.
- **Timing, same 3-page list, from source:** LibreOffice **2.9 s**, Word **52.6 s**. From the
  packaged exe: 7 s / 56 s. Both are US Letter and visually equivalent. Word's slowness is it
  querying the user's network HP printer, and there's no fix without changing system settings.
- reportlab was removed. The exe is now ~41 MB (docxtpl, lxml, pywin32).

**Incidents this version (recorded so they're not repeated):**
- *Default printer:* testing a Word speed-up (pointing Word at "Microsoft Print to PDF")
  changed the Windows default printer, because Word writes its printer back when it quits.
  - It was restored, with the registry and spooler verified.
  - The approach was removed.
  - A new CLAUDE.md rule: never change system settings without asking.
- *Orphaned Word processes:* 4 hidden `WINWORD.EXE /Automation` instances were left by failed
  test scripts; I closed them. A new CLAUDE.md rule: check for and close leftovers before
  finishing.
- *Build safety:* `build.py` now refuses to delete any file in `dist/TallyCraft/` that it didn't
  create or that was changed. The earlier check would have deleted a DXF the user had put
  there.

**Testing**
- 226 tests pass, and 2 opt-in real-conversion tests are skipped by default
  (`TALLYCRAFT_REAL_CONVERSION=1`).
- New test files: `test_engrave_units.py`, `test_packing_docx.py`, `test_pdf_convert.py`,
  `test_gui_packing.py`. The GUI tests cover the packing flow, Settings, re-print, and the
  engrave lines in the preview. Opening the Tk window is retried for its intermittent
  "init.tcl" startup error on Windows.
- **No test launches Word or LibreOffice.** Conversion is mocked, and the GUI tests make any
  real launch fail.
- The exe self-tests (`--selftest`, `--selftest-docx`, `--selftest-pdf`) pass on the packaged
  exe. CI runs the first two.
- After every run: no leftover Word/LibreOffice processes, and the default printer is unchanged.

**Next**
1. ~~Rebuild `dist\TallyCraft\`~~ — done (2026-09-27 20:01; exe 41 MB). All 8 leftover files were moved to
   `backups/` (byte-identical to the personal folder). The self-tests pass on that exe: DXF,
   docx, and PDF via LibreOffice in 5 s. No leftover processes, and the printer is unchanged.
2. The user prints a test packing list.
3. Commit, push, and tag `v0.4.0` on the user's go-ahead. Decide whether the real LightBurn file
   should ever be committed (currently no, since the repo is public).

---

## 2026-09-28 — Session 6: packing lists (still v0.3.0, unreleased)

**Design:**
- The JSON **record is the source of truth**. The PDF is always rendered from the record,
  on creation and on re-print, in reportlab's invariant mode.
- A re-print is therefore byte-identical and never reads DXF files.
- The record stores part pictures (RDP-simplified loops) and the logo (base64).

**Done**
- `packing.py` (pure): `build_record`, `validate_record`, `picture_from_parsed` +
  `simplify` (RDP), `items_ordered`, `default_filename`, `parse_order_date`, logo encoding.
- `packing_pdf.py`: US Letter portrait.
  - Header: logo, shop, customer block, items, prominent total, unmeasured warning.
  - Parts table:
    - vector pictures, each scaled to fit its own cell, with dimensions underneath;
    - kit columns that are full → "Kit N" + legend → per package → omitted, so the table
      never exceeds the page;
    - a totals row, a repeating header, and "Page X of Y" plus the order # on every page.
  - Sign-off, note, and a small-print shop record on the last page.
- `packing_ui.py`: Create dialog (name required, date validated, live file name), a
  read-only viewer with Re-print, and a Settings dialog (shop name, logo with a readable
  PNG/JPG check, default note).
- GUI:
  - Create Packing List… button and File menu entries, enabled only while results are
    current.
  - Snapshot at Calculate.
  - The skipped-parts confirmation.
  - The calibration preset name is recorded only if section 2 still matches it.
  - Missing logo → left out with a note. PDF write failure → record kept for re-print.
- Storage: `packing_lists/` (unique names, never overwritten) and new settings `shop_name`,
  `logo_path`, `default_note`. `build.py` creates the folder and protects it; new
  `--exe-only`. Hidden `--selftest-pdf`, added to CI.
- `reportlab` + `pillow` are now runtime requirements. The exe grew from 28 MB to 36 MB.
- Verification:
  - 149 unit tests pass (21 new in `test_packing.py`, including the byte-identical re-print
    after a JSON round trip).
  - New GUI test on copies of real DXFs: 30 checks, all pass, including a byte-identical
    re-print after deleting a DXF the list used. Earlier GUI suites all pass.
  - Sample PDFs were rendered from real files and reviewed: a 3-page, 3-kit order with an
    unmeasured part; 8 kits (short headers); and 15 kits (per-package). That review led to:
    - the per-package fallback;
    - part names without ".DXF";
    - a grammar fix for the singular case;
    - readable timestamps;
    - fitting headers in the viewer.
  - An exe built into scratch (the user's copies were running, so they weren't touched)
    rendered a correct packing list via `--selftest-pdf`.

**Next**
1. User tries a real packing list, then prints one to check it on paper.
2. Commit, push, and tag `v0.3.0` (orders + packing lists) on the user's go-ahead.
3. Later: Etsy integration.

---

## 2026-09-28 — Session 5: multi-package orders (v0.3.0, unreleased)

Built in the requested order, verifying each step before moving on.

1. **Data model** (`order.py`, pure):
   - `Package` holds rows, name, `preset_name`, quantity, and a baseline.
     "Unsaved changes" is derived from the baseline, so undoing an edit clears it.
   - `Order` provides `with_blank_package`, `kit_labels`, `find_preset`, `units_conflicts`,
     and `all_rows`.
   - The package preset format is unchanged; a v0.1 preset loads byte-for-byte as before.
   - Startup: one blank package, "New Package 1".
2. **Order section** above the pieces table:
   - Buttons: Add Package from Preset… / New Blank Package / Remove / Save Order… /
     Load Order… (also in the File menu).
   - Columns: Package, Quantity (editable), and Status (OK, Empty, N pieces with errors,
     warnings, units conflicts, unsaved changes).
   - Section 1 is scoped to the selected package: `rows` and `_row_order` became properties,
     so the existing pieces-table code is unchanged.
   - Adding a preset that's already in the order increases its quantity, with a message.
   - Adding a preset replaces the untouched startup blank, so a single sale takes the same
     clicks as before.
   - The reference-piece dropdown spans every package. Duplicate names get " — package".
   - Save Package Preset saves the selected package (prompting for the Etsy variation name),
     links and renames it, and refuses names already used in the order.
3. **Merged results:**
   - One row per unique DXF (normalized, case-insensitive path).
   - One count column per individual kit ("Name (k of n)"), with "—" when unused.
   - Then Total Count / Weight per piece / Item Total.
   - Kit columns are sized to their headings and remember user widths by title.
   - A piece is skipped entirely if it has an Error in any package, conflicting Units, or
     differing areas.
   - Sorting (kit columns numeric), the pinned skipped rows, the Incomplete badge, the
     skipped notice, and Copy Results (with kit columns) all still work.
4. **Save / Load Order:**
   - Saved to `order_presets/`, with pieces embedded so unsaved edits are kept.
   - On load, unsaved changes are recomputed against the preset on disk.
   - Files modified since the order was saved get a warning, and missing files an error,
     with a status-bar summary.
- Also:
  - `PieceRow.load(saved_what=…)`, so the warning says "this order" vs "this preset".
  - `build.py` creates `order_presets/`; root `.gitignore` covers it.
  - README.txt has a new "Packages and orders" section plus the Etsy naming note;
    README.md is updated; SPEC §4.0, §6.1, §6.3, and §7 are updated.
- Verification:
  - 128 unit tests pass (21 new in `test_order.py`).
  - New GUI test on copies of real DXFs: 45 checks, all pass. It covers the single-sale
    flow (same total as before), duplicate→quantity, scoping, unsaved marker and undo,
    presets untouched on disk, merged per-kit counts, the total across kits, conflicts,
    errors, sorting, widths, Copy, save/load with modified and missing files, and removing
    the last package.
  - All earlier GUI suites pass. Their position-based column lookups were updated for the
    new kit column.
  - Screenshot reviewed. That led to one fix: kit columns now fit their headings.

**Incident: a build deleted test data in `dist\TallyCraft\`.**
- `build.py` wiped `dist\TallyCraft\` before discovering that the user had TallyCraft 0.2.0
  running from there (the exe was locked).
- Everything else in that folder was deleted: README, settings, and the preset folders,
  including any presets the user saved while testing 0.2.0. This can't be recovered, since
  the files didn't go to the Recycle Bin.
- The user's repo-root copy was not affected.
- Fix: `build.py` now checks before deleting anything, both before and after PyInstaller.
  It stops with an explanation if the exe is running or if the folder holds presets, orders,
  or a non-default `settings.json`. Documented in BUILDING.md.
- The 0.3.0 exe was verified from `dist\_exe\` (its self-test passed). `dist\TallyCraft\`
  will be reassembled once the user closes the running copy.

**Next**
1. User tries a real multi-package order.
2. Commit, push, and tag `v0.3.0` on the user's go-ahead.
3. Later: Etsy integration that matches order variations to package presets by name.

---

## 2026-09-27 — Session 4: reference-piece calibration + main divider

These changes are still part of the unreleased v0.2.0.

**Done**
1. **Reference piece calibration** (the new default method). Section 2 was renamed
   "Calibration" and has a Method selector (Reference piece / Control sample); the last-used
   method is saved in `settings.json` as `calibration_mode`.
   - `calibration.py`: `ReferencePiece`, `SavedReference`, `validate_reference`,
     `parse_positive_int`, `describe`. The ratio is
     `total_g / (qty × net area cm²)`, using the row's own area and Units.
   - Validation blocks Calculate with a clear reason when:
     - no piece is chosen;
     - the chosen piece was removed from the table (the choice is cleared and a note explains
       why);
     - the piece's row has an Error or Unknown units;
     - the quantity isn't a whole number ≥ 1, or the weight isn't a number > 0.
   - If the reference row has a Warning, it's added to the existing pre-calculate
     confirmation.
   - Stale triggers: changing the piece, quantity, weight, or method, or the reference row's
     Units or area. The live ratio also updates when the reference row changes.
   - Presets (`storage.save_reference` / `load_control`):
     - Each preset now stores its method. Reference presets also store the path and name,
       quantity, weight, the derived g/cm², and the piece's area.
     - If the file is in the table, the preset re-links to it and notes if its area has
       changed since the preset was saved.
     - Otherwise it falls back to the saved area/ratio, with a note, and the quantity and
       weight stay editable.
     - Old v0.1.0 control presets (no `method` key) load unchanged.
   - My additions:
     - The reference re-links automatically when a package reload still contains its file.
     - Copy Results ends with a "Calibration: …" line.
     - UI text now says "Calibration preset"; the folder is still `control_presets/`.
2. **Main divider:** the top half (pieces) and bottom half (calibration + results) are now
   split by a draggable divider. Its position is saved as a fraction of height in
   `settings.json` (`main_split`, clamped 0.15–0.85) and restored on startup.
- Verification:
  - 107 unit tests pass (new: `test_calibration.py`, covering math, agreement with the
    control-sample method, units and holes, every validation case, preset round trips,
    legacy presets, bad presets, and settings sanitizing).
  - The new scripted GUI test (42 checks) and the earlier GUI suites (45 checks, plus the
    session 2 smoke test) all pass. The earlier suites were updated to pick Control sample
    mode, since Reference piece is now the default.
  - The rebuilt exe passes its self-test. The screenshot was reviewed.

**Released:** v0.2.0 (sessions 2–4) was committed as `fcc6354`, tagged, and published by CI:
https://github.com/jaerixon/TallyCraft/releases/tag/v0.2.0 (`TallyCraft-v0.2.0-windows.zip`;
tests and the exe self-test passed).

**Next**
1. User tries reference-piece calibration with a real weighing.
2. Housekeeping: bump the GitHub Actions versions off Node 20 (still only a warning).

---

## 2026-09-27 — Session 3: usability (column resizing, sorting, preview width, text size)

These changes are still part of the unreleased v0.2.0, since session 2 wasn't committed or
tagged yet.

**Done**
1. **Results columns snapped back.** Cause, reproduced with simulated mouse drags in the real
   app: Tk's Treeview only resizes a dragged column when a *stretchable* column lies to its
   right. Results had only File Name stretchable, with nothing stretchable after it. The pieces
   table had the same hidden limit on its right-hand columns (Area, Date Modified, Status).
   - Fix: all real columns are `stretch=False`, plus a blank stretchable filler column at the
     end of each table.
   - Every column in both tables now resizes, and widths survive relayout, re-Calculate, and
     sorting.
   - Also added horizontal scrollbars. Without them, large text pushed the Status column off
     the table with no way to reach it (found in the screenshot review).
2. **Sorting** (`table_sort.py`, 6 unit tests):
   - Click a header to sort, click again to reverse; the sorted header shows ▲ or ▼.
   - Pieces: Count, File Name, Date Modified (real timestamp), Status (Errors first).
     Results: all four columns, numeric where relevant; skipped rows always at the bottom.
   - Display only: the app keeps rows in import order (`_row_order`), which calculation and
     presets use. Selection and the preview follow the row, and results are never marked stale.
3. **Details | preview divider:** a horizontal `ttk.PanedWindow`; the preview redraws at its
   new width.
4. **Text size:** View menu with Larger/Smaller/Reset and Ctrl+= / Ctrl+- / Ctrl+0.
   - Named fonts cover both tables, the details pane, and the Results footer. The totals stay
     15/9 of the table text size.
   - Row height and column widths scale with the text.
   - Saved as `settings.json` → `text_scale` (sanitized on load: clamped to 0.8–2.5, junk
     falls back to 1.0) and restored on startup.
- Verification: 73 unit tests pass. A scripted GUI test (45 checks, all pass) uses real mouse
  drags on every column of both tables, and covers sort orders and arrows, preset/calculation
  order, stale state, selection/preview, the divider, and text keys and persistence.
  Screenshots at 125% and 160% were reviewed.

**Next**
1. User tries the build, especially column dragging and text sizes on their display.
2. Commit, push, and tag `v0.2.0` once the user gives the go-ahead.

---

## 2026-09-27 — Session 2: v0.2.0 (splines, skip-on-error, preview)

**Requested by the user**
1. Support SPLINE/ELLIPSE instead of raising an error. Four real files failed with this error:
   Main Box - Front Panel, Main Box - Tunnel Side Panel, Ramp - Step, Tunnel - Entrance Arch.
2. Calculate skips rows that have Errors instead of being blocked by them, and marks the total
   as incomplete.
3. DXF preview panel.

**Done**
- `dxf_geometry.py`: splines (including rational/NURBS) and ellipses are flattened with ezdxf
  at 1e-5 × curve size, then fed into the existing stitcher. Closed curves become their own
  loop. The stitcher now returns a `StitchResult` that includes open chains and error points.
  `ParsedPiece` gained `loop_depths`, `open_chains`, and `error_points`, which the preview uses.
- Tolerance check on real files: spline endpoints meet their neighbors within ≤ 2e-11 in., so
  the 1e-4 stitch tolerance was not loosened. Areas agree with a 1000× finer flattening to
  within 1.2e-6.
- All 8 spline files (the 4 XL files plus the Mini versions) now parse. The other ~45 real
  files still produce identical areas (regression check).
  - XL Front Panel v2 144.4901 in², XL Tunnel Side Panel v2 160.4236, XL Ramp Step v3 3.7458,
    XL Entrance Arch 21.0140.
- `calc.py`: `SkippedLine`, `CalcResult.skipped/incomplete/incomplete_note`, and
  `results_as_text()`.
- GUI:
  - Error rows are skipped. Calculate is blocked only when every row has an Error or the
    control values are invalid.
  - After calculating, a notice lists each skipped file and why.
  - Results show skipped rows as "Skipped - not included", with a red "⚠ Incomplete: N files
    skipped" badge beside the total. Copy Results carries the same marker.
- `preview.py`: Canvas preview beside the details pane, with a draggable divider.
  - Drawn from the parsed loops: solid outline in brown with a wood fill, holes in blue,
    unclosed runs as dashed orange lines, red rings at problem points.
  - Shows dimensions and a legend. Pieces that failed show "No preview available" plus the
    reason.
  - Redraws on resize and on a Units change.
- Row model: files with no readable geometry no longer show "units unknown" as their main
  error; the parser's own reason comes first.
- Tests: 61 pass, including analytic spline/ellipse areas (parabola segment, exact NURBS
  circle, πab), splines joining splines, and skip/incomplete logic.
- GUI smoke test on real files, with screenshots checked. Rebuilt exe; its self-test on the
  4 real spline files passed.
- Version bumped to 0.2.0; SPEC.md and both READMEs updated.

**Next**
1. User re-imports the 4 files in the app to confirm.
2. Commit and push, then tag `v0.2.0` to publish the release (waiting on the user's go-ahead).

---

## 2026-09-27 — Session 1: setup + v0.1.0 implementation

**Decisions made with the user**
- Thickness is dropped completely. The user updated the original prompt to match.
- Warnings don't block Calculate. Calculate shows one confirmation dialog first. Errors do block it.
- Layers: geometry on layers that are off or frozen is skipped, as is geometry on any layer
  named in `settings.json` → `ignored_layer_names` (default CONSTRUCTION, DEFPOINTS). Skipped
  geometry gets an Info note.
- GitHub: `gh` installed via winget. The repo will be the public `jaerixon/TallyCraft`.

**Done**
- Repo skeleton: `.gitignore`, MIT `LICENSE`, root `README.md`, `docs/` (SPEC, PROGRESS,
  BUILDING, original prompt), `CLAUDE.md`.
- `dxf_geometry.py`: LINE/ARC/CIRCLE stitching, LWPOLYLINE/POLYLINE with bulges, INSERT
  expansion, mirrored-arc (OCS) handling, duplicate removal, errors for gaps and junctions with
  locations, unsupported-type errors, multiple-shape warning (even-odd area), sanity checks,
  file-level errors.
- `pieces.py` row model: unit override treated as a reinterpretation of the file's numbers,
  unknown units block Calculate, "modified since preset" warning.
- `calc.py`: cm²-normalized math, lb/oz conversion with carry, control validation.
- `storage.py`: package and control presets, settings, atomic writes, corrupt-file handling.
- `gui.py`: three-section Tkinter UI with in-cell Count/Units editing, status tooltips, a
  details pane, stale-results indicator, Copy Results, and a top-level error handler that
  writes `tallycraft_error.log`.
- Icon generator (`tools/make_icon.py`) and `assets/tallycraft.ico`/`.png`.
- `build.py`: PyInstaller onefile build that assembles `dist/TallyCraft/` and zips it.
  Hidden `--selftest` mode for verifying packaged exes.
- `.github/workflows/release.yml`: on a `v*` tag it runs tests, builds, self-tests the exe, and
  publishes the release with the zip attached.
- Verification: 50 pytest tests pass. A scripted GUI smoke test (import, fix errors, calculate,
  save/load presets, default preset on restart) passed and the numbers were checked by hand.
  The packaged exe self-test passed and the GUI launches from the exe.

**Next**
1. ~~Create the repo and push~~. Done: https://github.com/jaerixon/TallyCraft. The `v0.1.0`
   release was built by CI; the exe self-test passed and the zip is attached.
2. Validate against one of the user's real DXF exports. The original prompt says the algorithm
   was prototyped against a real file; compare that file's area to the prototype's number.
3. Collect real-use feedback on the UI.

**Open questions**
- None pending.
- Housekeeping: GitHub warns that the actions in `release.yml` target Node 20, which is
  deprecated. They still run for now. Bump the action versions when newer majors come out.
