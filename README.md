<p align="center"><img src="assets/tallycraft.png" width="128" alt="TallyCraft icon"></p>

<h1 align="center">TallyCraft</h1>

<p align="center">
Shipping weights for laser-cut plywood kits, calculated from your DXF files.<br>
No need to weigh every kit.
</p>

---

## What it does

You sell products that ship as kits of flat plywood pieces, such as enclosures, furniture, or puzzles.
TallyCraft takes the DXF design file for each piece and measures its net surface area:
the outline minus every hole and cutout. It then weighs the kit using a single small **control
sample** cut from the same plywood stock.

It gives you:

- the weight of each piece,
- the item total for each piece (weight × count per kit), and
- the **package total** in grams and in **lb + oz**.

Save a kit as a *Package Preset* and a plywood batch as a *Control Preset*. The next shipment
then takes two clicks.

## Download

1. Go to the [**Releases**](https://github.com/jaerixon/TallyCraft/releases/latest) page.
2. Download `TallyCraft-vX.Y.Z-windows.zip` under **Assets**.
3. Unzip it somewhere you can save files, such as Documents or the Desktop (not Program Files).
4. Double-click `TallyCraft.exe`. You don't need to install Python or anything else.

> Windows may say *"Windows protected your PC"* the first time, because the exe isn't
> code-signed. Click **More info → Run anyway**.

The unzipped folder looks like this:

```
TallyCraft/
  TallyCraft.exe
  package_presets/     saved kits
  control_presets/     saved plywood batches
  settings.json        app settings (for example, the default plywood batch)
  README.txt           plain-language guide to every screen
```

## How it works

**Why weight-per-area instead of volume?** Plywood thickness varies from sheet to sheet, even at
the same nominal thickness. A thicker spot is also a heavier spot, though. If you weigh a scrap
(for example 2″ × 4″) cut from the same stock, the grams-per-area ratio accounts for thickness
automatically. You never have to measure it.

**Geometry.** Real CAD exports are usually loose `LINE`s and `ARC`s rather than clean closed
shapes. TallyCraft:

1. Reads `LINE`, `ARC`, `CIRCLE`, `LWPOLYLINE`/`POLYLINE`, and block references.
2. Converts arcs and circles into straight segments of 2° or less.
3. Joins segments into closed loops wherever their endpoints meet (within 0.0001 units).
4. Measures each loop with the shoelace formula. The largest loop is the outline, and every
   other loop is a hole that gets **subtracted**.

**Math.** Everything is converted to cm², so inch and mm files can be mixed freely:

```
g_per_cm² = control_weight_g / control_area_cm²
piece_g   = g_per_cm² × piece_area_cm²
item_g    = piece_g × count
total_g   = Σ item_g        →  also shown as lb + oz
```

**Problems are reported, not guessed around.** Each row gets a status: OK, Info, Warning, or
Error. Gaps in an outline, unsupported curves (splines, ellipses), unknown units, damaged files,
and files with several separate shapes are all flagged by name and location. Calculate won't
run while any row has an Error. It asks you to confirm before running if any row has a Warning.

## Run from source

```powershell
git clone https://github.com/jaerixon/TallyCraft.git
cd TallyCraft
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
$env:PYTHONPATH = "src"; .venv\Scripts\python -m tallycraft
```

When you run from source, presets and settings are stored in `portable/`, which is git-ignored.
Tests: `.venv\Scripts\python -m pytest`.

## Docs

- [Building & releasing](docs/BUILDING.md)
- [Design spec](docs/SPEC.md)
- [Progress log](docs/PROGRESS.md)

## License

[MIT](LICENSE)
