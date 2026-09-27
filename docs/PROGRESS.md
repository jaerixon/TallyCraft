# TallyCraft — Progress Log

Newest entries at the top. Each session records what was done, what's next, and
any open questions.

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

**Next**
1. User tries reference-piece calibration with a real weighing.
2. Commit, push, and tag `v0.2.0` once the user gives the go-ahead.

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
