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
the outline minus every hole and cutout. It then weighs the kit from one weighing of the same
plywood: either a few **pieces you've already cut** (weigh 10 of a part, enter the total), or a
separate small **control sample**.

It gives you:

- the weight of each piece,
- the item total for each piece (weight × count per kit), and
- the **package total** in grams and in **lb + oz**.

Save each product as a *Package Preset* and a plywood batch as a *Calibration Preset*. The next
shipment then takes two clicks.

**Orders with several products.** An order is a list of packages, each with a quantity, such as
2 × "XL Standard Box" plus 1 × "Mini Tunnel + Ramp". Results merge the whole order, with one row per
unique piece and one count column per kit, giving one shipping weight. A normal sale is just an
order with one package.

**Packing lists.** One click after Calculate produces a printable **packing list** (PDF + Word).
It has the customer and order details, the total shipping weight, and every part with a small
drawing, per-kit counts, weights, and a checkbox for the packer. **You control the look** by
editing a Word template; TallyCraft fills in the data. PDFs are made with LibreOffice (a few
seconds) or Microsoft Word. Each list is saved with a JSON record, so it can be re-printed later,
even if the DXF files change.

**SolidWorks and LightBurn files.** Black lines are cut; every other color is engraving, drawn in
pictures but never weighed. LightBurn DXF exports (which don't state units) are read as
millimeters.

**Import orders from Etsy.** Connect your shop once (read-only), then pick an open order: TallyCraft
builds the order by matching each listing variation (such as "Model: XL Standard Box") to the
package preset with the same name, and fills in the customer's name, address, order number and
date on the packing list. Items that don't match are shown so you can pick a preset or skip them,
and TallyCraft can remember your choice.

> **Tip:** name package presets exactly like your Etsy listing variations, so orders match
> automatically.

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
  order_presets/       saved orders
  packing_lists/       packing lists (PDF + Word + record)
  templates/           the Word template packing lists are made from
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

1. Reads `LINE`, `ARC`, `CIRCLE`, `SPLINE`, `ELLIPSE`, `LWPOLYLINE`/`POLYLINE`, and block
   references. Only **black** geometry (ACI 7 or RGB 0,0,0, configurable) counts as cut lines;
   other colors are engrave-only.
2. Converts arcs and circles into straight segments of 2° or less. Splines and ellipses are
   flattened even more finely (area error under 0.01%).
3. Joins segments into closed loops wherever their endpoints meet (within 0.0001 units).
4. Measures each loop with the shoelace formula. The largest loop is the outline, and every
   other loop is a hole that gets **subtracted**.

**Math.** Everything is converted to cm², so inch and mm files can be mixed freely:

```
g_per_cm² = weight_g / (quantity × piece_area_cm²)   # reference piece (default)
         or control_weight_g / control_area_cm²      # control sample
piece_g   = g_per_cm² × piece_area_cm²
item_g    = piece_g × count
total_g   = Σ item_g        →  also shown as lb + oz
```

**See what was measured.** Click any piece to see a preview drawn from the exact loops used for
its area. The solid outline and the holes are colored differently, and gaps are marked in red.

**Problems are reported, not guessed around.** Each row gets a status: OK, Info, Warning, or
Error. Gaps in an outline, unsupported geometry (such as 3D solids), unknown units, damaged
files, and files with several separate shapes are all flagged by name and location. Pieces with
an Error are skipped, and the total is clearly marked **"Incomplete: N files skipped"** so a
partial weight is never mistaken for a complete one. Calculate asks you to confirm before
running if any piece has a Warning.

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
- [Packing list template fields](docs/TEMPLATE_FIELDS.md)
- [Progress log](docs/PROGRESS.md)

## License

[MIT](LICENSE)
