"""Tkinter/ttk user interface. Holds no geometry or math — see dxf_geometry,
pieces, calc, and storage for that."""

from __future__ import annotations

import os
import sys
import traceback
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import APP_NAME, __version__
from .calc import (LABEL_TO_UNIT, UNIT_LABELS, PieceInput, calculate, format_lb_oz, parse_positive,
                   validate_control)
from .messages import Level
from .pieces import PieceRow
from .storage import PresetError, Storage

STATUS_TEXT = {Level.OK: "✔ OK", Level.INFO: "ℹ Info", Level.WARNING: "⚠ Warning", Level.ERROR: "✖ Error"}
ROW_TAGS = {Level.OK: "ok", Level.INFO: "info", Level.WARNING: "warning", Level.ERROR: "error"}
PIECE_COLUMNS = [
    ("count", "Count", 60, "center"),
    ("file", "File Name", 230, "w"),
    ("units", "Units", 100, "center"),
    ("bbox", "Bounding Box (W × H)", 190, "center"),
    ("area", "Area", 140, "e"),
    ("modified", "Date Modified", 135, "center"),
    ("status", "Status", 100, "w"),
]
UNIT_CHOICES = [UNIT_LABELS["in"], UNIT_LABELS["mm"], UNIT_LABELS["unknown"]]


def resource_path(rel: str) -> Path:
    """Locate bundled files both from source and inside a PyInstaller exe."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / rel


# ============================================================================ helpers

class Tooltip:
    """Small hover popup that can be moved/retexted as the mouse moves."""

    def __init__(self, widget):
        self.widget = widget
        self.tip: tk.Toplevel | None = None
        self.text = None

    def show(self, text: str, x: int, y: int) -> None:
        if self.tip and self.text == text:
            self.tip.geometry(f"+{x + 16}+{y + 12}")
            return
        self.hide()
        self.text = text
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.geometry(f"+{x + 16}+{y + 12}")
        tk.Label(self.tip, text=text, justify="left", background="#ffffe8", relief="solid",
                 borderwidth=1, wraplength=520, padx=6, pady=4).pack()

    def hide(self) -> None:
        if self.tip:
            self.tip.destroy()
        self.tip = None
        self.text = None


def choose_from_list(parent, title: str, prompt: str, names: list[str]) -> str | None:
    """Modal list chooser. Returns the chosen name or None."""
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.transient(parent)
    dlg.resizable(False, True)
    result: list[str | None] = [None]
    ttk.Label(dlg, text=prompt, padding=(10, 10, 10, 4)).pack(anchor="w")
    frame = ttk.Frame(dlg, padding=(10, 0))
    frame.pack(fill="both", expand=True)
    lb = tk.Listbox(frame, height=min(14, max(5, len(names))), width=48, activestyle="dotbox")
    sb = ttk.Scrollbar(frame, orient="vertical", command=lb.yview)
    lb.configure(yscrollcommand=sb.set)
    lb.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    for n in names:
        lb.insert("end", n)
    if names:
        lb.selection_set(0)

    def ok(*_):
        sel = lb.curselection()
        if sel:
            result[0] = names[sel[0]]
            dlg.destroy()

    buttons = ttk.Frame(dlg, padding=10)
    buttons.pack(fill="x")
    ttk.Button(buttons, text="Cancel", command=dlg.destroy).pack(side="right")
    ttk.Button(buttons, text="Load", command=ok, default="active").pack(side="right", padx=6)
    lb.bind("<Double-Button-1>", ok)
    dlg.bind("<Return>", ok)
    dlg.bind("<Escape>", lambda *_: dlg.destroy())
    dlg.grab_set()
    lb.focus_set()
    parent.wait_window(dlg)
    return result[0]


# ============================================================================ app

class TallyCraftApp(tk.Tk):
    def __init__(self, storage: Storage | None = None):
        super().__init__()
        self.storage = storage or Storage()
        self.rows: dict[str, PieceRow] = {}
        self._iid_counter = 0
        self._editor: tk.Widget | None = None
        self._results_valid = False
        self._last_result = None
        self._startup_notes: list[str] = []

        self.title(f"{APP_NAME} {__version__}")
        self.geometry("1180x820")
        self.minsize(900, 640)
        try:
            self.iconbitmap(default=str(resource_path("assets/tallycraft.ico")))
        except tk.TclError:
            pass
        self._init_style()

        try:
            self.storage.ensure_folders()
        except OSError as exc:
            self._startup_notes.append(
                f"TallyCraft can't create its preset folders in {self.storage.root} ({exc}). "
                "Presets can't be saved until the TallyCraft folder is somewhere you can write to "
                "(for example Documents or the Desktop).")
        self.settings, warn = self.storage.load_settings()
        if warn:
            self._startup_notes.append(warn)

        self._build_menu()
        self._build_layout()
        self._refresh_control_presets()
        self._load_default_control()
        self.after(150, self._show_startup_notes)

    # ------------------------------------------------------------------ setup

    def _init_style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=24)
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Total.TLabel", font=("Segoe UI", 15, "bold"))
        style.configure("Stale.TLabel", foreground="#a15c00")
        style.configure("Error.TLabel", foreground="#b00020")
        style.configure("Hint.TLabel", foreground="#555555")
        style.configure("Accent.TButton", font=("Segoe UI", 11, "bold"), padding=(18, 6))
        style.map("Invalid.TEntry", fieldbackground=[("!disabled", "#ffe3e3")])

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        filem = tk.Menu(menubar, tearoff=False)
        filem.add_command(label="Import DXF Files…", command=self.import_files, accelerator="Ctrl+O")
        filem.add_separator()
        filem.add_command(label="Save Package Preset…", command=self.save_package)
        filem.add_command(label="Load Package Preset…", command=self.load_package)
        filem.add_separator()
        filem.add_command(label="Open TallyCraft Folder", command=self.open_data_folder)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=filem)
        helpm = tk.Menu(menubar, tearoff=False)
        helpm.add_command(label="How to Use (README)", command=self.open_readme)
        helpm.add_command(label=f"About {APP_NAME}", command=self.show_about)
        menubar.add_cascade(label="Help", menu=helpm)
        self.config(menu=menubar)
        self.bind_all("<Control-o>", lambda e: self.import_files())

    def _build_layout(self) -> None:
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=3)
        outer.rowconfigure(1, weight=2)

        self._build_pieces_section(outer).grid(row=0, column=0, sticky="nsew")
        bottom = ttk.Frame(outer)
        bottom.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        bottom.columnconfigure(1, weight=1)
        bottom.rowconfigure(0, weight=1)
        self._build_control_section(bottom).grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        self._build_results_section(bottom).grid(row=0, column=1, sticky="nsew")

        self.statusbar = ttk.Label(self, text="Ready. Start by importing DXF files.", anchor="w",
                                   padding=(10, 3), relief="sunken")
        self.statusbar.pack(fill="x", side="bottom")

    # ------------------------------------------------------------------ pieces section

    def _build_pieces_section(self, parent) -> ttk.Frame:
        box = ttk.LabelFrame(parent, text=" 1. Package — pieces in one kit ", padding=8)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)

        bar = ttk.Frame(box)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Button(bar, text="Import DXF…", command=self.import_files).pack(side="left")
        ttk.Button(bar, text="Re-read Selected", command=self.reread_selected).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Remove Selected", command=self.remove_selected).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Clear All", command=self.clear_rows).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Load Package Preset…", command=self.load_package).pack(side="right")
        ttk.Button(bar, text="Save Package Preset…", command=self.save_package).pack(side="right", padx=(0, 6))

        cols = [c[0] for c in PIECE_COLUMNS]
        self.tree = ttk.Treeview(box, columns=cols, show="headings", selectmode="extended")
        for key, title, width, anchor in PIECE_COLUMNS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor=anchor, stretch=key in ("file", "bbox"))
        self.tree.tag_configure("error", background="#fde2e2")
        self.tree.tag_configure("warning", background="#fff4cc")
        self.tree.tag_configure("info", background="#ffffff")
        self.tree.tag_configure("ok", background="#ffffff")
        ysb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ysb.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        ysb.grid(row=1, column=1, sticky="ns")

        ttk.Label(box, text="Double-click a Count or Units cell to change it. Hover over Status "
                            "(or select a row) to see details.", style="Hint.TLabel"
                  ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.details = tk.Text(box, height=4, wrap="word", relief="solid", borderwidth=1,
                               background="#fafafa", font=("Segoe UI", 9))
        self.details.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self._set_details("Select a row to see its details here.")

        self.tooltip = Tooltip(self.tree)
        self.tree.bind("<Double-Button-1>", self._on_tree_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Motion>", self._on_tree_motion)
        self.tree.bind("<Leave>", lambda e: self.tooltip.hide())
        self.tree.bind("<Delete>", lambda e: self.remove_selected())
        return box

    def _set_details(self, text: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def _new_iid(self) -> str:
        self._iid_counter += 1
        return f"r{self._iid_counter}"

    def _row_values(self, row: PieceRow):
        return (row.count, row.name, UNIT_LABELS.get(row.unit, "Unknown"), row.bbox_text(),
                row.area_text(), row.mtime_text(), STATUS_TEXT[row.status])

    def _add_row(self, row: PieceRow) -> str:
        iid = self._new_iid()
        self.rows[iid] = row
        self.tree.insert("", "end", iid=iid, values=self._row_values(row), tags=(ROW_TAGS[row.status],))
        return iid

    def _refresh_row(self, iid: str) -> None:
        row = self.rows[iid]
        self.tree.item(iid, values=self._row_values(row), tags=(ROW_TAGS[row.status],))
        if iid in self.tree.selection():
            self._on_tree_select()

    def _ordered_rows(self) -> list[PieceRow]:
        return [self.rows[i] for i in self.tree.get_children()]

    def _ignored_layers(self) -> list[str]:
        return [str(n) for n in self.settings.get("ignored_layer_names") or []]

    def import_files(self) -> None:
        self._close_editor()
        initial = self.settings.get("last_import_dir") or os.path.expanduser("~")
        paths = filedialog.askopenfilenames(parent=self, title="Import DXF files", initialdir=initial,
                                            filetypes=[("DXF files", "*.dxf *.DXF"), ("All files", "*.*")])
        if not paths:
            return
        self.settings["last_import_dir"] = os.path.dirname(paths[0])
        self._save_settings_quietly()

        existing = {os.path.normcase(os.path.abspath(r.path)) for r in self.rows.values()}
        skipped, added, problems = [], 0, 0
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            for i, p in enumerate(paths, 1):
                self._status(f"Reading {os.path.basename(p)} ({i} of {len(paths)})…")
                key = os.path.normcase(os.path.abspath(p))
                if key in existing:
                    skipped.append(os.path.basename(p))
                    continue
                row = PieceRow.load(p, self._ignored_layers())
                self._add_row(row)
                existing.add(key)
                added += 1
                problems += row.status >= Level.WARNING
        finally:
            self.config(cursor="")
        self._invalidate_results()
        msg = f"Imported {added} file(s)."
        if problems:
            msg += f" {problems} need attention — see the Status column."
        self._status(msg)
        if skipped:
            messagebox.showinfo(APP_NAME, "These files are already in the table and were not added again "
                                          "(change their Count instead):\n\n" + "\n".join(skipped), parent=self)

    def reread_selected(self) -> None:
        self._close_editor()
        sel = self.tree.selection()
        if not sel:
            self._status("Select one or more rows to re-read.")
            return
        for iid in sel:
            old = self.rows[iid]
            unit = old.unit if old.unit != old.parsed.header_unit else None
            new = PieceRow.load(old.path, self._ignored_layers(), unit=unit, count=old.count)
            self.rows[iid] = new
            self._refresh_row(iid)
        self._invalidate_results()
        self._status(f"Re-read {len(sel)} file(s) from disk.")

    def remove_selected(self) -> None:
        self._close_editor()
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.rows.pop(iid, None)
        self._set_details("Select a row to see its details here.")
        self._invalidate_results()

    def clear_rows(self) -> None:
        self._close_editor()
        if self.rows and not messagebox.askyesno(APP_NAME, "Remove all pieces from the table?", parent=self):
            return
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        self._set_details("Select a row to see its details here.")
        self._invalidate_results()

    # ---- tree interaction

    def _on_tree_select(self, *_):
        sel = self.tree.selection()
        if len(sel) == 1:
            self._set_details(self.rows[sel[0]].details_text())
        elif sel:
            self._set_details(f"{len(sel)} rows selected.")

    def _on_tree_motion(self, event):
        iid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if iid and col == f"#{len(PIECE_COLUMNS)}" and iid in self.rows:
            row = self.rows[iid]
            text = "\n".join(f"• [{m.level.label}] {m.text}" for m in row.messages) or "No problems found."
            self.tooltip.show(text, event.x_root, event.y_root)
        else:
            self.tooltip.hide()

    def _on_tree_double_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        iid = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not iid:
            return
        key = PIECE_COLUMNS[int(col[1:]) - 1][0]
        if key == "count":
            self._edit_count(iid, col)
        elif key == "units":
            self._edit_units(iid, col)
        return "break"

    def _place_editor(self, widget, iid, col):
        x, y, w, h = self.tree.bbox(iid, col)
        widget.place(in_=self.tree, x=x, y=y, width=w, height=h)
        widget.focus_set()
        self._editor = widget

    def _close_editor(self):
        if self._editor is not None:
            ed, self._editor = self._editor, None
            ed.destroy()

    def _edit_count(self, iid, col):
        self._close_editor()
        row = self.rows[iid]
        var = tk.StringVar(value=str(row.count))
        spin = ttk.Spinbox(self.tree, from_=1, to=9999, increment=1, textvariable=var, justify="center")

        def commit(*_):
            if self._editor is not spin:
                return
            text = var.get().strip()
            try:
                value = int(text)
                if value < 1:
                    raise ValueError
            except ValueError:
                self._close_editor()
                messagebox.showerror(APP_NAME, f"Count for {row.name} must be a whole number of 1 or more "
                                               f"(you entered \"{text}\"). It was left at {row.count}.", parent=self)
                return
            self._close_editor()
            if value != row.count:
                row.count = value
                self._refresh_row(iid)
                self._invalidate_results()

        spin.bind("<Return>", commit)
        spin.bind("<KP_Enter>", commit)
        spin.bind("<FocusOut>", commit)
        spin.bind("<Escape>", lambda e: self._close_editor())
        self._place_editor(spin, iid, col)
        spin.selection_range(0, "end")

    def _edit_units(self, iid, col):
        self._close_editor()
        row = self.rows[iid]
        var = tk.StringVar(value=UNIT_LABELS.get(row.unit, "Unknown"))
        combo = ttk.Combobox(self.tree, values=UNIT_CHOICES, textvariable=var, state="readonly")

        def commit(*_):
            if self._editor is not combo:
                return
            new = LABEL_TO_UNIT.get(var.get(), row.unit)
            self._close_editor()
            if new != row.unit:
                row.unit = new
                self._refresh_row(iid)
                self._invalidate_results()
                self._status(f"{row.name}: units changed to {UNIT_LABELS[new]} — size and area re-derived.")

        combo.bind("<<ComboboxSelected>>", commit)
        combo.bind("<Escape>", lambda e: self._close_editor())

        def focus_out(_):
            # The dropdown list takes focus while open; only close when focus truly left.
            def check():
                focused = str(self.focus_get() or "")
                if self._editor is combo and not focused.startswith(str(combo)):
                    self._close_editor()
            self.after(50, check)

        combo.bind("<FocusOut>", focus_out)
        self._place_editor(combo, iid, col)

        def post():
            if self._editor is combo:
                try:
                    combo.tk.call("ttk::combobox::Post", combo)
                except tk.TclError:
                    pass
        self.after(10, post)

    # ---- package presets

    def save_package(self) -> None:
        self._close_editor()
        rows = self._ordered_rows()
        if not rows:
            messagebox.showinfo(APP_NAME, "There are no pieces to save yet. Import some DXF files first.", parent=self)
            return
        name = simpledialog.askstring("Save Package Preset", "Name for this package (e.g. XL Complete Set):",
                                      parent=self)
        if name is None:
            return
        try:
            path = self.storage.package_path(name)
            if path.exists() and not messagebox.askyesno(
                    APP_NAME, f"A package preset named \"{name.strip()}\" already exists. Replace it?", parent=self):
                return
            pieces = [{"path": os.path.abspath(r.path), "units": r.unit, "count": r.count, "mtime": r.mtime}
                      for r in rows]
            self.storage.save_package(name, pieces)
        except PresetError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        self._status(f"Saved package preset \"{name.strip()}\" ({len(rows)} pieces).")

    def load_package(self) -> None:
        self._close_editor()
        entries = self.storage.list_packages()
        if not entries:
            messagebox.showinfo(APP_NAME, "No package presets have been saved yet.\n\n"
                                          f"They are stored in:\n{self.storage.package_dir}", parent=self)
            return
        chosen = choose_from_list(self, "Load Package Preset", "Choose a package preset:", [e.name for e in entries])
        if chosen is None:
            return
        entry = next(e for e in entries if e.name == chosen)
        try:
            data = self.storage.load_package(entry.path)
        except PresetError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        if self.rows and not messagebox.askyesno(
                APP_NAME, "Loading a package replaces the pieces currently in the table. Continue?", parent=self):
            return
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            for p in data["pieces"]:
                self._add_row(PieceRow.load(p["path"], self._ignored_layers(), unit=p["units"],
                                            count=p["count"], stored_mtime=p["mtime"]))
        finally:
            self.config(cursor="")
        self._invalidate_results()
        flagged = sum(1 for r in self.rows.values() if r.status >= Level.WARNING)
        msg = f"Loaded package \"{data['name']}\" ({len(data['pieces'])} pieces)."
        if flagged:
            msg += f" {flagged} need attention — see the Status column."
        self._status(msg)

    # ------------------------------------------------------------------ control section

    def _build_control_section(self, parent) -> ttk.Frame:
        box = ttk.LabelFrame(parent, text=" 2. Control sample — plywood batch ", padding=10)
        self.ctl_length = tk.StringVar()
        self.ctl_width = tk.StringVar()
        self.ctl_weight = tk.StringVar()
        self.ctl_unit = tk.StringVar(value="in")

        ttk.Label(box, text="Length").grid(row=0, column=0, sticky="w")
        self.ent_length = ttk.Entry(box, textvariable=self.ctl_length, width=14)
        self.ent_length.grid(row=0, column=1, sticky="w", pady=2)
        ttk.Label(box, text="Width").grid(row=1, column=0, sticky="w")
        self.ent_width = ttk.Entry(box, textvariable=self.ctl_width, width=14)
        self.ent_width.grid(row=1, column=1, sticky="w", pady=2)
        units = ttk.Frame(box)
        units.grid(row=0, column=2, rowspan=2, sticky="w", padx=(8, 0))
        ttk.Radiobutton(units, text="Inches", value="in", variable=self.ctl_unit).pack(anchor="w")
        ttk.Radiobutton(units, text="mm", value="mm", variable=self.ctl_unit).pack(anchor="w")
        ttk.Label(box, text="Weight (g)").grid(row=2, column=0, sticky="w")
        self.ent_weight = ttk.Entry(box, textvariable=self.ctl_weight, width=14)
        self.ent_weight.grid(row=2, column=1, sticky="w", pady=2)

        self.ratio_label = ttk.Label(box, text="", style="Hint.TLabel")
        self.ratio_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.control_error = ttk.Label(box, text="", style="Error.TLabel", wraplength=300, justify="left")
        self.control_error.grid(row=4, column=0, columnspan=3, sticky="w")

        ttk.Separator(box).grid(row=5, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Label(box, text="Control preset").grid(row=6, column=0, sticky="w")
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(box, textvariable=self.preset_var, state="readonly", width=24)
        self.preset_combo.grid(row=6, column=1, columnspan=2, sticky="ew", pady=2)
        btns = ttk.Frame(box)
        btns.grid(row=7, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Button(btns, text="Load", command=self.load_control_preset).pack(side="left")
        ttk.Button(btns, text="Save Control Preset…", command=self.save_control_preset).pack(side="left", padx=(6, 0))
        self.default_var = tk.BooleanVar()
        ttk.Checkbutton(box, text="Use this preset as default on startup", variable=self.default_var,
                        command=self._toggle_default).grid(row=8, column=0, columnspan=3, sticky="w", pady=(6, 0))

        self.preset_combo.bind("<<ComboboxSelected>>", lambda e: self._sync_default_checkbox())
        for v in (self.ctl_length, self.ctl_width, self.ctl_weight, self.ctl_unit):
            v.trace_add("write", lambda *_: self._on_control_changed())
        self._on_control_changed()
        return box

    def _on_control_changed(self) -> None:
        fields = ((self.ent_length, self.ctl_length, "Control Length"),
                  (self.ent_width, self.ctl_width, "Control Width"),
                  (self.ent_weight, self.ctl_weight, "Control Weight (g)"))
        problems = []
        for entry, var, label in fields:
            text = var.get()
            if not text.strip():
                entry.configure(style="TEntry")
                continue
            try:
                parse_positive(text, label)
                entry.configure(style="TEntry")
            except ValueError as exc:
                entry.configure(style="Invalid.TEntry")
                problems.append(str(exc))
        self.control_error.configure(text="\n".join(problems))
        sample, _ = validate_control(self.ctl_length.get(), self.ctl_width.get(), self.ctl_unit.get(),
                                     self.ctl_weight.get())
        if sample:
            gpc = sample.grams_per_cm2
            self.ratio_label.configure(text=f"Ratio: {gpc:.5f} g/cm²  ({gpc * 6.4516:.5f} g/in²)")
        else:
            self.ratio_label.configure(text="Enter length, width, and weight to see the g/area ratio.")
        self._invalidate_results()

    def _refresh_control_presets(self) -> None:
        names = [e.name for e in self.storage.list_controls()]
        self.preset_combo.configure(values=names)
        if self.preset_var.get() not in names:
            self.preset_var.set("")
        self._sync_default_checkbox()

    def _sync_default_checkbox(self) -> None:
        cur = self.preset_var.get()
        self.default_var.set(bool(cur) and cur == self.settings.get("default_control_preset"))

    def _toggle_default(self) -> None:
        name = self.preset_var.get()
        if self.default_var.get():
            if not name:
                self.default_var.set(False)
                messagebox.showinfo(APP_NAME, "Choose (or save) a control preset first, then tick this box.",
                                    parent=self)
                return
            self.settings["default_control_preset"] = name
            self._status(f"\"{name}\" will load automatically when TallyCraft starts.")
        else:
            if self.settings.get("default_control_preset") == name:
                self.settings["default_control_preset"] = None
            self._status("No control preset will load automatically on startup.")
        self._save_settings_quietly(show_errors=True)

    def _apply_control(self, data: dict) -> None:
        self.ctl_unit.set(data["unit"])
        self.ctl_length.set(data["length"])
        self.ctl_width.set(data["width"])
        self.ctl_weight.set(data["weight_g"])

    def load_control_preset(self) -> None:
        name = self.preset_var.get()
        if not name:
            messagebox.showinfo(APP_NAME, "Choose a control preset from the list first.", parent=self)
            return
        try:
            self._apply_control(self.storage.load_control(name))
        except PresetError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        self._sync_default_checkbox()
        self._status(f"Loaded control preset \"{name}\".")

    def save_control_preset(self) -> None:
        sample, errors = validate_control(self.ctl_length.get(), self.ctl_width.get(), self.ctl_unit.get(),
                                          self.ctl_weight.get())
        if errors:
            messagebox.showerror(APP_NAME, "Fix the control values before saving:\n\n• " + "\n• ".join(errors),
                                 parent=self)
            return
        name = simpledialog.askstring("Save Control Preset", "Name for this plywood batch (e.g. DixiePly 120526):",
                                      parent=self, initialvalue=self.preset_var.get())
        if name is None:
            return
        try:
            path = self.storage.control_path(name)
            if path.exists() and not messagebox.askyesno(
                    APP_NAME, f"A control preset named \"{name.strip()}\" already exists. Replace it?", parent=self):
                return
            self.storage.save_control(name, self.ctl_length.get(), self.ctl_width.get(), self.ctl_unit.get(),
                                      self.ctl_weight.get())
        except PresetError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        self._refresh_control_presets()
        self.preset_var.set(name.strip())
        self._sync_default_checkbox()
        self._status(f"Saved control preset \"{name.strip()}\".")

    def _load_default_control(self) -> None:
        name = self.settings.get("default_control_preset")
        if not name:
            return
        try:
            self._apply_control(self.storage.load_control(name))
            self.preset_var.set(name)
            self._sync_default_checkbox()
            self._status(f"Loaded default control preset \"{name}\".")
        except PresetError as exc:
            self._startup_notes.append(f"The default control preset couldn't be loaded: {exc}")

    # ------------------------------------------------------------------ results section

    def _build_results_section(self, parent) -> ttk.Frame:
        box = ttk.LabelFrame(parent, text=" 3. Results ", padding=10)
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)

        top = ttk.Frame(box)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Button(top, text="Calculate", style="Accent.TButton", command=self.calculate).pack(side="left")
        ttk.Button(top, text="Copy Results", command=self.copy_results).pack(side="left", padx=(8, 0))
        self.stale_label = ttk.Label(top, text="", style="Stale.TLabel")
        self.stale_label.pack(side="left", padx=(12, 0))

        cols = ("file", "per", "count", "total")
        self.results = ttk.Treeview(box, columns=cols, show="headings", height=6)
        for key, title, width, anchor in (("file", "File Name", 240, "w"), ("per", "Weight per piece (g)", 150, "e"),
                                          ("count", "Count", 70, "center"), ("total", "Item Total (g)", 130, "e")):
            self.results.heading(key, text=title)
            self.results.column(key, width=width, anchor=anchor, stretch=key == "file")
        ysb = ttk.Scrollbar(box, orient="vertical", command=self.results.yview)
        self.results.configure(yscrollcommand=ysb.set)
        self.results.grid(row=1, column=0, sticky="nsew")
        ysb.grid(row=1, column=1, sticky="ns")

        foot = ttk.Frame(box)
        foot.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(foot, text="Package Total:", style="Header.TLabel").pack(side="left")
        self.total_g_label = ttk.Label(foot, text="—", style="Total.TLabel")
        self.total_g_label.pack(side="left", padx=(10, 0))
        ttk.Label(foot, text="=", style="Header.TLabel").pack(side="left", padx=10)
        self.total_lb_label = ttk.Label(foot, text="—", style="Total.TLabel")
        self.total_lb_label.pack(side="left")
        return box

    def _invalidate_results(self) -> None:
        if getattr(self, "stale_label", None) is None:
            return
        if self._results_valid:
            self._results_valid = False
            self.stale_label.configure(text="Inputs changed — press Calculate again to update.")
            self.total_g_label.configure(foreground="#999999")
            self.total_lb_label.configure(foreground="#999999")

    def calculate(self) -> None:
        self._close_editor()
        rows = self._ordered_rows()
        if not rows:
            messagebox.showwarning(APP_NAME, "There are no pieces to calculate. Import DXF files first.", parent=self)
            return

        blocked = [r for r in rows if r.status == Level.ERROR]
        sample, control_errors = validate_control(self.ctl_length.get(), self.ctl_width.get(),
                                                  self.ctl_unit.get(), self.ctl_weight.get())
        if blocked or control_errors:
            parts = []
            if blocked:
                parts.append("These pieces have errors that must be fixed first:")
                for r in blocked:
                    first = next(m.text for m in r.messages if m.level == Level.ERROR)
                    parts.append(f"  • {r.name}: {first}")
            if control_errors:
                if parts:
                    parts.append("")
                parts.append("Control sample:")
                parts.extend(f"  • {e}" for e in control_errors)
            messagebox.showerror(f"{APP_NAME} — can't calculate yet", "\n".join(parts), parent=self)
            return

        warned = [r for r in rows if r.status == Level.WARNING]
        if warned:
            lines = []
            for r in warned:
                first = next(m.text for m in r.messages if m.level == Level.WARNING)
                lines.append(f"  • {r.name}: {first}")
            if not messagebox.askyesno(f"{APP_NAME} — please review",
                                       "These pieces have warnings:\n\n" + "\n".join(lines) +
                                       "\n\nCalculate anyway?", icon="warning", parent=self):
                return

        result = calculate([PieceInput(r.name, r.area_cm2, r.count) for r in rows], sample)
        self.results.delete(*self.results.get_children())
        for line in result.lines:
            self.results.insert("", "end", values=(line.name, f"{line.weight_per_piece_g:,.2f}", line.count,
                                                   f"{line.item_total_g:,.2f}"))
        self._last_result = result
        self.total_g_label.configure(text=f"{result.total_g:,.1f} g", foreground="")
        self.total_lb_label.configure(text=format_lb_oz(result.total_g), foreground="")
        self.stale_label.configure(text="")
        self._results_valid = True
        self._status(f"Calculated {len(rows)} piece type(s) at {datetime.now():%H:%M:%S}.")

    def copy_results(self) -> None:
        if not self._results_valid:
            messagebox.showinfo(APP_NAME, "Press Calculate first (results are missing or out of date).", parent=self)
            return
        r = self._last_result
        lines = ["File Name\tWeight per piece (g)\tCount\tItem Total (g)"]
        lines += [f"{l.name}\t{l.weight_per_piece_g:.2f}\t{l.count}\t{l.item_total_g:.2f}" for l in r.lines]
        lines.append(f"Package Total\t\t\t{r.total_g:.1f} g ({format_lb_oz(r.total_g)})")
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self._status("Results copied — paste them into a spreadsheet or email.")

    # ------------------------------------------------------------------ misc

    def _status(self, text: str) -> None:
        self.statusbar.configure(text=text)

    def _save_settings_quietly(self, show_errors: bool = False) -> None:
        try:
            self.storage.save_settings(self.settings)
        except PresetError as exc:
            if show_errors:
                messagebox.showerror(APP_NAME, f"Settings couldn't be saved: {exc}", parent=self)

    def _show_startup_notes(self) -> None:
        if self._startup_notes:
            messagebox.showwarning(APP_NAME, "\n\n".join(self._startup_notes), parent=self)
            self._startup_notes.clear()

    def open_data_folder(self) -> None:
        try:
            os.startfile(self.storage.root)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Couldn't open {self.storage.root} ({exc}).", parent=self)

    def open_readme(self) -> None:
        for candidate in (self.storage.root / "README.txt", resource_path("dist_template/README.txt")):
            if candidate.exists():
                try:
                    os.startfile(candidate)  # type: ignore[attr-defined]
                    return
                except OSError:
                    pass
        messagebox.showinfo(APP_NAME, "README.txt wasn't found next to TallyCraft.exe.", parent=self)

    def show_about(self) -> None:
        messagebox.showinfo(f"About {APP_NAME}",
                            f"{APP_NAME} {__version__}\n\nCalculates shipping weights for laser-cut plywood kits "
                            "from DXF files, using the weight-per-area of a control sample.\n\n"
                            f"Data folder:\n{self.storage.root}\n\nMIT License · github.com/jaerxion/TallyCraft",
                            parent=self)

    def report_callback_exception(self, exc, val, tb):  # noqa: D401 (Tk hook)
        """Top-level safety net: never crash, always explain."""
        details = "".join(traceback.format_exception(exc, val, tb))
        log = self.storage.root / "tallycraft_error.log"
        try:
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"\n=== {datetime.now().isoformat(timespec='seconds')} ===\n{details}")
            where = f"Details were saved to {log}."
        except OSError:
            where = ""
        messagebox.showerror(APP_NAME, f"Something unexpected went wrong: {val}\n\n"
                                       f"Your work in the window is still there. {where}", parent=self)


def main() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = TallyCraftApp()
    app.mainloop()
