TALLYCRAFT — shipping weights for laser-cut plywood kits
=========================================================

WHAT IT DOES
------------
TallyCraft works out how much a kit of plywood pieces weighs, without you
having to weigh every kit.

You give it the DXF design file for each piece in the kit. It measures the
surface area of each piece (the outline minus any holes or cutouts). Then it
uses a small "control" sample, a scrap cut from the same plywood that you
weigh once, to find out how many grams each square inch or square millimeter
of that plywood weighs. From that it works out:

  * the weight of each piece,
  * the weight of all copies of that piece in the kit, and
  * the total weight of the whole package, in grams and in pounds + ounces.

Why a weight-per-area sample? Plywood thickness varies a little from sheet
to sheet, but a thicker sheet is also a heavier one. Weighing a scrap from
the same stock captures that automatically. You never need to measure
thickness.


WHAT'S IN THIS FOLDER
---------------------
  TallyCraft.exe     the program. Double-click to start it.
  package_presets\   your saved kits (lists of pieces), one file each
  control_presets\   your saved plywood batches (control samples), one file each
  settings.json      app settings, including which plywood batch to load
                     automatically at startup
  README.txt         this file

Keep this folder somewhere you can save files to, such as Documents or the
Desktop. Program Files won't work, because Windows won't let TallyCraft
save presets there. If you move the folder, your presets move with it.

Windows may show a "Windows protected your PC" message the first time you
run TallyCraft, because the program isn't signed by a big company. Click
"More info", then "Run anyway".


THE SCREEN
----------
1. PACKAGE (top): the pieces in one kit
   One row per DXF file:
     Count          how many of this piece go in one kit. Double-click to change it.
     File Name      the DXF file.
     Units          whether the numbers in the file are Inches or Millimeters.
                    TallyCraft reads this from the file. If the file is wrong
                    or doesn't say, double-click to choose the right one. The
                    size and area are then recalculated from the file's own
                    numbers.
     Bounding Box   the overall width x height of the piece.
     Area           the piece's surface area, with holes and cutouts subtracted.
     Date Modified  when the DXF file was last changed on disk.
     Status         OK, Info, Warning, or Error (see below). Hover over it, or
                    click the row, to read the details in the box underneath.

   Buttons: Import DXF, Re-read Selected (loads a changed file again),
   Remove Selected, Clear All, Save Package Preset, Load Package Preset.

2. CONTROL SAMPLE (bottom left): your plywood batch
   Length and Width of your sample scrap (pick Inches or mm), and its
   Weight in grams. You can type as many decimal places as your scale and
   ruler give you. TallyCraft shows the grams-per-area ratio as you type.
   Save a batch as a Control Preset (e.g. "DixiePly 120526") and load it
   again later from the list. Tick "Use this preset as default on startup"
   to have it filled in automatically every time TallyCraft opens.

3. RESULTS (bottom right)
   Press Calculate to see the weight of each piece, the item totals, and the
   Package Total in grams and in pounds + ounces. "Copy Results" copies the
   table so you can paste it into a spreadsheet or an email. If you change
   anything after calculating, the totals turn grey until you press
   Calculate again.


STATUS MEANINGS
---------------
  OK       No problems.
  Info     Just so you know: for example, text or dimension notes in the
           file were skipped because they aren't part of the cut shape.
           Doesn't stop anything.
  Warning  Please take a look: for example, the file changed since the
           package preset was saved, or the file seems to contain two
           separate shapes. Calculate asks you to confirm before it
           continues.
  Error    TallyCraft can't trust this piece's area. For example, the
           outline has a gap, the file uses a curve type TallyCraft can't
           measure (splines, ellipses), the units are unknown, or the file
           is missing or damaged. Calculate won't run until you fix it or
           remove the row.


BASIC WORKFLOW
--------------
  1. Import:     click "Import DXF..." and select all the piece files for one
                 kit (hold Ctrl or Shift to pick several).
  2. Review:     check the Status column and fix any Errors. Set each piece's
                 Count and correct its Units if needed.
  3. Control:    enter your sample's length, width, and weight, or load a
                 saved control preset.
  4. Calculate:  press Calculate and read the Package Total.
  5. Save:       optionally save the kit as a Package Preset, and the
                 plywood batch as a Control Preset. Next time, just load them.

Package presets and control presets are separate. Load any kit together with
any plywood batch.


TIPS
----
  * Geometry on layers that are switched off or frozen in your CAD program
    is skipped, as is geometry on layers named CONSTRUCTION or DEFPOINTS.
    To skip other layer names, add them to "ignored_layer_names" in
    settings.json (open it with Notepad).
  * If something unexpected goes wrong, TallyCraft saves the details in
    tallycraft_error.log in this folder.

Project page, updates, and source code: https://github.com/jaerxion/TallyCraft
License: MIT
