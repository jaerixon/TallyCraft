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
| Packing lists | `docxtpl` fills an editable Word template (`.docx`); part pictures drawn with Pillow |
| PDF conversion | LibreOffice (headless) or Microsoft Word (COM via `pywin32`), chosen in Settings |
| Packaging | PyInstaller `--onefile`, custom icon |
| Icon | Generated with Pillow (tally marks `\|\|\|\|` + slash beside an outlined crate) → `.ico` |

## 3. Distributed folder layout

```
TallyCraft/
  TallyCraft.exe
  package_presets/     one JSON file per package preset (a product definition)
  control_presets/     one JSON file per calibration preset
  order_presets/       one JSON file per saved order
  packing_lists/       per shipment: .pdf + .docx + JSON record
  templates/           packing_list_template.docx (the user's, editable in Word)
    _default/          the app's pristine copy (refreshed by the app, never the user's)
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
  "main_split": 0.62,
  "shop_name": "Bun Homes Co.",
  "logo_path": "C:/.../logo.png",
  "default_note": "Thank you for your order!",
  "cut_colors": ["ACI 7", "RGB 0,0,0"],
  "template_path": "templates/packing_list_template.docx",
  "pdf_engine": "auto"
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
- `shop_name`, `logo_path` (optional PNG/JPG), `default_note`: set with
  *File > Settings…* and used by packing lists (§9). A non-string value falls
  back to the default; a blank logo path means none.
- `cut_colors` (v0.4) — colors that mean "cut" (§5.1): each "ACI n" or
  "RGB r,g,b". Default black only. An empty or non-list value falls back to
  the default; unparseable entries are ignored.
- `template_path` (v0.4) — the packing-list Word template; relative paths are
  inside the TallyCraft folder.
- `pdf_engine` (v0.4) — "Make PDFs with": `"auto"` (LibreOffice if installed,
  else Word), `"word"`, or `"libreoffice"`. Anything else falls back to `"auto"`.
- `default_control_preset` can name either kind of calibration preset (the
  key name is kept for compatibility).
- Unknown keys are preserved; a corrupt settings file is reported, backed up
  as `settings.json.bak`, and replaced with defaults (never a crash).

## 4. Screens / UI

### 4.0 Orders and packages (v0.3)

**Concepts.**
- A **Package** is a product definition: DXF pieces with per-kit counts. It
  is what a package preset stores.
- An **Order** is a list of packages, each with a **Quantity ≥ 1**.
- A normal single-item sale is an order with one package at quantity 1.
- **Naming:** name package presets **exactly like the Etsy listing
  variations** (e.g. "XL Standard Box", "Mini Tunnel + Ramp"), so a future
  Etsy integration can match orders to presets by name.

**Model.** The model lives in `order.py` (pure and unit-tested).
- `Package` holds its rows (tree id → `PieceRow`) in import order, a name, a
  `preset_name` (the preset it came from or was saved as), a quantity, and a
  **baseline**: the (path, units, count) list of that preset.
- **"Unsaved changes"** is *derived*: the current contents differ from the
  baseline. So undoing an edit clears the marker. A preset entry without
  units counts as matching the file's header units.
- The app starts with an order holding **one blank package** ("New Package 1"),
  so it behaves like before.

**Order section.** It sits above the pieces table, in the upper pane.
- Buttons: *Add Package from Preset…*, *New Blank Package*, *Remove*,
  *Save Order…*, *Load Order…*. These are also in the File menu.
- Table columns: **Package**, **Quantity** (double-click to edit; a whole
  number ≥ 1), and **Status**. Status is a summary such as "OK", "Empty",
  "2 pieces with errors", "1 warning", "1 units conflict", or "unsaved
  changes", joined with " · ". Rows are tinted red for problems and yellow
  for unsaved changes.
- Selecting a package makes section 1 show and edit **only that package**.
  Import, counts, units, re-read, remove/clear, sorting, preview, and
  *Save Package Preset…* are all scoped to it. Section 1's title reads
  "1. Package: *name* (unsaved changes)".
  - Implementation: `rows` and `_row_order` are properties that point at the
    selected package, so the pieces-table code is unchanged. Tree ids are
    globally unique across packages.
- Editing a package changes only the order's copy, never the preset on disk,
  until *Save Package Preset…* is used.
- **One entry per package.** Adding a preset already in the order (matched
  by preset name) increases its Quantity instead, and a message says so.
- **Add Package from Preset** replaces the startup blank package if that is
  still the only, empty, unsaved package. This keeps a single sale at the
  same number of clicks as before **[decision]**.
- **New Blank Package** gets a unique name ("New Package 2", …).
  *Save Package Preset…* suggests the package's name and asks for the Etsy
  variation name. Saving links the package to that preset, renames it,
  and clears "unsaved changes". It refuses a name used by another package
  in the order, so kit columns stay unambiguous. Replacing a *different*
  existing preset asks first.
- **Remove** asks first if the package has unsaved changes. Removing the
  last package leaves a fresh blank one.
- **Reference-piece calibration** lists pieces from **all** packages (it's
  the same material). A file name that appears more than once gets
  " — *package*" appended, plus the folder if it's still ambiguous. The
  reference follows its file across packages. It is cleared (with a note)
  only when the file is gone from the whole order.
- The old section 1 *Load Package Preset…* button is replaced by *Add Package
  from Preset…*.

### 4.0.1 Main window

One main window: Order section, section 1 (package pieces), and sections 2
and 3 **[decision]**. A **draggable horizontal divider** separates the upper
area (Order section plus section 1 with details/preview) from the lower area
(sections 2 and 3), so either half can get more height. Its position is
remembered (`main_split`).

1. **Package (pieces table)**, for the package selected in the Order
   section. Toolbar: *Import DXF…*, *Re-read Selected*, *Remove Selected*,
   *Clear All*, *Save Package Preset…*. Table columns:

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

3. **Results** — *Calculate* button. The table is **merged across the whole
   order**, one row per unique piece (see §7). Columns: File Name, **one count
   column per individual kit**, then **Total Count**, Weight per piece (g),
   and Item Total (g).
   - A package with quantity 2 gives two columns, "XL Standard Box (1 of 2)"
     and "XL Standard Box (2 of 2)"; a package with quantity 1 just uses its
     name.
   - Each kit cell shows that single kit's count (not multiplied), or "—" if
     the kit doesn't use the piece.
   - Kit columns are rebuilt on each Calculate and sized to fit their
     headings. Widths the user sets are remembered by column title.
   - The table scrolls horizontally.
   - Prominent footer: **Package Total (g)** and **Package Total (lb, oz)**. Rows skipped because of Errors appear at the
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
  | Results | File Name (case-insensitive); each per-kit count column, Total Count, Weight per piece (g), and Item Total (g) (all numeric, not text; "—" sorts as 0) |

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

**Reading.** Files are read with `ezdxf.readfile` first; `ezdxf.recover` is
used only if readfile reports the file as damaged. (LightBurn exports reuse
entity handles; recover mode silently drops every entity of such files, while
readfile loads them fine.) ezdxf's log chatter about those handles is silenced
while reading.

**Color rule (v0.4): black = cut, every other color = engrave only.**
- Each entity's *effective* color: its true color (RGB) if set, else its ACI
  color. BYLAYER takes the layer's color (true color or ACI); layer "0" inside a
  block takes the block reference's layer. BYBLOCK takes the enclosing
  INSERT's effective color; at top level it's treated as 7.
- Cut colors come from `cut_colors` (default: ACI 7 — the black/white color
  SolidWorks and LightBurn use — and RGB 0,0,0), editable in Settings.
- Cut geometry is measured as below. **Engrave geometry is never stitched,
  never a hole, never a gap/junction error**, and unsupported entity types in
  engrave colors are an Info note, not an Error. It's kept (as polylines) for
  the preview and packing-list pictures, and each row gets an Info note:
  "N engrave-only items drawn but not counted in weight."
- **Safety check:** if a file has geometry but none of it is in a cut color →
  **Error** "No cut (black) lines found. Check the colors in this file."
- The bounding box uses cut geometry only.
- Verified: all 305 of the user's real DXFs give identical results to v0.3
  (SolidWorks exports are layer "0", ACI 7), except 5 unitless files now
  assumed to be mm (§5.4).

| Entity | Handling |
|---|---|
| LINE | Segment |
| ARC | Tessellated, ≤ 2° per segment |
| CIRCLE | Tessellated; is its own closed loop |
| LWPOLYLINE / POLYLINE (2D) | Supported: exploded to lines/arcs (bulges honored); closed polylines become their own loop |
| INSERT (block reference) | Exploded recursively and handled as above **[decision]** |
| SPLINE (incl. rational/NURBS, control- or fit-point) | Flattened with ezdxf to a max deviation of **1e-5 × the curve's control-point extent**; closed splines are their own loop, open ones are stitched like any segment |
| ELLIPSE (full or partial) | Flattened the same way (1e-5 × major diameter); a full ellipse is its own loop |
| HELIX, 3D polyline/mesh, SOLID, TRACE, 3DFACE, REGION, 3DSOLID, MPOLYGON, other drawable geometry | **Error** naming the type and count (in a cut color); Info in an engrave color |
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

- `$INSUNITS` 1 → Inches, 4 → Millimeters. cm, ft, … → **Unknown**, with a
  message naming what the header said **[decision]**.
- **No units stated** (`$INSUNITS` missing or 0) → **assumed millimeters**,
  with an Info note ("Units not stated in file, assumed millimeters (…why…)"),
  when the file is recognizably a **LightBurn export** (R12/AC1009 with layers
  named `Layer_0`, `Layer_1`, …; LightBurn always exports mm) or its cut
  geometry is **over 60 units across** (60 in = 5 ft, implausible for a
  laser-cut part). Other unitless files stay **Unknown**. The Units dropdown
  still overrides; the override note then says "the file itself doesn't say;
  TallyCraft assumed millimeters".
- Regression: the user's LightBurn sample (in git-ignored
  `tests/fixtures_private/`, not committed — the repo is public) must give
  368.30 × 361.95 mm, 79,273 mm² (122.87 in²), 22 cutouts totaling 20.67 in²,
  151 engrave-only items. A synthetic LightBurn-style file (R12, Layer_N,
  bulged polylines, reused handles, no $INSUNITS) covers the format on CI.
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
- **Format unchanged** by orders (v0.3): all existing package presets load as
  they are. Adding one to an order creates a package whose baseline is the
  preset's pieces list.
- **Naming:** use the exact Etsy listing variation name.

### 6.3 Order (`order_presets/<safe name>.json`)

```json
{
  "type": "tallycraft.order", "version": 1, "name": "Etsy 3141592",
  "saved_at": "2026-09-28T10:00:00",
  "packages": [
    {"name": "XL Standard Box", "preset_name": "XL Standard Box", "quantity": 2,
     "unsaved_changes": false,
     "pieces": [{"path": "D:/.../Front Panel.DXF", "units": "in", "count": 1,
                 "mtime": 1790000000.0}]}
  ]
}
```

- Each package's **pieces are embedded** (same format as a package preset),
  so unsaved edits are kept, not just preset names. `unsaved_changes` records
  the state at save time.
- **Loading** replaces the current order (it asks first unless the current
  order is just the startup blank package).
  - Each package is rebuilt from its embedded pieces.
  - "Unsaved changes" is recomputed against the package preset *as it is on
    disk now*. If that preset no longer exists, the package shows as unsaved.
  - Files changed since the order was saved get the row Warning "…modified
    since this order was saved…". Missing files get an Error.
  - The status bar summarizes both counts, as with package presets.
- Validation gives friendly errors for a file with no packages, a package
  with no pieces list, or a piece with no path.

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

0. **Merge the order** (`order.merge_order`):
   - Pieces are the same when they point to the **same DXF file**: path made
     absolute, normalized, and case-insensitive on Windows.
   - Each unique file becomes one row. Its display name gets " — *folder*"
     appended if two different files share a name.
   - `kit_counts`: for each package, its count of that file (or None), once
     per unit of the package's quantity. `total_count = Σ count × quantity`.
   - A piece is an **Error** (skipped entirely and reported, as before) if:
     - its row has an Error in *any* package (the reason names the package);
     - it has **conflicting Units** in different packages (the reason lists
       which Units are in which packages); or
     - it was read at different times and its **area differs** between
       packages (re-read it) **[decision]**.
   - Row warnings are collected with their package names for the
     confirmation dialog.
1. **Validation** before running:
   - Order not empty.
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
   - `item_total_g = weight_per_piece_g × total_count` (the count across every kit in the order)
   - `package_total_g = Σ item_total_g`
   - lb/oz: 453.59237 g/lb, 28.349523125 g/oz → e.g. `3 lb 4.2 oz`
     (ounces to 1 decimal; carries 16.0 oz into the next pound).
3. Display: grams to 2 decimals in the table, footer total to 1 decimal.
   *Copy Results* uses the same columns as the table, including the per-kit
   columns, with "—" for unused.
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

## 9. Packing lists (v0.3; Word templates since v0.4)

A packing list is a separate record of **one actual shipment**. Order files
(§6.3) stay reusable order definitions and are unchanged.

Workflow: build the order, calibrate, press Calculate, then **Create Packing
List…** (Results bar, and File menu).

### 9.1 Creating one

- **Enabled only while results are current.** Everything a list needs is
  snapshotted at Calculate time (packages with pieces, the result, part
  pictures incl. engrave lines, full calibration state, timestamp).
- The **template is validated first** (§9.4). Problems that would break the
  list block with a clear message; unrecognized placeholders ask whether to
  continue.
- If any pieces were skipped, a **confirmation lists them** (they still go in
  the box; only their weight is unknown).
- Dialog: **Customer name** (required), shipping address (multi-line), Etsy
  order number, order date (defaults to today; YYYY-MM-DD), note to customer
  (pre-filled from `default_note`); a live line shows the file name.
- Output in `packing_lists/`: `<date> - <customer> - <order #>` `.json` (the
  record), `.docx` (the filled-in template), `.pdf`. Never overwritten
  (" (2)", " (3)", … — checked across all three extensions).
- The **record is the source of truth**; documents are always generated from
  it (`packing_docx.render_docx`), never from live app state, so a re-print
  never re-reads DXF files.
- **PDF conversion** (§9.5) runs in a **background thread** with a progress
  window naming the program. If it fails or the program is missing, the
  `.docx` is kept and a message says plainly why there's no PDF (and offers
  to open the .docx). A missing logo file is left out with a note.

### 9.2 The Word template (`templates/packing_list_template.docx`)

- Filled with **docxtpl** (Jinja2 placeholders inside a .docx). The user
  controls the look by editing it in Word.
- The **starter template** (`assets/templates/`, generated reproducibly by
  `tools/make_template.py`, bundled in the exe) reproduces the v0.3 layout:
  logo + shop name, "PACKING LIST" + date, boxed Ship-to / order # / order
  date block, items ordered, a prominent total weight box, the unmeasured
  warning, the kit legend, the parts table, footnotes, "Packed by / Date",
  the note in a box, and the small-print shop record. Calibri throughout;
  sizes 18 (title) / 16 (shop) / 20 (total) / 12 (name) / 10 body / 9 table /
  7–8 labels; US Letter portrait, 0.5 in margins.
- **Parts table:** one row per part via `{%tr for p in parts %}`; kit columns
  via `{%tc for h in kit_headers %}` (each `{%tc %}`/`{%tr %}` tag sits in its
  own cell/row, which docxtpl removes). Header row repeats on each page
  (`w:tblHeader`), rows don't split (`w:cantSplit`), footer shows the order
  reference and "Page X of Y" (Word PAGE/NUMPAGES fields; the Footer style's
  built-in tabs are cleared so the right tab wins).
- **Column widths:** docxtpl's column loop makes every column equal, so after
  filling, TallyCraft finds the parts table by its **Alt Text "TallyCraft parts
  table"**, restores the template's widths for the fixed columns, and shares
  the remaining page width among kit columns. Without the Alt Text it leaves
  docxtpl's layout.
- **Kit columns** use the template's real widths: full names if every
  heading fits (≤ 3 lines, column ≥ 0.55 in); else "Kit 1…" + a legend; else
  one column per package ("XL Standard Box (each of 15)"); else only Total
  count with a note. Never wider than the page.
- **Pictures:** PNG at **400 DPI** at printed size (the Picture column width
  − padding × 0.72 in), drawn 3× oversampled then downscaled: cut outline
  solid black, holes thinner, **engrave light grey and thinnest**, unclosed
  runs dashed. Bounding-box size in small text under each picture.
- **Word-validity repair:** after filling, any table cell left with no
  paragraph (e.g. a cell whose `{%p if %}` blocks were all removed) gets an
  empty paragraph — Word otherwise calls the whole file "corrupted". The
  starter template also keeps a permanent paragraph in such cells.
- Empty optional values are `""` so `{%p if … %}` hides them; addresses and
  notes keep their line breaks; text is XML-escaped (`&`, `<` are safe).
- **Never overwrite the user's template:** on startup the app refreshes
  `templates/_default/` (its own copy) and creates the user's template only if
  missing. Settings > **Restore default template** writes a *new* file
  ("packing_list_template (default copy).docx", " 2", …) and asks whether to
  use it. `build.py` refuses to delete an edited template (§11).

### 9.3 Skipped (unmeasured) pieces

Listed with their counts, "—" for weights, and a marker `*N` pointing to a
footnote with the reason. A red warning box under the total says "Total
weight excludes N part(s) that could not be measured…", and the totals row
reads "Total (measured parts)".

### 9.4 Field reference and validation

- Every placeholder is defined once in `packing_docx.FIELDS` (+ `PART_FIELDS`,
  `FOOTNOTE_FIELDS`). That list generates `docs/TEMPLATE_FIELDS.md`, the
  README.txt section, and the **Help > Packing List Template Fields** window;
  tests fail if the docs drift from the list or the context has a field the
  list doesn't.
- `validate_template` before generating:
  - **Errors (block):** can't be opened / not a Word document; broken
    brackets (Jinja syntax error); the parts loop (`parts`) missing; the total
    weight (`total_weight_lb_oz` or `total_weight_g`) missing.
  - **Warnings (can continue):** unrecognized top-level placeholders, and
    unrecognized `p.…` / `f.…` attributes inside the parts/footnote loops
    (which docxtpl itself doesn't check) — likely typos, rendered blank.

### 9.5 PDF conversion (Settings > "Make PDFs with")

- **Automatic** (default): LibreOffice if `soffice.exe` is found (PATH or
  Program Files), otherwise Word. **Word** / **LibreOffice** force one.
- **LibreOffice:** `soffice --headless --convert-to pdf` with a
  **throwaway user profile** (`-env:UserInstallation`, so no first-run dialogs
  and no clash with an open LibreOffice), a **120 s timeout** (then the whole
  process tree is ended with `taskkill /T`), no window. Environment switches
  `SAL_DISABLE_PRINTERLIST=1` and `SAL_DISABLE_DEFAULTPRINTER=1` are set **for
  that child process only**: otherwise LibreOffice asks the Windows default
  printer for page metrics, which took ~51 s with the user's network HP
  OfficeJet (with the switches: ~1.5–3 s; page size still comes from the
  template, verified US Letter).
- **Word:** COM automation (a private `DispatchEx` instance, hidden, alerts
  off, opened read-only, `ExportAsFixedFormat`), always `Quit()` in `finally`.
  Word also queries the default printer during export (~52 s on the user's
  PC). **TallyCraft never changes the default printer or any system setting**
  to work around that: Word writes its printer to the Windows default on
  quit, and restoring it left the print spooler inconsistent (tried and
  reverted in v0.4 development).
- Measured on the user's PC, same 3-page packing list: LibreOffice 2.9 s,
  Word 52.6 s; both US Letter, 3 pages, visually equivalent.
- Failures → `PdfConversionError` with a plain reason (not installed, timed
  out, couldn't convert, PDF open in another program); the .docx is kept.

### 9.6 The record (`packing_lists/<name>.json`)

```json
{"type": "tallycraft.packing_list", "version": 1, "app_version": "0.4.0",
 "created_at": "2026-09-28T10:20:00", "calculated_at": "2026-09-28T10:15:00",
 "customer": {"name", "address", "etsy_order", "order_date", "note"},
 "shop": {"name": "...", "logo": {"filename", "format", "data_base64"} | null},
 "order": {"items_ordered": "...", "packages": [ {as in an order file §6.3} ]},
 "calibration": {"method": "control", "length", "width", "unit", "weight_g",
                 "grams_per_cm2", "preset_name"}
              | {"method": "reference", "piece_name", "piece_path", "package",
                 "quantity", "weight_g", "area_cm2", "from_preset",
                 "grams_per_cm2", "preset_name"},
 "results": {"kit_labels": [...], "total_g", "grams_per_cm2", "skipped_count",
             "lines": [{"name", "path", "unit", "kit_counts", "total_count",
                        "weight_per_piece_g", "item_total_g", "skipped", "reason",
                        "picture": {"loops", "depths", "open", "engrave", "bbox"}}]}}
```

`engrave` was added in v0.4 (older records without it still load). The logo
is embedded so a re-print doesn't depend on the image file.
`packing.validate_record` rejects a wrong type/version, missing sections, or a
missing customer name.

### 9.7 Open Packing List… / Re-print

A read-only viewer shows customer info, total, calibration, and the results
snapshot (kit columns sized to their headings, skipped rows in red).
**Re-print** first confirms: "Uses your current template. The original PDF is
still saved alongside the record." It then writes **new** files
`<name> (reprint 2026-09-28 1015).docx/.pdf` (" 2", … if needed) — the
original PDF is never replaced.

### 9.8 Settings dialog

Shop name, logo (checked PNG/JPG), default note; Word template (Browse,
**Restore default template**, **Template Help**); **Make PDFs with**
(Automatic / Word / LibreOffice, showing whether LibreOffice was found);
**Cut colors** (one per line, validated). Changing cut colors offers to
re-read every piece in the order (counts and Units choices kept).

## 10. Hidden self-test modes

Output goes to files (the exe has no console); on failure a traceback is
written to `<out>.error.txt` and the exit code is 3 (never PyInstaller's
blocking error dialog).
- `TallyCraft.exe --selftest <report.json> <file.dxf>...` — parse files,
  JSON report.
- `TallyCraft.exe --selftest-docx <out.docx> <file.dxf>...` — validate the
  bundled template and fill it with a one-package list. **CI runs this**
  (GitHub's Windows runners have no Word), and checks the .docx has pictures
  and that `templates/` is in the app folder.
- `TallyCraft.exe --selftest-pdf <out.pdf> <file.dxf>...` — the same, then
  convert with Word (local check only).

## 11. Repository & distribution

```
README.md            GitHub landing page (visitor-facing, download steps)
LICENSE              MIT
CLAUDE.md            conventions for Claude sessions
docs/                SPEC.md, PROGRESS.md, BUILDING.md, original prompt
src/tallycraft/      app package (dxf_geometry, calc, storage, gui, …)
assets/              generated icon (tallycraft.ico, .png), templates/packing_list_template.docx
tools/make_icon.py   icon generator
tools/make_template.py  starter Word template + generated field docs (--docs)
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
- **Build safety:** `build.py` rebuilds `dist/TallyCraft/` from scratch, but
  first refuses (changing nothing) if the exe there is running or the folder
  contains **any file the build didn't create or that was changed since**:
  presets, orders, packing lists, a changed `settings.json`, an edited
  template, or anything dropped in (e.g. a DXF). `--exe-only` builds just
  `dist/_exe/TallyCraft.exe`.
- **Tests never launch Word or LibreOffice**; conversion is mocked. The one
  exception is `tests/test_real_conversion.py`, skipped unless
  `TALLYCRAFT_REAL_CONVERSION=1`, which also checks no Word/LibreOffice
  process is left running.
