"""Dialogs for packing lists and shop settings (SPEC §9). No calculation here."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from .calc import format_lb_oz, kit_cell
from .packing import calibration_text, default_filename, parse_order_date, part_name, stamp


class _Modal(tk.Toplevel):
    def __init__(self, parent, title: str):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(True, True)
        self.result = None
        self.body = ttk.Frame(self, padding=12)
        self.body.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda e: self.destroy())

    def run(self, focus: tk.Widget | None = None):
        self.grab_set()
        (focus or self).focus_set()
        self.master.wait_window(self)
        return self.result


def _text(parent, height: int, initial: str = "") -> tk.Text:
    t = tk.Text(parent, height=height, width=46, wrap="word", relief="solid", borderwidth=1, font=("Segoe UI", 10))
    if initial:
        t.insert("1.0", initial)

    def newline(_event):
        # Enter always means "new line" in multi-line fields, and stops here so no
        # dialog or app-level Enter handling can ever act on it.
        t.insert("insert", "\n")
        t.see("insert")
        return "break"
    for seq in ("<Return>", "<KP_Enter>", "<Shift-Return>"):
        t.bind(seq, newline)
    return t


def _text_value(t: tk.Text) -> str:
    return t.get("1.0", "end").strip()


# ============================================================================ create

class PackingDialog(_Modal):
    """Customer details for a new packing list. result: dict or None."""

    def __init__(self, parent, default_note: str, packing_dir: Path, items: str, skipped_count: int,
                 prefill: dict | None = None):
        """prefill: customer details to start from (e.g. imported from Etsy); still editable."""
        super().__init__(parent, "Create Packing List")
        prefill = prefill or {}
        b = self.body
        b.columnconfigure(1, weight=1)
        self.name = tk.StringVar(value=prefill.get("name", ""))
        self.order_no = tk.StringVar(value=prefill.get("etsy_order", ""))
        self.order_date = tk.StringVar(value=prefill.get("order_date") or date.today().isoformat())
        ttk.Label(b, text=f"Items: {items}", style="Hint.TLabel", wraplength=460).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(b, text="Customer name *").grid(row=1, column=0, sticky="w", padx=(0, 8))
        name_entry = ttk.Entry(b, textvariable=self.name, width=40)
        name_entry.grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Label(b, text="Shipping address").grid(row=2, column=0, sticky="nw", padx=(0, 8), pady=3)
        self.address = _text(b, 4, prefill.get("address", ""))
        self.address.grid(row=2, column=1, sticky="nsew", pady=3)
        ttk.Label(b, text="Enter adds a new line.", style="Hint.TLabel").grid(row=2, column=0, sticky="sw",
                                                                             padx=(0, 8), pady=3)
        ttk.Label(b, text="Etsy order number").grid(row=3, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(b, textvariable=self.order_no, width=24).grid(row=3, column=1, sticky="w", pady=3)
        ttk.Label(b, text="Order date").grid(row=4, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(b, textvariable=self.order_date, width=14).grid(row=4, column=1, sticky="w", pady=3)
        ttk.Label(b, text="Note to customer").grid(row=5, column=0, sticky="nw", padx=(0, 8), pady=3)
        self.note = _text(b, 3, default_note)
        self.note.grid(row=5, column=1, sticky="nsew", pady=3)
        ttk.Label(b, text="* required. Everything else is optional.", style="Hint.TLabel").grid(
            row=6, column=1, sticky="w")
        if skipped_count:
            ttk.Label(b, text=f"Note: {skipped_count} part(s) couldn't be measured. They'll be listed, but their "
                              "weight isn't in the total.", style="Error.TLabel", wraplength=460).grid(
                row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.where = ttk.Label(b, text="", style="Hint.TLabel", wraplength=460)
        self.where.grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.error = ttk.Label(b, text="", style="Error.TLabel", wraplength=460)
        self.error.grid(row=9, column=0, columnspan=2, sticky="w")
        btns = ttk.Frame(b)
        btns.grid(row=10, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Create PDF", command=self._ok, default="active").pack(side="right", padx=6)
        b.rowconfigure(2, weight=1)
        self._packing_dir = packing_dir
        for v in (self.name, self.order_no, self.order_date):
            v.trace_add("write", lambda *_: self._update_where())
        self._update_where()
        self._name_entry = name_entry

    def _update_where(self):
        base = default_filename(self.order_date.get(), self.name.get() or "<customer>", self.order_no.get())
        self.where.configure(text=f"Will be saved in {self._packing_dir.name}\\ as \"{base}.pdf\" (+ .json record)")

    def _ok(self):
        problems = []
        if not self.name.get().strip():
            problems.append("Customer name is required.")
        order_date = ""
        if self.order_date.get().strip():
            try:
                order_date = parse_order_date(self.order_date.get())
            except ValueError as exc:
                problems.append(str(exc))
        if problems:
            self.error.configure(text="\n".join(problems))
            return
        address = _text_value(self.address)
        if address and "\n" not in address and "," not in address and not messagebox.askyesno(
                "Create Packing List",
                f"The shipping address is only one line:\n\n{address}\n\nIs that the complete address? "
                "(Press Enter in the address box for each new line.)", parent=self):
            self.address.focus_set()
            self.address.mark_set("insert", "end")
            return
        self.result = {"name": self.name.get().strip(), "address": address,
                       "etsy_order": self.order_no.get().strip(), "order_date": order_date,
                       "note": _text_value(self.note)}
        self.destroy()

    def run(self):
        return super().run(self._name_entry)


# ============================================================================ view

class PackingViewer(tk.Toplevel):
    """Read-only view of a saved packing list record, with Re-print PDF."""

    def __init__(self, parent, record: dict, json_path: Path, on_reprint):
        super().__init__(parent)
        cust, res = record["customer"], record["results"]
        self.title(f"Packing list — {json_path.stem}")
        self.geometry("980x640")
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        ttk.Label(outer, text="Read-only record of a shipment. Re-print uses this record (not the current DXF "
                              "files) and your current template.", style="Hint.TLabel").grid(row=0, column=0,
                                                                                            sticky="w")
        info = tk.Text(outer, height=9, wrap="word", relief="solid", borderwidth=1, font=("Segoe UI", 9),
                       background="#fafafa")
        total = res.get("total_g") or 0.0
        lines = [f"Customer: {cust.get('name', '')}"]
        if cust.get("address"):
            lines.append("Ship to: " + cust["address"].replace("\n", ", "))
        lines.append(f"Etsy order #: {cust.get('etsy_order') or '—'}     Order date: {cust.get('order_date') or '—'}"
                     f"     Created: {stamp(record.get('created_at'))}")
        lines.append(f"Items ordered: {record['order'].get('items_ordered', '')}")
        lines.append(f"Total shipping weight: {format_lb_oz(total)} ({total:,.1f} g)")
        if res.get("skipped_count"):
            lines.append(f"WARNING: total excludes {res['skipped_count']} part(s) that could not be measured.")
        if cust.get("note"):
            lines.append(f"Note to customer: {cust['note']}")
        lines.append(calibration_text(record["calibration"]) +
                     f" Calculated {stamp(record.get('calculated_at'))}. TallyCraft {record.get('app_version', '')}.")
        info.insert("1.0", "\n".join(lines))
        info.configure(state="disabled")
        info.grid(row=1, column=0, sticky="ew", pady=(6, 8))

        kits = res.get("kit_labels") or []
        cols = ["part"] + [f"k{i}" for i in range(len(kits))] + ["count", "per", "total"]
        frame = ttk.Frame(outer)
        frame.grid(row=2, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        heads = ["Part"] + kits + ["Total Count", "Weight per piece (g)", "Item Total (g)"]
        head_font = tkfont.nametofont("TkHeadingFont")
        for key, title in zip(cols, heads):
            tree.heading(key, text=title)
            width = 260 if key == "part" else max(90, head_font.measure(title) + 24)  # headings never cut off
            tree.column(key, width=width, anchor="w" if key == "part" else "center", stretch=False)
        tree.tag_configure("skipped", foreground="#9a1b1b", background="#f6f0f0")
        for line in res["lines"]:
            per = "—" if line.get("weight_per_piece_g") is None else f"{line['weight_per_piece_g']:,.2f}"
            tot = "—" if line.get("item_total_g") is None else f"{line['item_total_g']:,.2f}"
            counts = [kit_cell(c) for c in (list(line.get("kit_counts") or []) + [None] * len(kits))[:len(kits)]]
            tree.insert("", "end", values=(part_name(line["name"]), *counts, line.get("total_count", ""), per, tot),
                        tags=("skipped",) if line.get("skipped") else ())
        ysb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")

        btns = ttk.Frame(outer)
        btns.grid(row=3, column=0, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Re-print PDF", command=lambda: on_reprint(record, json_path, self),
                   default="active").pack(side="right", padx=6)
        self.tree = tree
        self.info = info


# ============================================================================ settings

class SettingsDialog(_Modal):
    """Shop details, packing-list template, cut colors, and Etsy. result: dict of settings, or None."""

    def __init__(self, parent, settings: dict, storage=None, show_help=None, etsy=None):
        super().__init__(parent, "Settings")
        self.storage = storage
        b = self.body
        b.columnconfigure(1, weight=1)
        self.shop = tk.StringVar(value=settings.get("shop_name") or "")
        self.logo = tk.StringVar(value=settings.get("logo_path") or "")
        self.template = tk.StringVar(value=settings.get("template_path") or "")
        from .pdf_convert import ENGINES, find_soffice
        self._engines = ENGINES
        self.engine = tk.StringVar(value=ENGINES.get(settings.get("pdf_engine", "auto"), "Automatic"))
        from .packing_docx import DIMENSION_UNITS
        self._dim_units = DIMENSION_UNITS
        self.dims = tk.StringVar(value=DIMENSION_UNITS.get(settings.get("dimension_units", "in"), "Inches"))

        ttk.Label(b, text="PACKING LISTS", style="Hint.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(b, text="Shop name").grid(row=1, column=0, sticky="w", padx=(0, 8))
        entry = ttk.Entry(b, textvariable=self.shop, width=44)
        entry.grid(row=1, column=1, columnspan=2, sticky="ew", pady=3)
        ttk.Label(b, text="Logo (PNG/JPG)").grid(row=2, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(b, textvariable=self.logo, width=44, state="readonly").grid(row=2, column=1, sticky="ew", pady=3)
        lb = ttk.Frame(b)
        lb.grid(row=2, column=2, sticky="w", padx=(6, 0))
        ttk.Button(lb, text="Browse…", command=self._browse_logo).pack(side="left")
        ttk.Button(lb, text="Clear", command=lambda: self.logo.set("")).pack(side="left", padx=(4, 0))
        ttk.Label(b, text="Default note to customer").grid(row=3, column=0, sticky="nw", padx=(0, 8), pady=3)
        self.note = _text(b, 3, settings.get("default_note") or "")
        self.note.grid(row=3, column=1, columnspan=2, sticky="nsew", pady=3)

        ttk.Label(b, text="Word template").grid(row=4, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(b, textvariable=self.template, width=44, state="readonly").grid(row=4, column=1, sticky="ew",
                                                                                pady=3)
        ttk.Button(b, text="Browse…", command=self._browse_template).grid(row=4, column=2, sticky="w", padx=(6, 0))
        tb = ttk.Frame(b)
        tb.grid(row=5, column=1, columnspan=2, sticky="w")
        ttk.Button(tb, text="Restore default template", command=self._restore_template).pack(side="left")
        if show_help:
            ttk.Button(tb, text="Template Help", command=show_help).pack(side="left", padx=(6, 0))
        ttk.Label(b, text="Edit the template in Word to change how packing lists look. Your edited file is never "
                          "replaced.", style="Hint.TLabel", wraplength=440).grid(row=6, column=1, columnspan=2,
                                                                                sticky="w", pady=(2, 4))
        ttk.Label(b, text="Make PDFs with").grid(row=7, column=0, sticky="w", padx=(0, 8))
        engine_box = ttk.Frame(b)
        engine_box.grid(row=7, column=1, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Combobox(engine_box, textvariable=self.engine, values=list(ENGINES.values()), state="readonly",
                     width=14).pack(side="left")
        dims_box = ttk.Frame(b)
        ttk.Label(b, text="Show dimensions in").grid(row=8, column=0, sticky="w", padx=(0, 8))
        dims_box.grid(row=8, column=1, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Combobox(dims_box, textvariable=self.dims, values=list(DIMENSION_UNITS.values()), state="readonly",
                     width=20).pack(side="left")
        ttk.Label(dims_box, text="  (the size printed under each part picture)", style="Hint.TLabel").pack(side="left")
        lo = "LibreOffice found" if find_soffice() else "LibreOffice not found"
        ttk.Label(engine_box, text=f"  Automatic = LibreOffice if installed, otherwise Word ({lo}).",
                  style="Hint.TLabel").pack(side="left")

        ttk.Label(b, text="DXF FILES", style="Hint.TLabel").grid(row=9, column=0, columnspan=3, sticky="w")
        ttk.Label(b, text="Cut colors").grid(row=10, column=0, sticky="nw", padx=(0, 8), pady=3)
        self.colors = _text(b, 3, "\n".join(settings.get("cut_colors") or ["ACI 7", "RGB 0,0,0"]))
        self.colors.configure(width=20)
        self.colors.grid(row=10, column=1, sticky="w", pady=3)
        ttk.Label(b, text="One per line: an ACI number (ACI 7) or R,G,B (RGB 0,0,0). Lines in these colors are "
                          "cut and measured; every other color is engrave-only (drawn, not weighed). Default: "
                          "black only.", style="Hint.TLabel", wraplength=440).grid(row=11, column=1, columnspan=2,
                                                                                  sticky="w")
        self.etsy = None
        if etsy is not None:
            from .etsy_ui import EtsySettings
            self.etsy = EtsySettings(self, b, 12, etsy, settings)  # rows 12-17
        self.error = ttk.Label(b, text="", style="Error.TLabel", wraplength=440)
        self.error.grid(row=18, column=0, columnspan=3, sticky="w", pady=(6, 0))
        btns = ttk.Frame(b)
        btns.grid(row=19, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Save", command=self._ok, default="active").pack(side="right", padx=6)
        self._entry = entry

    def _browse_logo(self):
        path = filedialog.askopenfilename(parent=self, title="Choose a logo image",
                                          filetypes=[("Images", "*.png *.jpg *.jpeg"), ("All files", "*.*")])
        if path:
            self.logo.set(path)

    def _relative(self, path: Path) -> str:
        """Store templates inside the TallyCraft folder relative to it, so the folder can move."""
        if self.storage is not None:
            try:
                return Path(path).resolve().relative_to(self.storage.root.resolve()).as_posix()
            except ValueError:
                pass
        return str(path)

    def _browse_template(self):
        start = self.storage.templates_dir if self.storage is not None else None
        path = filedialog.askopenfilename(parent=self, title="Choose a packing list template",
                                          initialdir=str(start) if start else None,
                                          filetypes=[("Word documents", "*.docx"), ("All files", "*.*")])
        if path:
            self.template.set(self._relative(Path(path)))

    def _restore_template(self):
        if self.storage is None:
            return
        try:
            new = self.storage.restore_default_template()
        except Exception as exc:
            messagebox.showerror("Restore default template", str(exc), parent=self)
            return
        if messagebox.askyesno("Restore default template",
                               f"A fresh copy of the default template was saved as:\n{new}\n\nYour current template "
                               "was not changed.\n\nUse the fresh copy for packing lists now?", parent=self):
            self.template.set(self._relative(new))

    def _ok(self):
        from .dxf_geometry import parse_color_spec
        problems = []
        logo = self.logo.get().strip()
        if logo:
            problem = check_logo(logo)
            if problem:
                problems.append(problem)
        colors = [line.strip() for line in _text_value(self.colors).splitlines() if line.strip()]
        if not colors:
            problems.append("List at least one cut color (black is ACI 7).")
        for c in colors:
            try:
                parse_color_spec(c)
            except ValueError as exc:
                problems.append(f"Cut colors: {exc}")
        template = self.template.get().strip()
        if template and not template.lower().endswith(".docx"):
            problems.append("The packing list template must be a Word .docx file.")
        if self.etsy is not None:
            try:
                self.etsy.save_keys()
            except OSError as exc:
                problems.append(f"The Etsy keys couldn't be saved ({exc.strerror}).")
        if problems:
            self.error.configure(text="\n".join(problems))
            return
        engine = next((k for k, v in self._engines.items() if v == self.engine.get()), "auto")
        dims = next((k for k, v in self._dim_units.items() if v == self.dims.get()), "in")
        self.result = {"shop_name": self.shop.get().strip(), "logo_path": logo or None,
                       "default_note": _text_value(self.note), "cut_colors": colors,
                       "template_path": template or "templates/packing_list_template.docx", "pdf_engine": engine,
                       "dimension_units": dims}
        if self.etsy is not None:
            self.result.update(self.etsy.values())
        self.destroy()

    def run(self):
        return super().run(self._entry)


class TemplateHelp(tk.Toplevel):
    """Every placeholder the packing list template can use (same list as docs/TEMPLATE_FIELDS.md)."""

    def __init__(self, parent, template_path: Path | None = None):
        super().__init__(parent)
        from .packing_docx import field_reference_text
        self.title("Packing List Template Fields")
        self.geometry("760x640")
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        where = f"Your template: {template_path}" if template_path else ""
        ttk.Label(outer, text="Edit your template in Microsoft Word. Placeholders below are filled in by TallyCraft. "
                              + where, style="Hint.TLabel", wraplength=720).grid(row=0, column=0, sticky="w")
        text = tk.Text(outer, wrap="word", font=("Consolas", 10), relief="solid", borderwidth=1)
        ysb = ttk.Scrollbar(outer, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=ysb.set)
        text.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        ysb.grid(row=1, column=1, sticky="ns", pady=(6, 0))
        text.insert("1.0", field_reference_text())
        text.configure(state="disabled")
        btns = ttk.Frame(outer)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Copy all", command=lambda: (self.clipboard_clear(),
                                                           self.clipboard_append(field_reference_text()))
                   ).pack(side="right", padx=6)
        self.text = text


def check_logo(path: str) -> str:
    """"" if `path` is a usable PNG/JPG, otherwise a plain-language problem."""
    if Path(path).suffix.lower() not in (".png", ".jpg", ".jpeg"):
        return "The logo must be a PNG or JPG image."
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
    except FileNotFoundError:
        return f"The logo file wasn't found: {path}"
    except Exception:
        return "That file couldn't be read as a PNG or JPG image."
    return ""


def confirm_skipped(parent, skipped) -> bool:
    listing = "\n".join(f"  • {part_name(s.name)} (×{s.count}): {s.reason}" for s in skipped)
    return messagebox.askyesno(
        "Create Packing List — unmeasured parts",
        f"{len(skipped)} part(s) could not be measured:\n\n{listing}\n\nThey will still be listed on the packing "
        "list (they go in the box), with \"—\" for weight, and the total weight will say it excludes them.\n\n"
        "Create the packing list anyway?", icon="warning", parent=parent)
