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
  package_presets\   your saved packages (products: lists of pieces), one file each
  control_presets\   your saved plywood batches (calibration presets), one file each
  order_presets\     your saved orders, one file each
  packing_lists\     your packing lists: PDF, Word version, and record, per
                     shipment
  templates\         the Word template packing lists are made from (edit it!)
  settings.json      app settings, including which plywood batch to load
                     automatically at startup
  README.txt         this file

Keep this folder somewhere you can save files to, such as Documents or the
Desktop. Program Files won't work, because Windows won't let TallyCraft
save presets there. If you move the folder, your presets move with it.

Windows may show a "Windows protected your PC" message the first time you
run TallyCraft, because the program isn't signed by a big company. Click
"More info", then "Run anyway".


PACKAGES AND ORDERS
-------------------
  A PACKAGE is one of your products: the list of DXF pieces in one kit and
  how many of each (for example "XL Standard Box").
  An ORDER is what you are shipping: one or more packages, each with a
  quantity. A normal sale is simply an order with one package.

  NAME YOUR PACKAGE PRESETS EXACTLY LIKE YOUR ETSY LISTING VARIATIONS,
  for example "XL Standard Box" or "Mini Tunnel + Ramp" (same spelling,
  capitals, and symbols). A future version will be able to match Etsy
  orders to your presets by name.


THE SCREEN
----------
ORDER (very top): the packages in this sale
   Package    the package name.
   Quantity   how many of that package are in the order. Double-click to
              change it.
   Status     "OK", or what needs attention: pieces with errors, warnings,
              a units conflict, or "unsaved changes" (you edited this
              package in the order but haven't saved its preset).

   Buttons:
     Add Package from Preset   add one of your saved packages. If it's
                               already in the order, its Quantity goes up by
                               one instead (TallyCraft tells you).
     New Blank Package         start a package from scratch.
     Remove                    take the selected package out of the order.
     Save Order / Load Order   keep a whole order (including any unsaved
                               edits) and open it again later.

   Click a package to show its pieces in section 1 below. Everything in
   section 1 (import, counts, units, preview) works on that package only.
   Changes stay in this order until you press "Save Package Preset" again,
   so your saved preset is never changed by accident.

   For a normal sale, just click "Add Package from Preset", pick the
   product, and press Calculate.

1. PACKAGE (top): the pieces in one kit of the selected package
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
   Remove Selected, Clear All, Save Package Preset (use your Etsy listing
   variation name).

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
   Package Total in grams and in pounds + ounces. Results cover the whole
   order: each piece appears once, even if several packages use it. There
   is one count column per kit being shipped. An order with 2 x "XL Standard
   Box" shows "XL Standard Box (1 of 2)" and "(2 of 2)", and a dash means
   that kit doesn't use the piece. Then come Total Count, Weight per piece,
   and Item Total. Scroll sideways if there are many kits. If the same DXF
   file is set to different Units in two packages, it's flagged as an
   error until you make them match. "Copy Results" copies the
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
  1. Order:      click "Add Package from Preset" and pick the product(s) sold.
                 Set each package's Quantity.
                 (New product? Use the starting blank package: click "Import
                 DXF..." and select all its piece files, hold Ctrl or Shift to
                 pick several, then "Save Package Preset" with the Etsy
                 variation name.)
  2. Review:     check the Status columns and fix any Errors. Set each piece's
                 Count and correct its Units if needed.
  3. Calibrate:  pick the part you weighed, how many, and their total weight
                 (or use a control sample), or load a saved calibration preset.
  4. Calculate:  press Calculate and read the Package Total.
  5. Save:       optionally save new or changed packages as Package Presets,
                 the plywood batch as a Calibration Preset, and the whole order
                 with Save Order. Next time, just load them.
  6. Pack:       press "Create Packing List...", fill in the customer, and
                 print the PDF to put in the box.

Package presets and calibration presets are separate. Load any kit together
with any plywood batch.


PACKING LISTS
-------------
  After you press Calculate, "Create Packing List..." (next to Copy Results,
  or in the File menu) makes a printable packing list for the box. It only
  works while the results are up to date. If you change anything, press
  Calculate again.

  You enter the customer's name (required), shipping address, Etsy order
  number, order date (today unless you change it), and an optional note to
  the customer. TallyCraft saves three files in the packing_lists folder,
  named like "2026-09-27 - Jordan Rivera - 3141592":
    .pdf    the packing list to print
    .docx   the same packing list as a Word document
    .json   the record of the shipment (TallyCraft's copy of every detail)
  It never overwrites an earlier one.

  The PDF is made by LibreOffice or Microsoft Word (File > Settings...
  > "Make PDFs with"):
    Automatic    LibreOffice if it's installed, otherwise Word (default)
    Word         always Microsoft Word
    LibreOffice  always LibreOffice (free: libreoffice.org)
  LibreOffice usually takes a few seconds. Word can take up to a minute on
  some computers, because it waits for the default printer to answer. Either
  way it runs in the background with a progress window. If the program
  isn't installed or something goes wrong, you still get the .docx, and
  TallyCraft tells you why there's no PDF. You can print the .docx yourself.

  The packing list shows:
    * your shop name and logo, and the customer and order details
    * the items ordered and the TOTAL SHIPPING WEIGHT (lb/oz and grams)
    * every part, with a drawing (cut lines solid, engraving lighter) and its
      size, the count for each kit, the weights, and a box to tick as you
      pack it
    * a "Packed by / Date" line and your note to the customer
    * in small print at the bottom, how the weight was worked out (for your
      records)

  Parts that couldn't be measured (errors) are still listed, because they
  still go in the box, but with "—" for weight. A warning next to the total
  says the weight doesn't include them. TallyCraft asks before making the
  list.

  File > Open Packing List... shows an earlier shipment exactly as it was
  recorded. "Re-print PDF" makes new copies from that record using your
  CURRENT template, even if the DXF files have changed or moved since. The
  original PDF stays alongside the record; re-prints are saved as
  "... (reprint <date>)".

  File > Settings... sets your shop name, logo (PNG or JPG), and the note
  that's filled in for customers by default.


CHANGING HOW THE PACKING LIST LOOKS (WORD TEMPLATE)
--------------------------------------------------
  The packing list is made from a Word document you can edit:
      templates\packing_list_template.docx
  Open it in Word and change fonts, sizes, colors, spacing, wording, or the
  logo size, then save. The next packing list uses your changes.

  Things in double curly brackets, like {{ customer_name }}, are filled in
  by TallyCraft. Keep them, including the brackets. Lines like
  {%tr for p in parts %} are instructions (here: "one table row per part").
  Keep each of those alone on its own line, row, or cell.

  Before making a packing list, TallyCraft checks the template:
    * If something essential is missing (the parts table rows or the total
      weight), it stops and tells you what to fix.
    * If there's a placeholder it doesn't recognize (probably a typo, like
      {{ custmer_name }}), it warns you and lets you continue.

  Your edited template is never replaced when TallyCraft is updated. A clean
  copy is kept in templates\_default\. File > Settings... > "Restore default
  template" makes a fresh copy under a new name; your file isn't touched.
  Settings can also point TallyCraft at a different template file.

  Help > Packing List Template Fields lists every placeholder. So does
  this list:

<<TEMPLATE FIELDS START>>
Placeholders are written like {{ customer_name }} in the Word template.
Required: The parts table loop ({%tr for p in parts %} … {%tr endfor %}) and the total weight ({{ total_weight_lb_oz }} or {{ total_weight_g }}) must be in the template.

Tags: {{ name }} inserts a value. {%p if ... %} / {%p endif %} show or hide
paragraphs. {%tr for ... %} / {%tr endfor %} repeat table rows, and
{%tc for ... %} / {%tc endfor %} repeat table columns. Each {%tr %}, {%tc %}
and {%p %} tag must sit alone in its own row, cell, or paragraph.
Keep the parts table's Alt Text "TallyCraft parts table" so TallyCraft
can keep your column widths.

SHOP
----
  {{ shop_name }}
      Your shop name (File > Settings). Empty if not set.
      e.g. Bun Homes Co.
  {{ shop_logo }}
      Your logo image (File > Settings), 0.8 in tall. Empty if not set. Put
      it on its own line.
      e.g. (image)
  {{ packing_date }}
      The date the packing list was created.
      e.g. 2026-09-28

ORDER AND CUSTOMER
------------------
  {{ customer_name }}
      Customer name (always filled in).
      e.g. Jordan Rivera
  {{ customer_address }}
      Shipping address; its line breaks are kept. Empty if not entered.
      e.g. 123 Maple Street / Springfield, IL 62704
  {{ etsy_order_number }}
      Etsy order number. Empty if not entered.
      e.g. 3141592653
  {{ order_date }}
      Order date. Empty if not entered.
      e.g. 2026-09-27
  {{ items_ordered }}
      The packages in the order with quantities.
      e.g. 2x XL Standard Box, 1x XL Tunnel + Ramp
  {{ note_to_customer }}
      The note to the customer. Empty if none.
      e.g. Thank you for your order!
  {{ footer_reference }}
      For the page footer: "Etsy order #…", or "Packing list — <customer>"
      if there's no order number.
      e.g. Etsy order #3141592653

WEIGHT
------
  {{ total_weight_lb_oz }}
      Total shipping weight in pounds and ounces (measured parts).
      e.g. 4 lb 14.9 oz
  {{ total_weight_g }}
      Total shipping weight in grams, 1 decimal, no unit.
      e.g. 2,237.2
  {{ unmeasured_count }}
      How many parts couldn't be measured (0 if none).
      e.g. 1
  {{ unmeasured_warning }}
      A warning sentence when parts couldn't be measured; empty otherwise.
      Use with {%p if unmeasured_warning %} … {%p endif %}.
      e.g. WARNING: Total weight excludes 1 part that could not be measured (marked * below). It still goes in the box.

PARTS TABLE
-----------
  {{ parts }}
      The parts table rows. Loop over them with {%tr for p in parts %} …
      {%tr endfor %}; each p has the p.… fields below.
      e.g. (list)
  {{ kit_headers }}
      Kit column headings, for the column loop {%tc for h in kit_headers %}
      {{ h }} {%tc endfor %}. Full kit names, "Kit 1…", or one per package,
      depending on what fits.
      e.g. XL Standard Box (1 of 2), XL Standard Box (2 of 2)
  {{ kit_legend }}
      Explains short kit headings ("Kit 1 = …"); empty when full names fit.
      e.g. Kit columns: Kit 1 = XL Standard Box (1 of 4); …
  {{ kit_totals }}
      Totals-row values for the kit columns (same column loop).
      e.g. 28, 28, 9
  {{ total_count }}
      Totals row: all parts across every kit.
      e.g. 65
  {{ total_weight_measured }}
      Totals row: total weight in grams, 2 decimals (measured parts).
      e.g. 12,564.18
  {{ total_label }}
      Totals row label: "Total", or "Total (measured parts)" when some
      couldn't be measured.
      e.g. Total
  {{ footnotes }}
      One per unmeasured part, for {%p for f in footnotes %} … {%p endfor
      %}; each f has f.marker, f.name, f.reason.
      e.g. (list)

SHOP RECORD
-----------
  {{ calibration_method }}
      "Reference piece" or "Control sample".
      e.g. Reference piece
  {{ calibration_details }}
      Full calibration sentence (method, values, ratio, preset).
      e.g. Calibration: control sample 4 × 2 in, weight 23.456 g → 0.45446 g/cm² (2.93200 g/in²).
  {{ calibration_preset }}
      Calibration preset name, if the values still match it. Empty
      otherwise.
      e.g. DixiePly 120526
  {{ grams_per_cm2 }}
      Weight per area, g/cm², 5 decimals.
      e.g. 0.45446
  {{ grams_per_in2 }}
      Weight per area, g/in², 5 decimals.
      e.g. 2.93200
  {{ calculated_at }}
      When Calculate was pressed.
      e.g. 2026-09-28 10:15
  {{ created_at }}
      When the packing list was created.
      e.g. 2026-09-28 10:20
  {{ app_version }}
      TallyCraft version.
      e.g. 0.4.0
  {{ shop_record }}
      The whole small-print shop record in one line.
      e.g. Calibration: … Calculated 2026-09-28 10:15. Packing list created 2026-09-28 10:20. TallyCraft 0.4.0.

EACH PART (P.…)
---------------
  {{ p.picture }}
      Drawing of the part (cut lines solid, engrave lines light), fitted to
      the Picture column.
      e.g. (image)
  {{ p.dimensions }}
      Bounding box size.
      e.g. 14.500 × 14.250 in
  {{ p.name }}
      Part name (file name without .dxf).
      e.g. XL v1 - Main Box - Front Panel v2 - x3
  {{ p.marker }}
      Footnote marker for unmeasured parts (" *1"); empty otherwise.
      e.g.  *1
  {{ p.counts }}
      This part's count in each kit column, for {%tc for c in p.counts %} {{
      c }} {%tc endfor %}; "—" if a kit doesn't use it.
      e.g. 2, 2, —
  {{ p.total_count }}
      Count across every kit in the order.
      e.g. 4
  {{ p.weight_per_piece }}
      Grams per piece, 2 decimals; "—" if unmeasured.
      e.g. 423.64
  {{ p.total_weight }}
      Grams for all of this part, 2 decimals; "—" if unmeasured.
      e.g. 1,694.58
  {{ p.skipped }}
      True if the part couldn't be measured.
      e.g. False
  {{ p.reason }}
      Why it couldn't be measured; empty otherwise.
      e.g. The outline has a gap…

EACH FOOTNOTE (F.…)
-------------------
  {{ f.marker }}
      The footnote marker.
      e.g. *1
  {{ f.name }}
      Part name.
      e.g. Broken gap
  {{ f.reason }}
      Why it couldn't be measured.
      e.g. The outline has a gap…

<<TEMPLATE FIELDS END>>


COLORS: CUT vs ENGRAVE (and LightBurn files)
--------------------------------------------
  Only lines drawn in BLACK count as cut lines. Black here means ACI color 7
  (the black/white color that SolidWorks and LightBurn exports use) or true
  color RGB 0,0,0. Lines in any other color are treated as engraving: they
  appear in the preview and on packing lists (thin and light) but don't
  affect the weight, and never cause gap errors.
  File > Settings... > "Cut colors" can add more colors.

  If a file has no black lines at all, you get an Error ("No cut (black)
  lines found") instead of a weight of zero.

  LightBurn DXF exports don't say which units they use, but they're always
  millimeters, so TallyCraft assumes mm for them (and for any unitless file
  far too big to be inches), with a note. You can still change the Units.


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
