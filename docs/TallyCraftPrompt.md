# Build "TallyCraft" — a Windows desktop app for calculating shipment weights from DXF files

## What this app is for

I run a small laser-cutting business selling plywood products (e.g., rabbit
enclosures). Each product ships as a kit of multiple flat pieces. I need an
app that takes the DXF files for a set of pieces, calculates each piece's
surface area, and — using a known weight-per-area ratio from a "control"
sample of the same plywood — calculates the weight of every piece, the total
count of each, and the total shipment weight. This lets me generate accurate
packing/shipping weights without manually weighing every kit.

**Why weight-per-area, not weight-per-volume:** Plywood thickness varies
sheet to sheet (moisture, manufacturing tolerance) even at a nominal
thickness. A single length/width/weight control sample and a "grams per unit
area" ratio sidesteps that problem entirely — a thicker spot in the sheet is
also a heavier spot, so the ratio holds even when the actual thickness
wanders. Thickness is therefore not collected anywhere in the app, and no
density figure is displayed.

## Tech stack

- Python, packaged as a native Windows executable via PyInstaller
  (`--onefile`, custom icon).
- GUI: Tkinter + ttk (built into Python — simplest to package, no extra
  runtime dependencies). A clean, simple layout is the goal, not a fancy one.
- DXF parsing: the `ezdxf` library.
- Presets/settings: plain JSON files on disk (no database).

## App name and icon

Name: **TallyCraft**

Icon/logo: keep it simple and generate it programmatically (e.g., with
Pillow) rather than requiring an external asset — a minimalist icon combining
a small stack of tally marks ( |||| / ) next to a simple outlined box/crate
shape. Render it to a `.ico` for the executable and window title bar.

## Folder structure on disk

The distributed app should be a folder like this:

```
TallyCraft/
  TallyCraft.exe
  package_presets/       <- saved "package" presets (JSON), one file per preset
  control_presets/       <- saved "control/material" presets (JSON), one file per preset
  settings.json           <- app-level settings, incl. default control preset
  README.txt              <- plain-language description + how to use it
```

`settings.json` should support: "use control preset X as the default on
startup." Store this as a simple key in settings.json (a single global
default is fine — I don't need per-folder logic beyond that).

The README.txt should explain, in plain non-technical language: what the app
does, the meaning of each screen, and the basic workflow (import → review/
adjust → set control values → calculate → save presets if desired).

## Core workflow

### 1. Import DXF files

- A button to open a multi-select file dialog for `.DXF` files.
- For each selected file, parse it and populate a row in a table with these
  columns:
  - **Count** — editable integer, default `1` (how many of this piece are in
    one kit/package)
  - **File Name**
  - **Units** — as read from the DXF header (`$INSUNITS`), but shown as an
    **editable dropdown** (Inches / Millimeters / Unknown) so I can correct
    it after the fact if the file's metadata is wrong
  - **Bounding Box (W x H)** — in whatever unit is currently selected for
    that row
  - **Area** — the calculated net surface area (see geometry logic below),
    in the currently selected unit for that row (in² or mm²)
  - **Date Modified** — the file's OS "last modified" timestamp, for my own
    reference (so I can tell if a design changed since I last calculated it)
  - **Status** — see error handling below (OK / Warning / Error, with a
    tooltip or expandable detail on hover/click)

- **Changing the Units dropdown for a row must re-derive the bounding box and
  area** by reinterpreting the raw DXF coordinate numbers in the new unit
  (i.e., this is a correction to a wrong assumption, not a unit conversion of
  a correct value — the underlying numbers don't change, only what unit they
  represent).
- Changing **Count** just updates that row's multiplier for the final
  calculation step — it does not affect area.
- Give me a "Recalculate" or equivalent so changes are clearly re-applied
  (can be automatic on edit if that's cleaner — your call).

### 2. Geometry / area calculation logic

This has already been prototyped and validated against a real file from my
library, so please follow this approach rather than re-deriving it from
scratch:

- Real-world DXF exports from my CAD software are **not** clean closed
  polylines — they're loose individual `LINE` and `ARC` entities (and
  possibly `CIRCLE`) that have to be stitched into closed loops by matching
  endpoint coordinates within a small tolerance (~1e-4 in the file's native
  units).
- Algorithm:
  1. Load all `LINE`, `ARC`, and `CIRCLE` entities from modelspace.
  2. Tessellate arcs/circles into short line segments (fine enough that the
     polygon approximation is for-all-practical-purposes exact — e.g. one
     segment per ~2° of arc).
  3. Any entity that is already closed on its own (a full circle) is its own
     loop. For the rest, stitch open segments end-to-end by matching
     endpoints within tolerance until each chain returns to its own start
     point, forming a closed loop.
  4. Compute each closed loop's area via the shoelace formula.
  5. **The loop with the largest area is the outer boundary. Subtract the
     area of every other loop from it.** That result is the piece's net
     area. (This correctly handles any number of holes/cutouts — it must
     NOT sum multiple loops' areas together.)
  6. Ignore non-geometry entities (TEXT, DIMENSION, construction layers,
     etc.) when computing area, but see error handling below re: telling me
     when something was ignored.

### 3. Save/load a "Package" preset

- A **Package** = the full imported table state: which DXF files, their
  per-row unit override, and their per-row count.
- "Save Package Preset" prompts for a name (e.g., "XL Complete Set") and
  writes a JSON file into `package_presets/`.
- "Load Package Preset" repopulates the table. On load, re-check each file's
  current on-disk "Date Modified" against what was stored in the preset —
  if it's changed, flag that row with a clear warning ("This file has been
  modified since this preset was saved — recommend re-importing/reviewing").
- Loading a package preset should NOT itself set/require a control preset —
  those are independent (see below).

### 4. Control / material values

A separate panel/section for the plywood batch currently being used:

- **Length**, **Width**, **Weight (g)** — three numeric inputs, each
  supporting **at least 3 decimal places** of precision. This is a simple
  control sample (e.g., a 2"x4" offcut) cut from the same stock as the
  pieces being calculated — no thickness measurement is needed, since the
  weight-per-area ratio already accounts for it (see rationale above).
- **Length/Width share a single unit toggle** (Inches / mm). Weight is
  always grams.
- "Save Control Preset" prompts for a name (e.g., "DixiePly 120526") and
  writes JSON into `control_presets/`.
- "Load Control Preset" — a dropdown or file-open populated from
  `control_presets/`.
- A setting (checkbox or menu item) — "Use this preset as default on
  startup" — writes the preset name into `settings.json`; on launch, if that
  key is set, auto-load that control preset.

### 5. Calculate

- Button: "Calculate." Before running, validate that every row in the
  package table is in an "OK" state (no unresolved errors — see below) and
  that all three control values (Length, Width, Weight) are filled in and > 0. If not, block
  calculation and clearly tell me what's missing/wrong.
- Math (perform all area/weight conversions into one consistent internal
  unit, e.g. convert everything to cm² before dividing, so mismatched
  in/mm settings between the control sample and imported pieces are handled
  correctly automatically):
  - `grams_per_unit_area = control_weight_g / control_area`
  - For each piece: `weight_per_piece_g = grams_per_unit_area * piece_area`
  - `item_total_g = weight_per_piece_g * count`
  - `package_total_g = sum(item_total_g for all pieces)`
  - Convert `package_total_g` to pounds + ounces for display.
- Results table: File Name, Weight per piece (g), Count, Item Total (g).
- Footer: **Package Total (g)** and **Package Total (lb, oz)**, shown
  prominently.

### 6. Error handling and validation (please be thorough here)

Every one of these should produce a clear, specific, non-technical message
telling me what's wrong and (where possible) which file/row it affects —
never a silent wrong number, and never an unhandled crash.

- **Unsupported geometry** — any entity type other than LINE/ARC/CIRCLE that
  contributes to the boundary (e.g. SPLINE, ELLIPSE, LWPOLYLINE/POLYLINE) —
  flag the row as an error naming the unsupported type, and don't include it
  in totals until resolved. (Support LWPOLYLINE/POLYLINE properly if
  reasonably easy, since some of my export settings may produce those
  instead of loose lines — but always fail loudly and specifically for
  anything genuinely unhandled, rather than guessing.)
- **Unclosed loop / dangling chain** — a segment that doesn't find a
  matching endpoint within tolerance — flag as an error naming that a gap
  was found (approximate location if feasible).
- **Multiple disconnected shape groups in one file** (i.e., after stitching,
  the loops don't all nest within one outer boundary — there appear to be
  two unrelated shapes in the same file) — flag as a warning for manual
  review rather than silently picking one.
- **Sanity check**: if the combined area of the "hole" loops is ≥ the area
  of the largest loop, or any individual inner loop is larger than the
  outer loop, flag as an error (something almost certainly parsed wrong).
- **Ignored entities** — if TEXT/DIMENSION/other non-geometry entities were
  present and ignored, show an informational (non-blocking) note so I know
  the app saw them and intentionally skipped them.
- **File-level errors** — missing file, corrupted/unreadable DXF, empty
  file, etc. — should show a clear per-file error and not crash the app or
  block importing the other files in the batch.
- **Input validation** on the control panel — non-numeric or zero/negative
  values for length/width/weight should be rejected with a clear
  message, not silently treated as zero.

## Distribution — public GitHub repository

This project should live in a **public GitHub repository** so I can download
it (and share it) directly from GitHub, similar in spirit to a previous
project of mine (TaiwanAtlas) — a clean root README, docs kept out of the
way in their own folder, and a working live artifact anyone can grab without
having to build it themselves.

- Initialize a git repo and structure it for GitHub from the start (`.gitignore`
  for Python/PyInstaller build artifacts, a root `README.md`, a `docs/`
  folder for anything beyond the root README).
- The root `README.md` is the GitHub landing page — written for a visitor,
  not just for me: what the app does, a short "how it works" summary, and
  clear **download instructions**.
- Since this is a Windows desktop app (not a web app), the right way to
  distribute it is a **GitHub Release** with the built `TallyCraft.exe` (or
  a zip of the whole `TallyCraft/` folder) attached as a release asset, so
  people can download and run it without cloning the repo or having Python
  installed. Document the release process (or better, set up a GitHub
  Actions workflow that builds the PyInstaller executable and attaches it
  to a release automatically when I push a version tag — nice to have, not
  mandatory if it adds too much complexity up front).
- Include an open-source license file — MIT is a reasonable default for
  something like this unless I say otherwise.

## Deliverables

- Full source code, organized reasonably (don't need to overthink
  architecture for an app this size, but keep DXF-parsing logic, the GUI,
  and preset/settings I/O in separate modules rather than one giant file).
- A PyInstaller spec/build command that produces the `TallyCraft/` folder
  layout described above.
- The generated icon.
- The README.txt described above.
- Brief notes on how to re-build the .exe if I need to make changes later.
