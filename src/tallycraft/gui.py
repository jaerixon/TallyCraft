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
from tkinter import font as tkfont

from . import APP_NAME, __version__
from .calc import (LABEL_TO_UNIT, SKIPPED_LABEL, UNIT_LABELS, PieceInput, SkippedLine, calculate,
                   format_lb_oz, parse_positive, results_as_text, validate_control)
from .calibration import (MODE_CONTROL, MODE_REFERENCE, MODES, TIP as CAL_TIP, SavedReference, describe,
                          parse_positive_int, validate_reference)
from .messages import Level
from .pieces import PieceRow
from .preview import PiecePreview
from .storage import MAIN_SPLIT_MAX, MAIN_SPLIT_MIN, TEXT_SCALE_MAX, TEXT_SCALE_MIN, PresetError, Storage
from .table_sort import PIECE_SORT_KEYS, order_results, sort_pieces

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
RESULT_COLUMNS = [
    ("file", "File Name", 240, "w"),
    ("per", "Weight per piece (g)", 150, "e"),
    ("count", "Count", 70, "center"),
    ("total", "Item Total (g)", 130, "e"),
]
UNIT_CHOICES = [UNIT_LABELS["in"], UNIT_LABELS["mm"], UNIT_LABELS["unknown"]]

# Tk's Treeview only lets a column be dragged wider/narrower if a *stretchable*
# column lies to its right to absorb the difference; otherwise the drag snaps
# back. A blank stretchable filler column at the far right makes every real
# column resizable, and leaves user-set widths alone.
FILLER = "_fill"

SORT_ARROWS = {False: " ▲", True: " ▼"}

# View > Larger / Smaller Text steps (1.0 = default).
TEXT_SCALE_STEPS = [0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6, 1.8, 2.0, 2.25, 2.5]
# Named fonts the text-size setting scales: (base point size, weight).
BASE_FONTS = {
    "table": (9, "normal"),       # both tables' rows
    "heading": (9, "normal"),     # both tables' column headers
    "details": (9, "normal"),     # details pane
    "results_hdr": (11, "bold"),  # "Package Total:"
    "total": (15, "bold"),        # the totals themselves (stays proportionally larger)
    "incomplete": (11, "bold"),   # "Incomplete: N files skipped" badge
}


SAVED_KEY = "<saved>"  # reference dropdown entry for a preset's saved area (file not in this package)


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


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
        self._last_calibration_note = ""
        self._startup_notes: list[str] = []
        self._row_order: list[str] = []  # import order: used for calculation and presets
        self._piece_sort: tuple[str, bool] | None = None  # (column, descending); display only
        self._result_sort: tuple[str, bool] | None = None
        self._text_scale = 1.0

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

        self.fonts = {name: tkfont.Font(self, family="Segoe UI", size=size, weight=weight)
                      for name, (size, weight) in BASE_FONTS.items()}
        self._build_menu()
        self._build_layout()
        self._apply_text_scale(self.settings.get("text_scale", 1.0), save=False, announce=False)
        self._refresh_control_presets()
        self._load_default_control()
        self.after(150, self._show_startup_notes)

    # ------------------------------------------------------------------ setup

    def _init_style(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        # Treeview / heading / totals fonts and row height are set by _apply_text_scale.
        style.configure("Stale.TLabel", foreground="#a15c00")
        style.configure("Error.TLabel", foreground="#b00020")
        style.configure("Incomplete.TLabel", foreground="#ffffff", background="#b00020", padding=(8, 2))
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
        viewm = tk.Menu(menubar, tearoff=False)
        viewm.add_command(label="Larger Text", command=lambda: self.change_text_size(+1), accelerator="Ctrl+=")
        viewm.add_command(label="Smaller Text", command=lambda: self.change_text_size(-1), accelerator="Ctrl+-")
        viewm.add_command(label="Reset Text Size", command=lambda: self.change_text_size(0), accelerator="Ctrl+0")
        menubar.add_cascade(label="View", menu=viewm)
        helpm = tk.Menu(menubar, tearoff=False)
        helpm.add_command(label="How to Use (README)", command=self.open_readme)
        helpm.add_command(label=f"About {APP_NAME}", command=self.show_about)
        menubar.add_cascade(label="Help", menu=helpm)
        self.config(menu=menubar)
        self.bind_all("<Control-o>", lambda e: self.import_files())
        for seq in ("<Control-equal>", "<Control-plus>", "<Control-KP_Add>"):
            self.bind_all(seq, lambda e: self.change_text_size(+1))
        for seq in ("<Control-minus>", "<Control-KP_Subtract>"):
            self.bind_all(seq, lambda e: self.change_text_size(-1))
        for seq in ("<Control-Key-0>", "<Control-KP_0>", "<Control-KP_Insert>"):
            self.bind_all(seq, lambda e: self.change_text_size(0))

    def _build_layout(self) -> None:
        self.statusbar = ttk.Label(self, text="Ready. Start by importing DXF files.", anchor="w",
                                   padding=(10, 3), relief="sunken")
        self.statusbar.pack(fill="x", side="bottom")

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        # Top (pieces + details/preview) | bottom (calibration + results), with a draggable
        # divider between them whose position is remembered in settings.json.
        self.main_split = ttk.PanedWindow(outer, orient="vertical")
        self.main_split.pack(fill="both", expand=True)
        top = ttk.Frame(self.main_split, padding=(0, 0, 0, 5))
        top.columnconfigure(0, weight=1)
        top.rowconfigure(0, weight=1)
        self._build_pieces_section(top).grid(row=0, column=0, sticky="nsew")
        bottom = ttk.Frame(self.main_split, padding=(0, 5, 0, 0))
        bottom.columnconfigure(1, weight=1)
        bottom.rowconfigure(0, weight=1)
        self._build_control_section(bottom).grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        self._build_results_section(bottom).grid(row=0, column=1, sticky="nsew")
        self.main_split.add(top, weight=3)
        self.main_split.add(bottom, weight=2)
        self.main_split.bind("<ButtonRelease-1>", lambda e: self.after_idle(self._remember_split))
        self.after(120, self._restore_split)

    def _restore_split(self) -> None:
        frac = self.settings.get("main_split")
        if frac is None:
            return
        self.update_idletasks()
        height = self.main_split.winfo_height()
        if height > 50:
            self.main_split.sashpos(0, round(height * frac))

    def _remember_split(self) -> None:
        height = self.main_split.winfo_height()
        if height <= 50:
            return
        frac = min(MAIN_SPLIT_MAX, max(MAIN_SPLIT_MIN, self.main_split.sashpos(0) / height))
        if frac != self.settings.get("main_split"):
            self.settings["main_split"] = round(frac, 4)
            self._save_settings_quietly()

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

        # Table above; details + preview below, with a draggable divider between.
        panes = ttk.PanedWindow(box, orient="vertical")
        panes.grid(row=1, column=0, columnspan=2, sticky="nsew")
        table = ttk.Frame(panes)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        lower = ttk.Frame(panes)
        lower.columnconfigure(0, weight=1)
        lower.rowconfigure(1, weight=1)
        panes.add(table, weight=3)
        panes.add(lower, weight=2)

        cols = [c[0] for c in PIECE_COLUMNS] + [FILLER]
        self.tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="extended")
        for key, title, width, anchor in PIECE_COLUMNS:
            self.tree.heading(key, text=title)
            if key in PIECE_SORT_KEYS:
                self.tree.heading(key, command=lambda k=key: self.sort_pieces_by(k))
            self.tree.column(key, width=width, minwidth=30, anchor=anchor, stretch=False)
        self.tree.heading(FILLER, text="")
        self.tree.column(FILLER, width=1, minwidth=0, stretch=True)
        self.tree.tag_configure("error", background="#fde2e2")
        self.tree.tag_configure("warning", background="#fff4cc")
        self.tree.tag_configure("info", background="#ffffff")
        self.tree.tag_configure("ok", background="#ffffff")
        ysb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        xsb = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)  # wide columns / large text
        self.tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")

        ttk.Label(lower, text="Double-click a Count or Units cell to change it. Hover over Status "
                              "(or select a row) to see details.", style="Hint.TLabel"
                  ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(4, 0))
        # Details | preview, with a draggable vertical divider to trade width between them.
        side = ttk.PanedWindow(lower, orient="horizontal")
        side.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(4, 0))
        self.details = tk.Text(side, height=6, width=40, wrap="word", relief="solid", borderwidth=1,
                               background="#fafafa", font=self.fonts["details"])
        self.preview = PiecePreview(side, width=380, height=170)
        side.add(self.details, weight=3)
        side.add(self.preview, weight=2)
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
        """Append a row in import order. Callers re-apply any active sort afterwards."""
        iid = self._new_iid()
        self.rows[iid] = row
        self._row_order.append(iid)
        self.tree.insert("", "end", iid=iid, values=self._row_values(row), tags=(ROW_TAGS[row.status],))
        return iid

    def _forget_rows(self, iids) -> None:
        for iid in iids:
            if self.tree.exists(iid):
                self.tree.delete(iid)
            self.rows.pop(iid, None)
        gone = set(iids)
        self._row_order = [i for i in self._row_order if i not in gone]

    def _refresh_row(self, iid: str) -> None:
        row = self.rows[iid]
        self.tree.item(iid, values=self._row_values(row), tags=(ROW_TAGS[row.status],))
        self._apply_piece_sort()  # e.g. a Count edit while sorted by Count
        if iid in self.tree.selection():
            self._on_tree_select()
        if iid == getattr(self, "ref_iid", None):  # reference row's Units/area changed
            self._on_control_changed()

    def _ordered_rows(self) -> list[PieceRow]:
        """Rows in import order, whatever order the table is currently sorted in."""
        return [self.rows[i] for i in self._row_order]

    # ---- sorting (display order only)

    def sort_pieces_by(self, column: str) -> None:
        self._close_editor()
        desc = self._piece_sort is not None and self._piece_sort == (column, False)
        self._piece_sort = (column, desc)
        self._apply_piece_sort()

    def _apply_piece_sort(self) -> None:
        if self._piece_sort is None:
            ordered = list(self._row_order)
        else:
            col, desc = self._piece_sort
            ordered = sort_pieces([(i, self.rows[i]) for i in self._row_order], col, desc)
        for index, iid in enumerate(ordered):
            self.tree.move(iid, "", index)
        for key, title, _w, _a in PIECE_COLUMNS:
            arrow = SORT_ARROWS[self._piece_sort[1]] if self._piece_sort and self._piece_sort[0] == key else ""
            self.tree.heading(key, text=title + arrow)

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
            self._apply_piece_sort()
        self._sync_reference()
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
        self._sync_reference()
        self._invalidate_results()
        self._status(f"Re-read {len(sel)} file(s) from disk.")

    def remove_selected(self) -> None:
        self._close_editor()
        self._forget_rows(list(self.tree.selection()))
        self._set_details("Select a row to see its details here.")
        self.preview.show(None)
        self._sync_reference()
        self._invalidate_results()

    def clear_rows(self) -> None:
        self._close_editor()
        if self.rows and not messagebox.askyesno(APP_NAME, "Remove all pieces from the table?", parent=self):
            return
        self._forget_rows(list(self._row_order))
        self._set_details("Select a row to see its details here.")
        self.preview.show(None)
        self._sync_reference()
        self._invalidate_results()

    # ---- tree interaction

    def _on_tree_select(self, *_):
        sel = self.tree.selection()
        if len(sel) == 1:
            row = self.rows[sel[0]]
            self._set_details(row.details_text())
            self.preview.show(row)
        elif sel:
            self._set_details(f"{len(sel)} rows selected.")
            self.preview.show(None, placeholder=f"{len(sel)} rows selected — select one to preview it.")
        else:
            self.preview.show(None)

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
        index = int(col[1:]) - 1
        if not 0 <= index < len(PIECE_COLUMNS):
            return  # the blank filler column
        key = PIECE_COLUMNS[index][0]
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
        self._forget_rows(list(self._row_order))
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            for p in data["pieces"]:
                self._add_row(PieceRow.load(p["path"], self._ignored_layers(), unit=p["units"],
                                            count=p["count"], stored_mtime=p["mtime"]))
        finally:
            self.config(cursor="")
            self._apply_piece_sort()
        self._sync_reference()  # re-links the reference if the new package has the same file
        self._invalidate_results()
        flagged = sum(1 for r in self.rows.values() if r.status >= Level.WARNING)
        msg = f"Loaded package \"{data['name']}\" ({len(data['pieces'])} pieces)."
        if flagged:
            msg += f" {flagged} need attention — see the Status column."
        self._status(msg)

    # ------------------------------------------------------------------ calibration section

    def _build_control_section(self, parent) -> ttk.Frame:
        box = ttk.LabelFrame(parent, text=" 2. Calibration — plywood batch ", padding=10)
        box.columnconfigure(1, weight=1)

        # Method selector (remembered in settings.json)
        mode = self.settings.get("calibration_mode", MODE_REFERENCE)
        self.cal_mode = tk.StringVar(value=mode if mode in MODES else MODE_REFERENCE)
        modes = ttk.Frame(box)
        modes.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(modes, text="Method:").pack(side="left")
        ttk.Radiobutton(modes, text="Reference piece", value=MODE_REFERENCE, variable=self.cal_mode,
                        command=self._on_mode_changed).pack(side="left", padx=(6, 0))
        ttk.Radiobutton(modes, text="Control sample", value=MODE_CONTROL, variable=self.cal_mode,
                        command=self._on_mode_changed).pack(side="left", padx=(6, 0))

        # --- Reference piece inputs
        self.ref_frame = ttk.Frame(box)
        self.ref_frame.columnconfigure(1, weight=1)
        self.ref_iid: str | None = None
        self.ref_saved: SavedReference | None = None
        self._ref_removed_note = ""
        self._ref_last = ("", "")  # (path, name) of the current reference, to re-link or explain removal
        self._ref_labels: dict[str, str] = {}  # combobox label -> row iid (or SAVED_KEY)
        self.ref_choice = tk.StringVar()
        self.ref_qty = tk.StringVar()
        self.ref_weight = tk.StringVar()
        ttk.Label(self.ref_frame, text="Piece").grid(row=0, column=0, sticky="w")
        self.ref_combo = ttk.Combobox(self.ref_frame, textvariable=self.ref_choice, state="readonly", width=30)
        self.ref_combo.grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Label(self.ref_frame, text="Quantity weighed").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.ent_ref_qty = ttk.Entry(self.ref_frame, textvariable=self.ref_qty, width=8)
        self.ent_ref_qty.grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(self.ref_frame, text="Total weight (g)").grid(row=2, column=0, sticky="w", padx=(0, 8))
        self.ent_ref_weight = ttk.Entry(self.ref_frame, textvariable=self.ref_weight, width=14)
        self.ent_ref_weight.grid(row=2, column=1, sticky="w", pady=2)
        ttk.Label(self.ref_frame, text=CAL_TIP, style="Hint.TLabel", wraplength=300, justify="left"
                  ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.ref_note = ttk.Label(self.ref_frame, text="", style="Stale.TLabel", wraplength=300, justify="left")
        self.ref_note.grid(row=4, column=0, columnspan=2, sticky="w")
        self.ref_combo.bind("<<ComboboxSelected>>", lambda e: self._on_reference_chosen())

        # --- Control sample inputs (unchanged behavior)
        self.ctl_frame = ttk.Frame(box)
        self.ctl_length = tk.StringVar()
        self.ctl_width = tk.StringVar()
        self.ctl_weight = tk.StringVar()
        self.ctl_unit = tk.StringVar(value="in")
        ttk.Label(self.ctl_frame, text="Length").grid(row=0, column=0, sticky="w")
        self.ent_length = ttk.Entry(self.ctl_frame, textvariable=self.ctl_length, width=14)
        self.ent_length.grid(row=0, column=1, sticky="w", pady=2)
        ttk.Label(self.ctl_frame, text="Width").grid(row=1, column=0, sticky="w")
        self.ent_width = ttk.Entry(self.ctl_frame, textvariable=self.ctl_width, width=14)
        self.ent_width.grid(row=1, column=1, sticky="w", pady=2)
        units = ttk.Frame(self.ctl_frame)
        units.grid(row=0, column=2, rowspan=2, sticky="w", padx=(8, 0))
        ttk.Radiobutton(units, text="Inches", value="in", variable=self.ctl_unit).pack(anchor="w")
        ttk.Radiobutton(units, text="mm", value="mm", variable=self.ctl_unit).pack(anchor="w")
        ttk.Label(self.ctl_frame, text="Weight (g)").grid(row=2, column=0, sticky="w", padx=(0, 8))
        self.ent_weight = ttk.Entry(self.ctl_frame, textvariable=self.ctl_weight, width=14)
        self.ent_weight.grid(row=2, column=1, sticky="w", pady=2)

        for frame in (self.ref_frame, self.ctl_frame):
            frame.grid(row=1, column=0, columnspan=3, sticky="ew")

        self.ratio_label = ttk.Label(box, text="", style="Hint.TLabel")
        self.ratio_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.control_error = ttk.Label(box, text="", style="Error.TLabel", wraplength=320, justify="left")
        self.control_error.grid(row=4, column=0, columnspan=3, sticky="w")

        ttk.Separator(box).grid(row=5, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Label(box, text="Calibration preset").grid(row=6, column=0, sticky="w", padx=(0, 8))
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(box, textvariable=self.preset_var, state="readonly", width=24)
        self.preset_combo.grid(row=6, column=1, columnspan=2, sticky="ew", pady=2)
        btns = ttk.Frame(box)
        btns.grid(row=7, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Button(btns, text="Load", command=self.load_control_preset).pack(side="left")
        ttk.Button(btns, text="Save Calibration Preset…", command=self.save_control_preset).pack(side="left",
                                                                                               padx=(6, 0))
        self.default_var = tk.BooleanVar()
        ttk.Checkbutton(box, text="Use this preset as default on startup", variable=self.default_var,
                        command=self._toggle_default).grid(row=8, column=0, columnspan=3, sticky="w", pady=(6, 0))

        self.preset_combo.bind("<<ComboboxSelected>>", lambda e: self._sync_default_checkbox())
        for v in (self.ctl_length, self.ctl_width, self.ctl_weight, self.ctl_unit, self.ref_qty, self.ref_weight):
            v.trace_add("write", lambda *_: self._on_control_changed())
        self._show_mode_frame()
        self._refresh_reference_choices()
        self._on_control_changed()
        return box

    # ---- mode

    def _show_mode_frame(self) -> None:
        if self.cal_mode.get() == MODE_REFERENCE:
            self.ctl_frame.grid_remove()
            self.ref_frame.grid()
        else:
            self.ref_frame.grid_remove()
            self.ctl_frame.grid()

    def _on_mode_changed(self) -> None:
        self._show_mode_frame()
        self.settings["calibration_mode"] = self.cal_mode.get()
        self._save_settings_quietly()
        self._on_control_changed()

    # ---- reference piece choice

    def _refresh_reference_choices(self) -> None:
        """Rebuild the Piece dropdown from the pieces table (import order)."""
        names = [self.rows[i].name for i in self._row_order]
        labels: dict[str, str] = {}
        for iid in self._row_order:
            row = self.rows[iid]
            label = row.name
            if names.count(row.name) > 1:  # same file name from different folders
                label = f"{row.name} — {Path(row.path).parent.name}"
            labels[label] = iid
        if self.ref_saved is not None:
            labels[f"{self.ref_saved.name} (from preset \"{self.ref_saved.preset}\")"] = SAVED_KEY
        self._ref_labels = labels
        self.ref_combo.configure(values=list(labels))
        current = SAVED_KEY if (self.ref_iid is None and self.ref_saved) else self.ref_iid
        self.ref_choice.set(next((l for l, i in labels.items() if i == current), ""))

    def _on_reference_chosen(self) -> None:
        key = self._ref_labels.get(self.ref_choice.get())
        if key == SAVED_KEY:
            return
        if key != self.ref_iid or self.ref_saved is not None:
            self.ref_iid = key
            self.ref_saved = None  # picking a real piece replaces a preset's saved area
            self._ref_removed_note = ""
            self.ref_note.configure(text="")
            self._sync_reference()

    def _sync_reference(self) -> None:
        """Call after the pieces table changes. Keeps the reference linked to its file;
        if the file is gone from the table, clears the choice and says why."""
        if self.ref_iid is not None and self.ref_iid not in self.rows:
            lost_path, lost_name = self._ref_last
            again = next((i for i in self._row_order if _same_path(self.rows[i].path, lost_path)), None)
            if again is not None:  # e.g. a package reload that still contains the file
                self.ref_iid = again
            else:
                self.ref_iid = None
                self._ref_removed_note = (f"The reference piece {lost_name} was removed from the pieces table, "
                                          "so it was cleared. Choose another piece to calibrate from.")
                self.ref_note.configure(text=self._ref_removed_note)
                self._status(self._ref_removed_note)
        if self.ref_iid is not None:
            row = self.rows[self.ref_iid]
            self._ref_last = (row.path, row.name)
        self._refresh_reference_choices()
        self._on_control_changed()

    def _current_calibration(self):
        """Returns (calibration or None, errors, warnings) for the selected method."""
        if self.cal_mode.get() == MODE_CONTROL:
            sample, errors = validate_control(self.ctl_length.get(), self.ctl_width.get(), self.ctl_unit.get(),
                                              self.ctl_weight.get())
            return sample, errors, []
        row = self.rows.get(self.ref_iid) if self.ref_iid else None
        return validate_reference(row, self.ref_qty.get(), self.ref_weight.get(),
                                  saved=self.ref_saved if row is None else None,
                                  removed_note=self._ref_removed_note)

    def _on_control_changed(self) -> None:
        """Live validation, highlighting and ratio for whichever method is active."""
        if self.cal_mode.get() == MODE_CONTROL:
            fields = ((self.ent_length, self.ctl_length, "Control Length", parse_positive),
                      (self.ent_width, self.ctl_width, "Control Width", parse_positive),
                      (self.ent_weight, self.ctl_weight, "Control Weight (g)", parse_positive))
            empty_hint = "Enter length, width, and weight to see the g/area ratio."
        else:
            fields = ((self.ent_ref_qty, self.ref_qty, "Quantity weighed", parse_positive_int),
                      (self.ent_ref_weight, self.ref_weight, "Total weight (g)", parse_positive))
            empty_hint = "Choose the piece you weighed, then enter the quantity and total weight."
        problems = []
        for entry, var, label, parse in fields:
            text = var.get()
            if not text.strip():
                entry.configure(style="TEntry")
                continue
            try:
                parse(text, label)
                entry.configure(style="TEntry")
            except ValueError as exc:
                entry.configure(style="Invalid.TEntry")
                problems.append(str(exc))
        cal, errors, _warnings = self._current_calibration()
        if self.cal_mode.get() == MODE_REFERENCE:
            # Show piece-level problems (Error row / unknown units) right away, not just on Calculate.
            problems += [e for e in errors if e.startswith("The reference piece")]
        self.control_error.configure(text="\n".join(dict.fromkeys(problems)))
        if cal:
            gpc = cal.grams_per_cm2
            src = f"  — from saved preset \"{cal.from_preset}\"" if getattr(cal, "from_preset", None) else ""
            self.ratio_label.configure(text=f"Ratio: {gpc:.5f} g/cm²  ({gpc * 6.4516:.5f} g/in²){src}")
        else:
            self.ratio_label.configure(text=empty_hint)
        self._invalidate_results()

    # ---- presets

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
                messagebox.showinfo(APP_NAME, "Choose (or save) a calibration preset first, then tick this box.",
                                    parent=self)
                return
            self.settings["default_control_preset"] = name
            self._status(f"\"{name}\" will load automatically when TallyCraft starts.")
        else:
            if self.settings.get("default_control_preset") == name:
                self.settings["default_control_preset"] = None
            self._status("No calibration preset will load automatically on startup.")
        self._save_settings_quietly(show_errors=True)

    def _apply_control(self, data: dict) -> str:
        """Fill section 2 from a loaded preset. Returns a short note for the status bar."""
        if data["method"] == MODE_CONTROL:
            self.cal_mode.set(MODE_CONTROL)
            self.ctl_unit.set(data["unit"])
            self.ctl_length.set(data["length"])
            self.ctl_width.set(data["width"])
            self.ctl_weight.set(data["weight_g"])
            self._on_mode_changed()
            return ""

        self.cal_mode.set(MODE_REFERENCE)
        self.ref_qty.set(data["quantity"])
        self.ref_weight.set(data["weight_g"])
        self._ref_removed_note = ""
        match = next((i for i in self._row_order if _same_path(self.rows[i].path, data["reference_path"])), None)
        note = ""
        if match is not None:
            self.ref_iid, self.ref_saved = match, None
            row = self.rows[match]
            self._ref_last = (row.path, row.name)
            try:  # does the file's current area still give the ratio that was saved?
                now = float(data["weight_g"]) / (int(data["quantity"]) * row.area_cm2)
                if abs(now / data["grams_per_cm2"] - 1) > 1e-6:
                    note = (f"{row.name}'s area has changed since this preset was saved, so the ratio "
                            "now uses its current area.")
            except (TypeError, ValueError, ZeroDivisionError):
                pass  # row has an error or the fields are blank; validation reports it
        else:
            area = data.get("area_cm2")
            try:
                area = area or float(data["weight_g"]) / (int(data["quantity"]) * data["grams_per_cm2"])
            except (ValueError, ZeroDivisionError):
                area = None
            if area:
                self.ref_iid = None
                self.ref_saved = SavedReference(data["reference_name"], data["reference_path"], area, data["name"])
                note = (f"Calibration comes from the saved preset \"{data['name']}\", not from a piece in this "
                        f"package ({data['reference_name']} isn't in the pieces table).")
            else:
                self.ref_iid, self.ref_saved = None, None
                note = f"The preset \"{data['name']}\" is damaged: its saved ratio can't be used."
        self.ref_note.configure(text=note)
        self._refresh_reference_choices()
        self._on_mode_changed()
        return note

    def load_control_preset(self) -> None:
        name = self.preset_var.get()
        if not name:
            messagebox.showinfo(APP_NAME, "Choose a calibration preset from the list first.", parent=self)
            return
        try:
            note = self._apply_control(self.storage.load_control(name))
        except PresetError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        self._sync_default_checkbox()
        self._status(f"Loaded calibration preset \"{name}\"." + (f" {note}" if note else ""))

    def save_control_preset(self) -> None:
        cal, errors, _ = self._current_calibration()
        if errors:
            messagebox.showerror(APP_NAME, "Fix the calibration values before saving:\n\n• " + "\n• ".join(errors),
                                 parent=self)
            return
        name = simpledialog.askstring("Save Calibration Preset",
                                      "Name for this plywood batch (e.g. DixiePly 120526):",
                                      parent=self, initialvalue=self.preset_var.get())
        if name is None:
            return
        try:
            path = self.storage.control_path(name)
            if path.exists() and not messagebox.askyesno(
                    APP_NAME, f"A calibration preset named \"{name.strip()}\" already exists. Replace it?",
                    parent=self):
                return
            if self.cal_mode.get() == MODE_CONTROL:
                self.storage.save_control(name, self.ctl_length.get(), self.ctl_width.get(), self.ctl_unit.get(),
                                          self.ctl_weight.get())
            else:
                self.storage.save_reference(name, os.path.abspath(cal.path), cal.name, self.ref_qty.get(),
                                            self.ref_weight.get(), cal.grams_per_cm2, cal.area_cm2)
        except PresetError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self)
            return
        self._refresh_control_presets()
        self.preset_var.set(name.strip())
        self._sync_default_checkbox()
        self._status(f"Saved calibration preset \"{name.strip()}\".")

    def _load_default_control(self) -> None:
        name = self.settings.get("default_control_preset")
        if not name:
            return
        try:
            self._apply_control(self.storage.load_control(name))
            self.preset_var.set(name)
            self._sync_default_checkbox()
            self._status(f"Loaded default calibration preset \"{name}\".")
        except PresetError as exc:
            self._startup_notes.append(f"The default calibration preset couldn't be loaded: {exc}")

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

        cols = [c[0] for c in RESULT_COLUMNS] + [FILLER]
        self.results = ttk.Treeview(box, columns=cols, show="headings", height=6)
        for key, title, width, anchor in RESULT_COLUMNS:
            self.results.heading(key, text=title, command=lambda k=key: self.sort_results_by(k))
            self.results.column(key, width=width, minwidth=30, anchor=anchor, stretch=False)
        self.results.heading(FILLER, text="")
        self.results.column(FILLER, width=1, minwidth=0, stretch=True)
        ysb = ttk.Scrollbar(box, orient="vertical", command=self.results.yview)
        xsb = ttk.Scrollbar(box, orient="horizontal", command=self.results.xview)
        self.results.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.results.tag_configure("skipped", foreground="#9a1b1b", background="#f6f0f0")
        self.results.grid(row=1, column=0, sticky="nsew")
        ysb.grid(row=1, column=1, sticky="ns")
        xsb.grid(row=2, column=0, sticky="ew")

        foot = ttk.Frame(box)
        foot.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(foot, text="Package Total:", style="Header.TLabel").pack(side="left")
        self.total_g_label = ttk.Label(foot, text="—", style="Total.TLabel")
        self.total_g_label.pack(side="left", padx=(10, 0))
        ttk.Label(foot, text="=", style="Header.TLabel").pack(side="left", padx=10)
        self.total_lb_label = ttk.Label(foot, text="—", style="Total.TLabel")
        self.total_lb_label.pack(side="left")
        self.incomplete_label = ttk.Label(foot, text="", style="Incomplete.TLabel")  # packed only when needed
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

        errored = [r for r in rows if r.status == Level.ERROR]
        usable = [r for r in rows if r.status != Level.ERROR]
        calibration, control_errors, cal_warnings = self._current_calibration()
        # Only block when there is nothing meaningful to compute.
        if not usable or control_errors:
            parts = []
            if not usable:
                parts.append("Every piece has an error, so there's nothing to calculate:")
                parts.extend(f"  • {r.name}: {self._first(r, Level.ERROR)}" for r in errored)
            if control_errors:
                if parts:
                    parts.append("")
                parts.append("Reference piece calibration:" if self.cal_mode.get() == MODE_REFERENCE
                             else "Control sample:")
                parts.extend(f"  • {e}" for e in control_errors)
            messagebox.showerror(f"{APP_NAME} — can't calculate yet", "\n".join(parts), parent=self)
            return

        warned = [r for r in usable if r.status == Level.WARNING]
        if warned or cal_warnings:
            text = []
            if warned:
                text.append("These pieces have warnings:\n\n" +
                            "\n".join(f"  • {r.name}: {self._first(r, Level.WARNING)}" for r in warned))
            if cal_warnings:
                text.append(f"The reference piece used for calibration ({calibration.name}) has a warning, "
                            "so the g/area ratio may be off:\n\n" + "\n".join(f"  • {w}" for w in cal_warnings))
            if not messagebox.askyesno(f"{APP_NAME} — please review", "\n\n".join(text) + "\n\nCalculate anyway?",
                                       icon="warning", parent=self):
                return

        skipped = [SkippedLine(r.name, r.count, self._first(r, Level.ERROR)) for r in errored]
        result = calculate([PieceInput(r.name, r.area_cm2, r.count) for r in usable], calibration, skipped)
        self._last_calibration_note = describe(calibration)

        self._last_result = result
        self._render_results()
        self.total_g_label.configure(text=f"{result.total_g:,.1f} g", foreground="")
        self.total_lb_label.configure(text=format_lb_oz(result.total_g), foreground="")
        self._show_incomplete(result)
        self.stale_label.configure(text="")
        self._results_valid = True
        note = f" — {result.incomplete_note.upper()}" if result.incomplete else ""
        self._status(f"Calculated {len(usable)} piece type(s) at {datetime.now():%H:%M:%S}{note}.")

        if skipped:
            listing = "\n".join(f"  • {s.name} (×{s.count}): {s.reason}" for s in skipped)
            messagebox.showwarning(
                f"{APP_NAME} — incomplete total",
                f"{len(skipped)} file(s) had errors and were NOT included in the Package Total:\n\n"
                f"{listing}\n\nThe total shown is incomplete. Fix or remove these files and "
                "calculate again for a complete shipping weight.", parent=self)

    def sort_results_by(self, column: str) -> None:
        desc = self._result_sort is not None and self._result_sort == (column, False)
        self._result_sort = (column, desc)
        self._render_results()

    def _render_results(self) -> None:
        """Fill the results table: calculated rows (sorted if chosen), then skipped
        rows, which always stay at the bottom."""
        for key, title, _w, _a in RESULT_COLUMNS:
            arrow = SORT_ARROWS[self._result_sort[1]] if self._result_sort and self._result_sort[0] == key else ""
            self.results.heading(key, text=title + arrow)
        result = self._last_result
        if result is None:
            return
        col, desc = self._result_sort or (None, False)
        self.results.delete(*self.results.get_children())
        for item in order_results(result.lines, result.skipped, col, desc):
            if isinstance(item, SkippedLine):
                self.results.insert("", "end", tags=("skipped",),
                                    values=(item.name, SKIPPED_LABEL, item.count, SKIPPED_LABEL))
            else:
                self.results.insert("", "end", values=(item.name, f"{item.weight_per_piece_g:,.2f}", item.count,
                                                       f"{item.item_total_g:,.2f}"))

    # ------------------------------------------------------------------ text size

    def change_text_size(self, step: int) -> None:
        """step: +1 larger, -1 smaller, 0 reset."""
        if step == 0:
            new = 1.0
        else:
            nearest = min(range(len(TEXT_SCALE_STEPS)), key=lambda i: abs(TEXT_SCALE_STEPS[i] - self._text_scale))
            new = TEXT_SCALE_STEPS[max(0, min(len(TEXT_SCALE_STEPS) - 1, nearest + step))]
        self._apply_text_scale(new)

    def _apply_text_scale(self, scale: float, save: bool = True, announce: bool = True) -> None:
        scale = min(TEXT_SCALE_MAX, max(TEXT_SCALE_MIN, float(scale)))
        ratio = scale / self._text_scale
        self._text_scale = scale
        for name, (base, _weight) in BASE_FONTS.items():
            self.fonts[name].configure(size=max(6, round(base * scale)))
        style = ttk.Style(self)
        line = self.fonts["table"].metrics("linespace")
        style.configure("Treeview", font=self.fonts["table"], rowheight=line + max(8, line // 2))
        style.configure("Treeview.Heading", font=self.fonts["heading"])
        style.configure("Header.TLabel", font=self.fonts["results_hdr"])
        style.configure("Total.TLabel", font=self.fonts["total"])
        style.configure("Incomplete.TLabel", font=self.fonts["incomplete"])
        if ratio != 1.0:  # keep columns (including any the user resized) in proportion to the text
            for tree, spec in ((self.tree, PIECE_COLUMNS), (self.results, RESULT_COLUMNS)):
                for key, *_ in spec:
                    tree.column(key, width=max(30, round(tree.column(key, "width") * ratio)))
        self.preview.redraw()
        if save:
            self.settings["text_scale"] = scale
            self._save_settings_quietly()
        if announce:
            self._status(f"Text size {round(scale * 100)}%  (View menu, or Ctrl+= / Ctrl+- / Ctrl+0).")

    @staticmethod
    def _first(row: PieceRow, level: Level) -> str:
        return next((m.text for m in row.messages if m.level == level), "")

    def _show_incomplete(self, result) -> None:
        if result is not None and result.incomplete:
            self.incomplete_label.configure(text=f"⚠ {result.incomplete_note}")
            self.incomplete_label.pack(side="left", padx=(16, 0))
        else:
            self.incomplete_label.configure(text="")
            self.incomplete_label.pack_forget()

    def copy_results(self) -> None:
        if not self._results_valid:
            messagebox.showinfo(APP_NAME, "Press Calculate first (results are missing or out of date).", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(results_as_text(self._last_result, self._last_calibration_note))
        msg = "Results copied — paste them into a spreadsheet or email."
        if self._last_result.incomplete:
            msg += f" (Marked: {self._last_result.incomplete_note}.)"
        self._status(msg)

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
                            f"Data folder:\n{self.storage.root}\n\nMIT License · github.com/jaerixon/TallyCraft",
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
