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
  "last_import_dir": "C:/..."
}
```

- `default_control_preset` — auto-loaded on startup if set. If the named
  preset no longer exists, show a non-blocking notice and continue.
- `ignored_layer_names` — case-insensitive layer names whose geometry is
  skipped (see §5.1). **[decision, user-approved]**
- `last_import_dir` — convenience only **[decision]**.
- Unknown keys are preserved; a corrupt settings file is reported, backed up
  as `settings.json.bak`, and replaced with defaults (never a crash).

## 4. Screens / UI

One main window, three stacked sections **[decision]**:

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

2. **Control sample** — Length, Width (shared unit toggle Inches / mm),
   Weight (g). Entry fields accept ≥ 3 decimal places (no rounding of input).
   Buttons: *Save Control Preset…*, preset dropdown + *Load*, checkbox
   *Use this preset as default on startup*. Live display of the computed
   ratio (g/in² and g/cm²) when inputs are valid.

3. **Results** — *Calculate* button; table: File Name, Weight per piece (g),
   Count, Item Total (g); prominent footer: **Package Total (g)** and
   **Package Total (lb, oz)**. *Copy Results* puts a tab-separated table on
   the clipboard **[decision]**. Results are cleared/marked stale whenever the
   pieces table or control values change after a calculation **[decision]**.

## 5. DXF geometry

### 5.1 Entity handling

| Entity | Handling |
|---|---|
| LINE | Segment |
| ARC | Tessellated, ≤ 2° per segment |
| CIRCLE | Tessellated; is its own closed loop |
| LWPOLYLINE / POLYLINE (2D) | Supported: exploded to lines/arcs (bulges honored); closed polylines become their own loop |
| INSERT (block reference) | Exploded recursively and handled as above **[decision]** |
| SPLINE, ELLIPSE, 3D polyline/mesh, SOLID, 3DFACE, REGION, other drawable geometry | **Error** naming the type and count |
| TEXT, MTEXT, DIMENSION, LEADER, MLEADER, HATCH, POINT, ATTDEF, VIEWPORT, IMAGE, etc. | Ignored → **Info** note naming what was skipped |
| Any entity on a layer that is **off or frozen**, or whose name is in `ignored_layer_names` | Skipped → **Info** note (layer name + count) **[decision, user-approved]** |

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
- **Unknown units = Error** (blocks Calculate until the user picks a unit).
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

### 6.2 Control preset (`control_presets/<safe name>.json`)

```json
{"type": "tallycraft.control", "version": 1, "name": "DixiePly 120526",
 "length": "4.000", "width": "2.0", "unit": "in", "weight_g": "23.456"}
```

Values are stored as the exact text typed (strings) so no precision or
trailing zeros are lost **[decision]**; numeric values are also accepted on load. Default-on-startup flag lives
in `settings.json`, not in the preset.

## 7. Calculation

1. **Validation** before running:
   - Table not empty.
   - Any row with **Error** → blocked; list each file + reason.
   - All three control values (Length, Width, Weight) numeric and > 0 →
     otherwise blocked with a message per field.
   - Any row with **Warning** → one confirmation dialog listing them; user may
     continue **[decision, user-approved]**. Info never blocks.
2. **Math** (internal unit cm²; 1 in = 2.54 cm, 1 mm = 0.1 cm):
   - `g_per_cm2 = weight_g / (length_cm × width_cm)`
   - `weight_per_piece_g = g_per_cm2 × piece_area_cm2`
   - `item_total_g = weight_per_piece_g × count`
   - `package_total_g = Σ item_total_g`
   - lb/oz: 453.59237 g/lb, 28.349523125 g/oz → e.g. `3 lb 4.2 oz`
     (ounces to 1 decimal; carries 16.0 oz into the next pound).
3. Display: grams to 2 decimals in the table, footer total to 1 decimal.

## 8. Error-handling principles

- Every problem is a specific, plain-language message tied to a file/row.
- One bad file never blocks importing the rest of the batch.
- Missing / unreadable / corrupt / empty DXF → per-row **Error**.
- Unexpected exceptions anywhere in the GUI are caught by a top-level handler
  that shows a friendly dialog (and writes details to `tallycraft_error.log`
  next to the exe) instead of crashing **[decision]**.
- Control inputs: non-numeric, zero, or negative → field highlighted + clear
  message; never treated as zero.

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

- Public repo: `github.com/jaerxion/TallyCraft`.
- Release: pushing tag `vX.Y.Z` triggers GitHub Actions (windows-latest) to
  run tests, build, zip `TallyCraft/` as `TallyCraft-vX.Y.Z-windows.zip`,
  and attach it to a GitHub Release.
- Rebuild instructions in `docs/BUILDING.md`.
