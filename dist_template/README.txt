TALLYCRAFT — shipping weights for laser-cut plywood kits
=========================================================

WHAT IT DOES
------------
TallyCraft works out how much a kit of plywood pieces weighs, without you
having to weigh every kit.

You give it the DXF design file for each piece in the kit. It measures the
surface area of each piece (the outline minus any holes or cutouts). Then
you weigh something cut from the same plywood, once, so TallyCraft knows how
many grams each square inch or square millimeter of that plywood weighs.
That can be some pieces you've already cut from the kit (the easiest way),
or a separate scrap sample. From that it works out:

  * the weight of each piece,
  * the weight of all copies of that piece in the kit, and
  * the total weight of the whole package, in grams and in pounds + ounces.

Why weight-per-area? Plywood thickness varies a little from sheet to sheet,
but a thicker sheet is also a heavier one. Weighing something cut from the
same stock captures that automatically. You never need to measure thickness.


WHAT'S IN THIS FOLDER
---------------------
  TallyCraft.exe     the program. Double-click to start it.
  package_presets\   your saved kits (lists of pieces), one file each
  control_presets\   your saved plywood batches (calibration presets), one file each
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

   PREVIEW: click a row to see a drawing of that piece next to the details
   box. It shows exactly what TallyCraft measured:
     brown outline, wood fill   the solid piece
     blue outlines              holes and cutouts (subtracted)
     dashed orange line         part of an outline that never closes
     red circles                where a gap or a problem junction is
   The piece's size is shown under the drawing. If a file couldn't be read
   at all, the preview says why. Drag the bar above the details box to make
   the preview taller. Drag the bar between the details box and the preview
   to make it wider.

2. CALIBRATION (bottom left): your plywood batch
   This tells TallyCraft how heavy your plywood is. Pick a Method:

   Reference piece (the default, and usually easiest)
     Weigh some pieces you've already cut, for example 10 of the same part.
       Piece             choose that part from the list (it lists the files
                         in the pieces table above)
       Quantity weighed  how many of them you put on the scale
       Total weight (g)  what they weighed together
     For best accuracy, weigh several pieces or a large piece.
     The part must have a good outline (no Error) and known Units. If you
     remove that part from the table, TallyCraft clears it and tells you.

   Control sample
     Weigh a separate scrap rectangle instead. Enter its Length and Width
     (pick Inches or mm) and its Weight in grams.

   Either way, you can type as many decimal places as your scale gives you,
   and TallyCraft shows the grams-per-area ratio as you type.

   Save a batch as a Calibration Preset (e.g. "DixiePly 120526") and load it
   again later from the list. Tick "Use this preset as default on startup"
   to have it filled in automatically every time TallyCraft opens.
   A Reference piece preset also works with a different kit: if that part
   isn't in the table, TallyCraft uses the weight-per-area saved in the
   preset and says so.

3. RESULTS (bottom right)
   Press Calculate to see the weight of each piece, the item totals, and the
   Package Total in grams and in pounds + ounces. "Copy Results" copies the
   table so you can paste it into a spreadsheet or an email. If you change
   anything after calculating, the totals turn grey until you press
   Calculate again.

   Pieces with an Error are left out of the total. They are listed in the
   results as "Skipped - not included", a message tells you which files
   were skipped and why, and a red "Incomplete: N files skipped" badge
   appears next to the Package Total. A total with that badge is NOT the
   full shipping weight. Fix or remove those files and press Calculate
   again.


TABLE TIPS
----------
  * Sorting: click a column heading to sort by it, and click again to
    reverse the order. An arrow shows which column is sorted. In the pieces
    table you can sort by Count, File Name, Date Modified, or Status (Errors
    first). In Results you can sort by any column. Skipped files always stay
    at the bottom. Sorting only changes what you see. It doesn't change the
    total or the order saved in a package preset.
  * Column widths: drag the line between two column headings. If the columns
    get wider than the table, use the scrollbar underneath.
  * Window layout: drag the bar between the top half (pieces) and the bottom
    half (calibration and results) to give either half more room. TallyCraft
    remembers where you left it.
  * Text size: View menu > Larger Text / Smaller Text / Reset Text Size, or
    press Ctrl and = (larger), Ctrl and - (smaller), or Ctrl and 0 (reset).
    This changes the tables, the details box, and the results. TallyCraft
    remembers your choice.


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
           outline has a gap, the file uses a shape type TallyCraft can't
           measure (such as a 3D solid or a helix), the units are unknown,
           or the file is missing or damaged. Calculate skips these pieces
           and marks the total as incomplete (see RESULTS above).


BASIC WORKFLOW
--------------
  1. Import:     click "Import DXF..." and select all the piece files for one
                 kit (hold Ctrl or Shift to pick several).
  2. Review:     check the Status column and fix any Errors. Set each piece's
                 Count and correct its Units if needed.
  3. Calibrate:  pick the part you weighed, how many, and their total weight
                 (or use a control sample), or load a saved calibration preset.
  4. Calculate:  press Calculate and read the Package Total.
  5. Save:       optionally save the kit as a Package Preset, and the
                 plywood batch as a Calibration Preset. Next time, just load
                 them.

Package presets and calibration presets are separate. Load any kit together
with any plywood batch.


TIPS
----
  * Geometry on layers that are switched off or frozen in your CAD program
    is skipped, as is geometry on layers named CONSTRUCTION or DEFPOINTS.
    To skip other layer names, add them to "ignored_layer_names" in
    settings.json (open it with Notepad).
  * If something unexpected goes wrong, TallyCraft saves the details in
    tallycraft_error.log in this folder.

Project page, updates, and source code: https://github.com/jaerixon/TallyCraft
License: MIT
