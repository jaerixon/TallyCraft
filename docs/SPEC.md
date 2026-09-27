# TallyCraft — Design Spec

Living design spec. Supersedes `TallyCraftPrompt.md` (the original request,
kept for history). Items marked **[decision]** were resolved during
development rather than stated in the original prompt — revisit freely.

---

## 1. Purpose

A small laser-cutting business sells plywood products shipped as kits of flat
pieces. TallyCraft takes the DXF file for each piece, computes its net surface
area, and — using the grams-per-area ratio of a small **control sample** cut
from the same plywood stock — computes each piece's weight, per-item totals,
and the total package weight (grams and lb/oz).

**Why weight-per-area:** plywood thickness varies sheet to sheet, but a
thicker spot is also a heavier spot, so a measured grams-per-area ratio holds
regardless. **Thickness is not collected anywhere in the app and no density
figure is shown.**

## 2. Tech stack

| Concern | Choice |
|---|---|
| Language | Python (CI builds with 3.12) |
| GUI | Tkinter + ttk |
| DXF parsing | `ezdxf` |
| Presets / settings | Plain JSON files |
| Packaging | PyInstaller `--onefile`, custom icon |
| Icon | Generated with Pillow (tally marks `\|\|\|\|` + slash beside an outlined crate) → `.ico` |

## 3. Distributed folder layout

```
TallyCraft/
  TallyCraft.exe
  package_presets/     one JSON file per package preset
  control_presets/     one JSON file per control preset
  settings.json        app-level settings
  README.txt           plain-language guide
```

The app locates these relative to the **exe's folder** when frozen, or the
repo's `portable/` folder when run from source **[decision]** (gitignored).
Missing folders / settings file are created on startup.

### settings.json

```json
{
  "default_control_preset": "DixiePly 120526",
  "ignored_layer_names": ["CONSTRUCTION", "DEFPOINTS"],
  "last_import_dir": "C:/...",
  "text_scale": 1.0,
  "calibration_mode": "reference",
  "main_split": 0.62
}
```

- `default_control_preset` — auto-loaded on startup if set. If the named
  preset no longer exists, show a non-blocking notice and continue.
- `ignored_layer_names` — case-insensitive layer names whose geometry is
  skipped (see §5.1). **[decision, user-approved]**
- `last_import_dir` — convenience only **[decision]**.
- `text_scale` — the View > text size (1.0 = default), restored on startup.
  It is clamped to 0.8–2.5; an unusable value falls back to 1.0.
- `calibration_mode` — last-used section 2 method, `"reference"` (default)
  or `"control"`. Anything else falls back to `"reference"`.
- `main_split` — position of the top/bottom window divider, stored as a
  fraction of the divider area's height (so it adapts to window size),
  clamped to 0.15–0.85. `null` means the default split (3:2). Saved when the
  divider is released and restored on startup.
- `default_control_preset` can name either kind of calibration preset (the
  key name is kept for compatibility).
- Unknown keys are preserved; a corrupt settings file is reported, backed up
  as `settings.json.bak`, and replaced with defaults (never a crash).

## 4. Screens / UI

One main window, three sections **[decision]**. A **draggable horizontal
divider** separates the upper area (section 1: pieces table plus
details/preview) from the lower area (sections 2 and 3), so either half can
get more height. Its position is remembered (`main_split`).

1. **Package (pieces table)** — toolbar: *Import DXF…*, *Remove Selected*,
   *Clear*, *Save Package Preset…*, *Load Package Preset…*. Table columns:

   | Column | Behavior |
   |---|---|
   | Count | Editable integer ≥ 1, default 1. Multiplier only; never affects area. |
   | File Name | Base name; full path in tooltip/details. |
   | Units | Editable dropdown: Inches / Millimeters / Unknown. Initially from `$INSUNITS`. |
   | Bounding Box (W × H) | In the row's current unit. |
   | Area | Net area in in² or mm² per the row's unit. |
   | Date Modified | File's OS mtime, `YYYY-MM-DD HH:MM`. |
   | Status | OK / Info / Warning / Error. Hover tooltip + a details pane below the table showing all messages for the selected row. |

   Also: *Re-read Selected* (re-parses files from disk, keeping Count and any
   Units override — the way to clear a "modified since preset" warning), and
   importing a file already in the table is skipped with a note ("change its
   Count instead") **[decision]**.

   Editing is done by double-clicking a Count or Units cell (in-place
   Spinbox/Combobox). **Recalculation is automatic** on every edit
   **[decision]** — no separate Recalculate button.

   **Preview panel.** It sits next to the details pane. A horizontal
   draggable divider sits between the table and the details/preview strip,
   and a **vertical** draggable divider sits between the details pane and the
   preview, to trade width between them. Selecting one row draws that
   piece on a Tkinter Canvas (no extra dependencies):
   - Drawn from the **same** `ParsedPiece.loops` / `loop_depths` /
     `open_chains` / `error_points` the area was computed from — no separate
     rendering path, so it shows exactly what TallyCraft measured.
   - Scaled to fit, aspect ratio kept, Y flipped (DXF y-up → canvas y-down).
   - Solid loops (even nesting depth: the outer boundary, and any islands)
     are brown outlines with a plywood fill; holes (odd depth) are blue
     outlines. Runs that never closed are dashed orange; loose ends and bad
     junctions get red ring markers. A small legend lists what is shown.
   - If the piece has no valid area (any geometry Error), loops are drawn
     as outlines only, with no fill, so nothing looks "measured" **[decision]**.
   - Bounding-box dimensions (in the row's current unit, or "units unknown")
     under the drawing.
   - Rows with no geometry at all (missing/corrupt/empty file) show
     "No preview available" plus the reason.
   - Redraws on resize (including either divider) and whenever the row
     changes. For example, a Units change keeps the same shape but updates
     the dimension labels. Multi-row selection shows a hint.

2. **Calibration — plywood batch** (renamed from "Control sample", v0.2).
   A **Method** selector offers *Reference piece* (the default) or *Control
   sample*. The last-used method is remembered (`calibration_mode`), and only
   the chosen method's inputs are shown. Both methods show a live ratio in
   g/cm² and g/in² when their inputs are valid, and flag invalid fields as you
   type. Logic lives in `calibration.py` (pure and unit-tested).

   **Reference piece.** Calibrates from pieces already cut from the imported
   list.
   - *Piece*: a dropdown of the files currently in the pieces table, in import
     order. Duplicate file names get their folder name appended.
   - *Quantity weighed*: a whole number ≥ 1.
   - *Total weight (g)*: accepts ≥ 3 decimal places.
   - Tip under the inputs: "For best accuracy, weigh several pieces or a
     large piece."
   - The ratio is `total_weight_g / (quantity × piece_net_area_cm2)`, using
     that row's net area and current Units, exactly as the row's own weight
     is computed.
   - A reference row with an Error or Unknown units can't be used. The reason
     is shown live in section 2 and blocks Calculate.
   - If the reference file is removed from the table, the choice is cleared
     and a note (plus a status-bar message) says why. Calculate then explains
     the same thing. If the table changes but still contains the same file
     (for example a package reload), the reference is **re-linked** to it
     automatically **[decision]**.
   - Stale triggers: changing the piece, quantity, weight, or method, or the
     reference row's Units or area (such as a re-read), marks results stale.
     A Units or area change also updates the live ratio.

   **Control sample.** Behaves exactly as before: Length and Width (with a
   shared Inches/mm toggle) plus Weight (g).

   **Calibration presets.** Controls: *Calibration preset* dropdown, *Load*,
   *Save Calibration Preset…*, and the checkbox *Use this preset as default on
   startup*. Presets are stored in `control_presets/`. See §6.2.

3. **Results** — *Calculate* button; table: File Name, Weight per piece (g),
   Count, Item Total (g); prominent footer: **Package Total (g)** and
   **Package Total (lb, oz)**. Rows skipped because of Errors appear at the
   bottom of the table as **"Skipped - not included"** in red, and
   a red badge beside the total reads **"⚠ Incomplete: N files skipped"**
   (see §7). *Copy Results* puts a tab-separated table on the clipboard
   **[decision]**, including the skipped rows, an
   "INCOMPLETE: N FILES SKIPPED - NOT A COMPLETE SHIPPING WEIGHT" marker on
   the total line, and one "Skipped: file - reason" line per skipped file. Results are cleared/marked stale whenever the
   pieces table or control values change after a calculation **[decision]**.

### 4.1 Table behavior (both tables)

- **Column resizing.** Drag a header border to resize any column; the width
  stays through window resizes, re-Calculate, and sorting.
  Cause of the old Results snap-back: Tk's Treeview only resizes a dragged
  column if a *stretchable* column lies to its right to absorb the
  difference; otherwise it undoes the drag. Results had just one stretchable
  column (File Name) with nothing stretchable after it. The pieces table had
  the same latent issue for its right-hand columns. Fix: every real column
  is `stretch=False`, and each table ends with a blank stretchable **filler
  column** that absorbs slack. Both tables have **horizontal scrollbars**, so
  columns wider than the table (for example with large text) stay reachable.
- **Sorting.** Click a header to sort ascending, and click again to reverse.
  The sorted header shows ▲ or ▼. A stable sort is used, so ties keep import
  order. Logic lives in `table_sort.py` and is unit-tested.

  | Table | Sortable columns and key |
  |---|---|
  | Pieces | Count (number); File Name (case-insensitive); Date Modified (real timestamp; missing files always last); Status (Error → Warning → Info → OK) |
  | Results | File Name (case-insensitive); Weight per piece (g), Count, and Item Total (g) (all numeric, not text) |

  - "Skipped - not included" rows always stay at the bottom of Results,
    whatever the sort direction (and when unsorted).
  - Sorting is **display-only**. The app keeps rows in import order
    (`_row_order`), and calculation and Save Package Preset always use that
    order. Selection and the preview follow the selected row. Sorting never
    marks results stale.
  - A sort stays active. It is re-applied after import, preset load, and
    edits (for example, changing Count while sorted by Count). The Results
    sort also survives re-Calculate.

### 4.2 Text size

View menu: **Larger Text** (Ctrl+=, also Ctrl+Plus / Ctrl+keypad +),
**Smaller Text** (Ctrl+-), and **Reset Text Size** (Ctrl+0). Available steps
are 80, 90, 100, 110, 125, 140, 160, 180, 200, 225, and 250%.

- Scales named fonts shared by both tables (rows and headers), the details
  pane, and the Results footer. The footer keeps its proportions: base sizes
  are "Package Total:" 11pt bold, the totals 15pt bold, and the Incomplete
  badge 11pt bold, against 9pt table text.
- Treeview row height = line spacing + max(8, line spacing / 2), so text
  never clips.
- Column widths are scaled by the same ratio, which keeps any widths the
  user set in proportion.
- Saved to `settings.json` → `text_scale` and restored on startup.
- The control panel, buttons, and section titles are not scaled
  **[decision]**. The request covered the tables, details, and results.

## 5. DXF geometry

### 5.1 Entity handling

| Entity | Handling |
|---|---|
| LINE | Segment |
| ARC | Tessellated, ≤ 2° per segment |
| CIRCLE | Tessellated; is its own closed loop |
| LWPOLYLINE / POLYLINE (2D) | Supported: exploded to lines/arcs (bulges honored); closed polylines become their own loop |
| INSERT (block reference) | Exploded recursively and handled as above **[decision]** |
| SPLINE (incl. rational/NURBS, control- or fit-point) | Flattened with ezdxf to a max deviation of **1e-5 × the curve's control-point extent**; closed splines are their own loop, open ones are stitched like any segment |
| ELLIPSE (full or partial) | Flattened the same way (1e-5 × major diameter); a full ellipse is its own loop |
| HELIX, 3D polyline/mesh, SOLID, TRACE, 3DFACE, REGION, 3DSOLID, MPOLYGON, other drawable geometry | **Error** naming the type and count |
| TEXT, MTEXT, DIMENSION, LEADER, MLEADER, HATCH, POINT, ATTDEF, VIEWPORT, IMAGE, etc. | Ignored → **Info** note naming what was skipped |
| Any entity on a layer that is **off or frozen**, or whose name is in `ignored_layer_names` | Skipped → **Info** note (layer name + count) **[decision, user-approved]** |

Curve accuracy: 2° arcs under-report a full circle's area by about 2e-4
(relative). Flattened splines and ellipses are finer: the tests check them
against analytic areas (a parabola segment, an exact NURBS circle, πab) to
0.01%. On the user's real files, the areas agree with a 1000× finer
flattening to within 1.2e-6.

Spline endpoints: ezdxf evaluates each curve's exact start and end, so they
land on neighboring LINE/ARC/SPLINE endpoints far inside the 1e-4 stitch
tolerance. On the user's real exports, the measured mismatch is ≤ 2e-11 in.
The tolerance was **not** loosened.

### 5.2 Loop building

1. Collect segments in **raw file coordinates** (never scaled).
2. Drop zero-length segments; drop exact duplicate segments (common in CAD
   exports) with an Info note **[decision]**.
3. Closed entities (circle, closed polyline) → own loop.
4. Stitch remaining segments end-to-end, matching endpoints within
   **1e-4 file units**, until each chain returns to its start.
   - An endpoint shared by more than two segments → **Error** (ambiguous
     junction, approximate location given) **[decision]**.
   - A chain that cannot close → **Error** "gap found near (x, y)".
5. Loop area by the shoelace formula (absolute value).

### 5.3 Net area

- Largest loop = outer boundary. **Net area = outer − Σ(other loops).**
  Never a sum of loops.
- **Sanity errors:** Σ(holes) ≥ outer, or any single loop > outer.
- **Multiple shape groups (Warning):** any non-outer loop that is not inside
  the outer loop (tested by point-in-polygon on a vertex), or a loop nested
  inside a hole. For display in that case the area is computed by even-odd
  nesting (outer shapes add, holes subtract) and the warning says so
  **[decision]**. Numerically identical to the spec formula whenever there is
  exactly one shape group.
- No geometry at all after filtering → **Error**.

### 5.4 Units

- `$INSUNITS` 1 → Inches, 4 → Millimeters. Anything else (0/unitless,
  cm, ft, …) → **Unknown**, with a message naming what the header said
  **[decision]**.
- **Unknown units = Error** (that row is skipped by Calculate until the
  user picks a unit). This message is not shown for files with no readable
  geometry: there the parser's own error is the real reason.
- Changing a row's Units reinterprets the raw numbers in the new unit;
  bounding box and area are re-derived from the raw data.

## 6. Presets

### 6.1 Package preset (`package_presets/<safe name>.json`)

```json
{
  "type": "tallycraft.package", "version": 1, "name": "XL Complete Set",
  "saved_at": "2026-09-27T13:00:00",
  "pieces": [
    {"path": "D:/Designs/XL/side.dxf", "units": "in", "count": 2,
     "mtime": 1790000000.0}
  ]
}
```

- Absolute paths **[decision]**. File name is the preset name with
  characters illegal on Windows replaced; confirm before overwriting.
- On load: table is replaced; each file is re-parsed; unit override and count
  restored. If the current mtime differs from the stored one → **Warning**
  "This file has been modified since this preset was saved — recommend
  re-importing/reviewing." Missing file → **Error** on that row.
- Loading a package never touches the control section.

### 6.2 Calibration preset (`control_presets/<safe name>.json`)

Control-sample method:

```json
{"type": "tallycraft.control", "version": 1, "name": "DixiePly 120526",
 "method": "control",
 "length": "4.000", "width": "2.0", "unit": "in", "weight_g": "23.456"}
```

Reference-piece method:

```json
{"type": "tallycraft.control", "version": 1, "name": "DixiePly 120526",
 "method": "reference",
 "reference_path": "D:/.../XL v1 - Main Box - Rear Panel - x3.DXF",
 "reference_name": "XL v1 - Main Box - Rear Panel - x3.DXF",
 "quantity": "10", "weight_g": "1234.567",
 "grams_per_cm2": 0.45446, "reference_area_cm2": 1272.98}
```

- Typed values are stored as the exact text entered (strings), so no
  precision or trailing zeros are lost **[decision]**. Numeric values are
  also accepted on load.
- **Backward compatible:** a preset with no `"method"` key (v0.1.0) loads as
  a control-sample preset, unchanged.
- Loading a reference preset switches the method to Reference piece and
  fills in the quantity and weight. Then:
  - If the referenced file (matched by full path, case-insensitive) is in
    the current table, it becomes the Piece and its **current** area is
    used. If that gives a different ratio than the saved one, a note says
    the file's area has changed since the preset was saved.
  - Otherwise, the preset's **saved area** is used (`reference_area_cm2`,
    or `weight / (quantity × grams_per_cm2)` if missing). This reproduces the
    saved g/cm². The Piece dropdown shows "*name* (from preset "*P*")", the
    ratio line adds "from saved preset", and a note says the calibration came
    from a saved preset, not a piece in this package. Quantity and weight
    stay editable, and the ratio recomputes from the saved area
    **[decision]**. Choosing a real piece replaces the saved area.
- Validation on load gives a friendly error for a missing reference path, a
  missing or ≤ 0 saved ratio, or an unknown method.
- The default-on-startup flag lives in `settings.json`, not in the preset.

## 7. Calculation

1. **Validation** before running:
   - Table not empty.
   - **Blocked** (nothing meaningful to compute) only if *every* row has an
     Error, or the calibration is invalid. Each problem is listed.
     - Control sample: any of Length, Width, or Weight is missing,
       non-numeric, or ≤ 0.
     - Reference piece: no piece chosen, or the chosen file was removed (with
       the reason); the piece's row has an Error or Unknown units; or Quantity
       or Total weight is missing, non-numeric, or ≤ 0 (Quantity must also be
       a whole number).
   - Rows with **Error** are otherwise **skipped, not blocking**
     (user-requested change, v0.2): Calculate runs on all non-Error rows.
   - Any *included* row with **Warning** → one confirmation dialog listing
     them; the user may continue **[user-approved]**. Info never blocks.
     If the **reference piece's** row has a Warning, the same dialog adds a
     section saying the calibration piece has a warning (so the ratio may be
     off). The dialog appears even if no other row has a warning.
   - After calculating, if rows were skipped, a notice lists each skipped
     file (with count) and the reason (its first Error). The results table
     and total are marked incomplete (see §4, Results) so a partial weight is never
     mistaken for a complete shipping weight.
2. **Math** (internal unit cm²; 1 in = 2.54 cm, 1 mm = 0.1 cm):
   - Control sample: `g_per_cm2 = weight_g / (length_cm × width_cm)`
   - Reference piece: `g_per_cm2 = total_weight_g / (quantity × piece_net_area_cm2)`
   - Everything below uses only `g_per_cm2`, so it's the same for both
     methods.
   - `weight_per_piece_g = g_per_cm2 × piece_area_cm2`
   - `item_total_g = weight_per_piece_g × count`
   - `package_total_g = Σ item_total_g`
   - lb/oz: 453.59237 g/lb, 28.349523125 g/oz → e.g. `3 lb 4.2 oz`
     (ounces to 1 decimal; carries 16.0 oz into the next pound).
3. Display: grams to 2 decimals in the table, footer total to 1 decimal.
4. *Copy Results* ends with a line saying where the ratio came from, e.g.
   `Calibration: reference piece X.DXF, 10 weighed, 1234.567 g total → 0.45446 g/cm² (2.93200 g/in²)`,
   noting "area from saved preset" when that applies **[decision]**.

## 8. Error-handling principles

- Every problem is a specific, plain-language message tied to a file/row.
- One bad file never blocks importing the rest of the batch.
- Missing / unreadable / corrupt / empty DXF → per-row **Error**.
- Unexpected exceptions anywhere in the GUI are caught by a top-level handler
  that shows a friendly dialog (and writes details to `tallycraft_error.log`
  next to the exe) instead of crashing **[decision]**.
- Control inputs: non-numeric, zero, or negative → field highlighted + clear
  message; never treated as zero.

Implementation: `calc.calculate(pieces, control, skipped)` returns a
`CalcResult` with `.skipped`, `.incomplete`, and `.incomplete_note`, and
`calc.results_as_text(result)` builds the clipboard text. Both are covered by
unit tests.

## 9. Hidden self-test mode

`TallyCraft.exe --selftest <report.json> <file.dxf>...` parses files without a
window and writes a JSON report. It exists so CI (and anyone else) can verify
a packaged exe really bundles ezdxf correctly.

## 10. Repository & distribution

```
README.md            GitHub landing page (visitor-facing, download steps)
LICENSE              MIT
CLAUDE.md            conventions for Claude sessions
docs/                SPEC.md, PROGRESS.md, BUILDING.md, original prompt
src/tallycraft/      app package (dxf_geometry, calc, storage, gui, …)
assets/              generated icon (tallycraft.ico, .png)
tools/make_icon.py   icon generator
dist_template/       README.txt shipped inside the TallyCraft/ folder
build.py             PyInstaller build + assembles dist/TallyCraft/ + zip
tests/               pytest
.github/workflows/release.yml
```

- Public repo: `github.com/jaerixon/TallyCraft`.
- Release: pushing tag `vX.Y.Z` triggers GitHub Actions (windows-latest) to
  run tests, build, zip `TallyCraft/` as `TallyCraft-vX.Y.Z-windows.zip`,
  and attach it to a GitHub Release.
- Rebuild instructions in `docs/BUILDING.md`.
