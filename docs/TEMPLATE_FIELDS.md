# Packing list template fields

<!-- Generated from src/tallycraft/packing_docx.py (FIELDS). Run `python tools/make_template.py --docs` after changing fields. -->

TallyCraft fills a Word template (`templates/packing_list_template.docx`) using [docxtpl](https://docxtpl.readthedocs.io/) placeholders. Edit the template in Word; keep the placeholders (including their `{{ }}` / `{% %}` brackets) intact.

**Required:** The parts table loop ({%tr for p in parts %} … {%tr endfor %}) and the total weight ({{ total_weight_lb_oz }} or {{ total_weight_g }}) must be in the template.

**Tags:** `{{ name }}` inserts a value. `{%p if … %}` / `{%p endif %}` show or hide whole paragraphs. `{%tr for … %}` / `{%tr endfor %}` repeat table rows. `{%tc for … %}` / `{%tc endfor %}` repeat table columns. Each `{%tr %}` / `{%tc %}` / `{%p %}` tag must sit alone in its own row / cell / paragraph.

**Column widths:** keep the parts table's Alt Text set to `TallyCraft parts table` (Word: right-click the table > Table Properties > Alt Text). TallyCraft then keeps your column widths and shares the remaining width among the kit columns.

## Shop

| Placeholder | Contains | Example |
|---|---|---|
| `{{ shop_name }}` | Your shop name (File > Settings). Empty if not set. | Bun Homes Co. |
| `{{ shop_logo }}` | Your logo image (File > Settings), 0.8 in tall. Empty if not set. Put it on its own line. | (image) |
| `{{ packing_date }}` | The date the packing list was created. | 2026-09-28 |

## Order and customer

| Placeholder | Contains | Example |
|---|---|---|
| `{{ customer_name }}` | Customer name (always filled in). | Jordan Rivera |
| `{{ customer_address }}` | Shipping address; its line breaks are kept. Empty if not entered. | 123 Maple Street / Springfield, IL 62704 |
| `{{ etsy_order_number }}` | Etsy order number. Empty if not entered. | 3141592653 |
| `{{ order_date }}` | Order date. Empty if not entered. | 2026-09-27 |
| `{{ items_ordered }}` | The packages in the order with quantities. | 2x XL Standard Box, 1x XL Tunnel + Ramp |
| `{{ note_to_customer }}` | The note to the customer. Empty if none. | Thank you for your order! |
| `{{ footer_reference }}` | For the page footer: "Etsy order #…", or "Packing list — <customer>" if there's no order number. | Etsy order #3141592653 |

## Weight

| Placeholder | Contains | Example |
|---|---|---|
| `{{ total_weight_lb_oz }}` | Total shipping weight in pounds and ounces (measured parts). | 4 lb 14.9 oz |
| `{{ total_weight_g }}` | Total shipping weight in grams, 1 decimal, no unit. | 2,237.2 |
| `{{ unmeasured_count }}` | How many parts couldn't be measured (0 if none). | 1 |
| `{{ unmeasured_warning }}` | A warning sentence when parts couldn't be measured; empty otherwise. Use with {%p if unmeasured_warning %} … {%p endif %}. | WARNING: Total weight excludes 1 part that could not be measured (marked * below). It still goes in the box. |

## Parts table

| Placeholder | Contains | Example |
|---|---|---|
| `{{ parts }}` | The parts table rows. Loop over them with {%tr for p in parts %} … {%tr endfor %}; each p has the p.… fields below. | (list) |
| `{{ kit_headers }}` | Kit column headings, for the column loop {%tc for h in kit_headers %} {{ h }} {%tc endfor %}. Full kit names, "Kit 1…", or one per package, depending on what fits. | XL Standard Box (1 of 2), XL Standard Box (2 of 2) |
| `{{ kit_legend }}` | Explains short kit headings ("Kit 1 = …"); empty when full names fit. | Kit columns: Kit 1 = XL Standard Box (1 of 4); … |
| `{{ kit_totals }}` | Totals-row values for the kit columns (same column loop). | 28, 28, 9 |
| `{{ total_count }}` | Totals row: all parts across every kit. | 65 |
| `{{ total_weight_measured }}` | Totals row: total weight in grams, 2 decimals (measured parts). | 12,564.18 |
| `{{ total_label }}` | Totals row label: "Total", or "Total (measured parts)" when some couldn't be measured. | Total |
| `{{ footnotes }}` | One per unmeasured part, for {%p for f in footnotes %} … {%p endfor %}; each f has f.marker, f.name, f.reason. | (list) |

## Shop record

| Placeholder | Contains | Example |
|---|---|---|
| `{{ calibration_method }}` | "Reference piece" or "Control sample". | Reference piece |
| `{{ calibration_details }}` | Full calibration sentence (method, values, ratio, preset). | Calibration: control sample 4 × 2 in, weight 23.456 g → 0.45446 g/cm² (2.93200 g/in²). |
| `{{ calibration_preset }}` | Calibration preset name, if the values still match it. Empty otherwise. | DixiePly 120526 |
| `{{ grams_per_cm2 }}` | Weight per area, g/cm², 5 decimals. | 0.45446 |
| `{{ grams_per_in2 }}` | Weight per area, g/in², 5 decimals. | 2.93200 |
| `{{ calculated_at }}` | When Calculate was pressed. | 2026-09-28 10:15 |
| `{{ created_at }}` | When the packing list was created. | 2026-09-28 10:20 |
| `{{ app_version }}` | TallyCraft version. | 0.4.0 |
| `{{ shop_record }}` | The whole small-print shop record in one line. | Calibration: … Calculated 2026-09-28 10:15. Packing list created 2026-09-28 10:20. TallyCraft 0.4.0. |

## Each part (p.…)

| Placeholder | Contains | Example |
|---|---|---|
| `{{ p.picture }}` | Drawing of the part (cut lines solid, engrave lines light), fitted to the Picture column. | (image) |
| `{{ p.dimensions }}` | Bounding box size. | 14.500 × 14.250 in |
| `{{ p.name }}` | Part name (file name without .dxf). | XL v1 - Main Box - Front Panel v2 - x3 |
| `{{ p.marker }}` | Footnote marker for unmeasured parts (" *1"); empty otherwise. |  *1 |
| `{{ p.counts }}` | This part's count in each kit column, for {%tc for c in p.counts %} {{ c }} {%tc endfor %}; "—" if a kit doesn't use it. | 2, 2, — |
| `{{ p.total_count }}` | Count across every kit in the order. | 4 |
| `{{ p.weight_per_piece }}` | Grams per piece, 2 decimals; "—" if unmeasured. | 423.64 |
| `{{ p.total_weight }}` | Grams for all of this part, 2 decimals; "—" if unmeasured. | 1,694.58 |
| `{{ p.skipped }}` | True if the part couldn't be measured. | False |
| `{{ p.reason }}` | Why it couldn't be measured; empty otherwise. | The outline has a gap… |

## Each footnote (f.…)

| Placeholder | Contains | Example |
|---|---|---|
| `{{ f.marker }}` | The footnote marker. | *1 |
| `{{ f.name }}` | Part name. | Broken gap |
| `{{ f.reason }}` | Why it couldn't be measured. | The outline has a gap… |

