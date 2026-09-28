"""GUI tests: packing-list flow, Settings, and engrave lines in the preview.

Runs the real Tk app against a temporary folder with generated DXFs, entirely
hidden: no window is ever shown or focused (conftest.no_windows_on_screen). PDF
conversion is mocked, and anything that would start Word or LibreOffice fails
the test (see CLAUDE.md). Skipped if Tk isn't available.
"""

import json
import re
import tkinter as tk
from pathlib import Path

import pytest

from tallycraft import gui, packing_ui, pdf_convert, word_pdf
from tallycraft.storage import Storage
from tallycraft.word_pdf import PdfConversionError


def _tk_available() -> bool:
    for _attempt in range(3):  # retried: see TK_STARTUP_FLAKE
        try:
            r = tk.Tk()
            r.withdraw()  # never shown (this runs at import, before the conftest guard)
            r.destroy()
            return True
        except tk.TclError:
            pass
    return False


# Tk on Windows sometimes fails to read its own library files when many windows are
# opened in a row ("Can't find a usable init.tcl", "invalid command name
# tcl_findLibrary"). Rerun a test (pytest-rerunfailures) only for that error; any
# other failure is reported at once.
TK_STARTUP_FLAKE = pytest.mark.flaky(reruns=2, only_rerun=[r"Can't find a usable", r"init\.tcl", r"tk\.tcl",
                                                           r"tcl_findLibrary"])

pytestmark = [pytest.mark.skipif(not _tk_available(), reason="no display for Tk"), TK_STARTUP_FLAKE, pytest.mark.gui]


def fire_binding(widget, sequence: str) -> None:
    """Run the widget's own binding for `sequence` exactly as Tk would on a real key
    press. Tests never show or focus a window, and Tk only delivers key events to a
    focused, visible one, so the binding script is run directly (Tk's % fields get
    placeholder 0s, %W the widget)."""
    script = widget.bind(sequence)
    assert script, f"{widget} has no binding for {sequence}"
    script = re.sub(r"%(.)", lambda m: str(widget) if m.group(1) == "W" else "0", script)
    widget.tk.eval("foreach _ {1} {" + script + "}")  # a loop, so the binding's "break" is legal


def hidden_bbox(monkeypatch, tree):
    """In-place editors are placed over the table cell; a hidden table has no cell boxes."""
    monkeypatch.setattr(tree, "bbox", lambda *a, **k: (10, 10, 120, 22))


def rect(msp, x0, y0, x1, y1, **attribs):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for a, b in zip(pts, pts[1:] + pts[:1]):
        msp.add_line(a, b, dxfattribs=attribs)


@pytest.fixture
def files(dxf):
    doc, msp = dxf.new(insunits=1)
    rect(msp, 0, 0, 10, 6)
    msp.add_circle((5, 3), 1.5, dxfattribs={"color": 3})  # engraved artwork inside the panel
    panel = dxf.save(doc, "panel.dxf")
    doc, msp = dxf.new(insunits=1)
    rect(msp, 0, 0, 2, 1)
    pin = dxf.save(doc, "pin.dxf")
    doc, msp = dxf.new(insunits=1)
    msp.add_line((0, 0), (4, 0))
    msp.add_line((4, 0), (4, 2))
    gap = dxf.save(doc, "gap.dxf")
    return {"panel": panel, "pin": pin, "gap": gap}


def _open_app(storage):
    """Tk on Windows sometimes fails to read its own library files (init.tcl / tk.tcl)
    when many windows are opened in a row ("Can't find a usable ..."). Retry only that."""
    import time
    for attempt in range(3):
        try:
            return gui.TallyCraftApp(storage)
        except tk.TclError as exc:
            startup_flake = "Can't find a usable" in str(exc) or "init.tcl" in str(exc)  # Tk's own .tcl files
            if not startup_flake or attempt == 2:
                raise
            time.sleep(0.5)


@pytest.fixture
def app(tmp_path, monkeypatch, files):
    calls = {"info": [], "warn": [], "error": [], "ask": [], "okcancel": [], "opened": [], "convert": []}
    answers = {"ask": [], "okcancel": []}

    def ask(*a, **k):
        calls["ask"].append(a[1])
        return answers["ask"].pop(0) if answers["ask"] else False

    def okcancel(*a, **k):
        calls["okcancel"].append(a[1])
        return answers["okcancel"].pop(0) if answers["okcancel"] else True

    for mod in (gui.messagebox, packing_ui.messagebox):
        monkeypatch.setattr(mod, "showinfo", lambda *a, **k: calls["info"].append(a[1]))
        monkeypatch.setattr(mod, "showwarning", lambda *a, **k: calls["warn"].append(a[1]))
        monkeypatch.setattr(mod, "showerror", lambda *a, **k: calls["error"].append(a[1]))
        monkeypatch.setattr(mod, "askyesno", ask)
        monkeypatch.setattr(mod, "askokcancel", okcancel)
    monkeypatch.setattr(gui.os, "startfile", lambda p: calls["opened"].append(str(p)), raising=False)

    # Never launch Word or LibreOffice from tests.
    def no_real(*a, **k):
        raise AssertionError("a test tried to start Word or LibreOffice")
    monkeypatch.setattr(word_pdf, "convert_docx_to_pdf", no_real)
    monkeypatch.setattr(pdf_convert, "convert_with_word", no_real)
    monkeypatch.setattr(pdf_convert, "convert_with_libreoffice", no_real)
    monkeypatch.setattr(pdf_convert, "find_soffice", lambda: None)

    def fake_convert(docx, pdf, choice="auto"):
        calls["convert"].append((Path(docx), Path(pdf), choice))
        if calls.get("convert_fails"):
            raise PdfConversionError(calls["convert_fails"])
        Path(pdf).write_bytes(b"%PDF-1.7 fake")
        return "word"
    monkeypatch.setattr(gui, "convert_to_pdf", fake_convert)

    monkeypatch.setattr(gui.filedialog, "askopenfilenames", lambda **k: [files["panel"], files["pin"], files["gap"]])
    customer = {"name": "Jordan Rivera", "address": "123 Maple St", "etsy_order": "3141592",
                "order_date": "2026-09-27", "note": "Thanks!"}

    class FakePackingDialog:
        def __init__(self, *a, **k):
            pass

        def run(self):
            return dict(customer)
    monkeypatch.setattr(gui, "PackingDialog", FakePackingDialog)

    a = _open_app(Storage(tmp_path / "app"))
    a.withdraw()
    a.update()
    a.calls, a.answers = calls, answers
    yield a
    # Tripwire: nothing from this test may have appeared on the user's screen
    # ("wm stackorder" lists every mapped toplevel, including Tk-made ones like dropdowns).
    shown = a.tk.splitlist(a.tk.call("wm", "stackorder", "."))
    a.destroy()
    assert not shown, f"windows were shown on screen during the test: {shown}"


def calculate_ready(a):
    a.import_files()
    a.cal_mode.set("control")
    a._on_mode_changed()
    a.ctl_length.set("4")
    a.ctl_width.set("2")
    a.ctl_weight.set("23.456")
    a.answers["ask"][:0] = []
    a.calculate()
    a.update()


def pump(a, until, limit=400):
    for _ in range(limit):
        a.update()
        if until():
            return
        a.after(10)
        a.update_idletasks()
        import time
        time.sleep(0.01)
    raise AssertionError("background conversion didn't finish")


# ---------------------------------------------------------------- packing-list flow

def test_button_only_enabled_with_current_results(app):
    assert str(app.packing_button.cget("state")) == "disabled"
    calculate_ready(app)
    assert str(app.packing_button.cget("state")) == "normal"
    app._invalidate_results()
    assert str(app.packing_button.cget("state")) == "disabled"


def test_create_packing_list_saves_record_docx_and_pdf(app):
    calculate_ready(app)
    app.answers["ask"] = [True, False]  # confirm unmeasured part, then "open the PDF now?" -> no
    app.settings["pdf_engine"] = "libreoffice"
    app.create_packing_list()
    pump(app, lambda: len(app.calls["ask"]) >= 2)
    folder = app.storage.packing_dir
    names = sorted(p.name for p in folder.iterdir())
    assert names == ["2026-09-27 - Jordan Rivera - 3141592.docx", "2026-09-27 - Jordan Rivera - 3141592.json",
                     "2026-09-27 - Jordan Rivera - 3141592.pdf"]
    assert "could not be measured" in app.calls["ask"][0]  # unmeasured parts confirmed first
    docx, pdf, engine = app.calls["convert"][0]
    assert docx.name.endswith(".docx") and engine == "libreoffice"  # Settings choice is used
    assert "Packing list created" in app.calls["ask"][1]
    record = json.loads((folder / "2026-09-27 - Jordan Rivera - 3141592.json").read_text(encoding="utf-8"))
    assert record["customer"]["name"] == "Jordan Rivera" and record["results"]["skipped_count"] == 1


def test_pdf_failure_keeps_docx_and_says_why(app):
    calculate_ready(app)
    app.calls["convert_fails"] = "Microsoft Word isn't installed (or couldn't be started), so the PDF couldn't be made."
    app.answers["ask"] = [True, False]
    app.create_packing_list()
    pump(app, lambda: len(app.calls["ask"]) >= 2)
    folder = app.storage.packing_dir
    assert (folder / "2026-09-27 - Jordan Rivera - 3141592.docx").exists()
    assert not (folder / "2026-09-27 - Jordan Rivera - 3141592.pdf").exists()
    msg = app.calls["ask"][1]
    assert "The Word document was saved" in msg and "The PDF couldn't be made: Microsoft Word isn't installed" in msg
    assert "Open the Word document now?" in msg


def test_template_error_blocks(app, tmp_path):
    calculate_ready(app)
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a document")
    app.settings["template_path"] = str(bad)
    app.create_packing_list()
    assert app.calls["error"] and "can't be used" in app.calls["error"][-1]
    assert not list(app.storage.packing_dir.glob("*"))


def test_template_warning_can_be_declined(app, tmp_path):
    from docx import Document
    calculate_ready(app)
    d = Document(str(app.storage.template_path(app.settings)))
    d.add_paragraph("{{ custmer_name }}")
    typo = tmp_path / "typo.docx"
    d.save(typo)
    app.settings["template_path"] = str(typo)
    app.answers["ask"] = [False]
    app.create_packing_list()
    assert "custmer_name" in app.calls["ask"][0]
    assert not list(app.storage.packing_dir.glob("*"))


def test_reprint_uses_current_template_and_keeps_original(app):
    calculate_ready(app)
    app.answers["ask"] = [True, False]
    app.create_packing_list()
    pump(app, lambda: len(app.calls["ask"]) >= 2)
    folder = app.storage.packing_dir
    json_path = folder / "2026-09-27 - Jordan Rivera - 3141592.json"
    original = (folder / "2026-09-27 - Jordan Rivera - 3141592.pdf").read_bytes()
    record = app.storage.load_packing_record(json_path)
    app.answers["ask"] = [False]
    app._reprint(record, json_path)
    pump(app, lambda: len(app.calls["ask"]) >= 3)
    assert "Uses your current template. The original PDF is still saved alongside the record." in \
        app.calls["okcancel"][-1]
    reprints = sorted(p.name for p in folder.glob("*(reprint *"))
    assert len(reprints) == 2 and all(n.startswith("2026-09-27 - Jordan Rivera - 3141592 (reprint ") for n in reprints)
    assert (folder / "2026-09-27 - Jordan Rivera - 3141592.pdf").read_bytes() == original


def test_reprint_can_be_cancelled(app):
    calculate_ready(app)
    app.answers["ask"] = [True, False]
    app.create_packing_list()
    pump(app, lambda: len(app.calls["ask"]) >= 2)
    json_path = next(app.storage.packing_dir.glob("*.json"))
    app.answers["okcancel"] = [False]
    app._reprint(app.storage.load_packing_record(json_path), json_path)
    assert not list(app.storage.packing_dir.glob("*(reprint *"))


# ---------------------------------------------------------------- Settings

def test_settings_dialog_values_and_validation(app):
    d = packing_ui.SettingsDialog(app, app.settings, app.storage, app.show_template_help)
    d.engine.set("LibreOffice")
    d.colors.delete("1.0", "end")
    d.colors.insert("1.0", "ACI 7\nblack")
    d._ok()
    assert "Cut colors" in d.error.cget("text") and d.result is None
    d.colors.delete("1.0", "end")
    d.colors.insert("1.0", "ACI 7\nRGB 0,0,0\nACI 1")
    d._ok()
    assert d.result["pdf_engine"] == "libreoffice"
    assert d.result["cut_colors"] == ["ACI 7", "RGB 0,0,0", "ACI 1"]
    assert d.result["template_path"] == "templates/packing_list_template.docx"


def test_restore_default_template_from_settings(app):
    user = app.storage.templates_dir / "packing_list_template.docx"
    user.write_bytes(b"my edits")
    d = packing_ui.SettingsDialog(app, app.settings, app.storage, None)
    app.answers["ask"] = [True]  # use the fresh copy now
    d._restore_template()
    assert user.read_bytes() == b"my edits"  # never replaced
    assert d.template.get() == "templates/packing_list_template (default copy).docx"
    assert (app.storage.templates_dir / "packing_list_template (default copy).docx").exists()
    d.destroy()


def test_changing_cut_colors_rereads_pieces(app, monkeypatch):
    calculate_ready(app)
    panel = next(r for r in app.order.packages[0].ordered_rows() if r.name == "panel.dxf")
    assert len(panel.parsed.engrave) == 1  # green circle is engrave with the default colors
    new = dict(app.settings, cut_colors=["ACI 7", "ACI 3"])
    monkeypatch.setattr(gui.SettingsDialog, "run", lambda self: {k: new[k] for k in (
        "shop_name", "logo_path", "default_note", "cut_colors", "template_path", "pdf_engine")})
    app.answers["ask"] = [True]
    app.open_settings()
    panel = next(r for r in app.order.packages[0].ordered_rows() if r.name == "panel.dxf")
    assert panel.parsed.engrave == [] and len(panel.parsed.loops) == 2  # the circle now cuts a hole
    saved = json.loads(app.storage.settings_path.read_text(encoding="utf-8"))
    assert saved["cut_colors"] == ["ACI 7", "ACI 3"]


def test_template_help_window(app):
    app.show_template_help()
    app.update()
    helps = [w for w in app.winfo_children() if isinstance(w, packing_ui.TemplateHelp)]
    assert helps and "{{ customer_name }}" in helps[0].text.get("1.0", "end")


# ---------------------------------------------------------------- preview

def test_preview_draws_engrave_lines_with_legend(app):
    app.import_files()
    app.update()
    iid = next(i for i in app._row_order if app.rows[i].name == "panel.dxf")
    app.tree.selection_set(iid)
    app.update()
    app.preview.redraw()
    canvas = app.preview
    from tallycraft.preview import ENGRAVE_LINE
    engrave = [i for i in canvas.find_all() if canvas.type(i) == "line" and canvas.itemcget(i, "fill") == ENGRAVE_LINE]
    assert engrave, "engrave lines should be drawn"
    widths = {float(canvas.itemcget(i, "width")) for i in engrave}
    assert widths == {1.0}  # thinner than the 2-px cut outline
    texts = [canvas.itemcget(i, "text") for i in canvas.find_all() if canvas.type(i) == "text"]
    assert "engrave" in texts


# ---------------------------------------------------------------- v0.5: dialog fixes, display names, dimensions

def _packing_dialog(app, tmp_path, **kw):
    d = packing_ui.PackingDialog(app, "Thanks!", tmp_path, "1x Box", 0, **kw)
    d.update()
    return d


def test_enter_in_address_adds_a_line_and_keeps_the_dialog_open(app, tmp_path):
    d = _packing_dialog(app, tmp_path)
    d.name.set("Jordan Rivera")
    d.address.insert("end", "1223 Elegance Court")
    for seq in ("<Return>", "<Shift-Return>"):
        fire_binding(d.address, seq)
        d.update()
    assert d.address.bind("<KP_Enter>")  # the keypad Enter key too
    assert not d.bind("<Return>") and not d.bind("<KP_Enter>")  # nothing at dialog level could submit it
    d.address.insert("end", "Springfield, IL 62704")
    d.update()
    assert d.winfo_exists() and d.result is None  # Enter never closes or submits the dialog
    assert d.address.get("1.0", "end").strip() == "1223 Elegance Court\n\nSpringfield, IL 62704"
    d._ok()
    assert d.result["address"] == "1223 Elegance Court\n\nSpringfield, IL 62704"
    assert app.calls["ask"] == []  # multi-line: no "only one line" question


def test_one_line_address_asks_before_saving(app, tmp_path):
    d = _packing_dialog(app, tmp_path)
    d.name.set("Jordan Rivera")
    d.address.insert("1.0", "1223 Elegance Court")
    app.answers["ask"] = [False]  # "No, it isn't complete"
    d._ok()
    assert d.winfo_exists() and d.result is None and "only one line" in app.calls["ask"][-1]
    app.answers["ask"] = [True]
    d._ok()
    assert d.result["address"] == "1223 Elegance Court"


def test_packing_dialog_prefill_is_editable(app, tmp_path):
    d = _packing_dialog(app, tmp_path, prefill={"name": "Sam Lee", "etsy_order": "3141592653",
                                                "order_date": "2026-09-20", "address": "1 Main St\nTown, ST 1"})
    assert d.name.get() == "Sam Lee" and d.order_no.get() == "3141592653" and d.order_date.get() == "2026-09-20"
    assert d.address.get("1.0", "end").strip() == "1 Main St\nTown, ST 1"
    d.name.set("Sam Q. Lee")
    d._ok()
    assert d.result["name"] == "Sam Q. Lee" and d.result["etsy_order"] == "3141592653"


def test_settings_dimension_units(app):
    d = packing_ui.SettingsDialog(app, app.settings, app.storage, None)
    assert d.dims.get() == "Inches"  # default
    d.dims.set("Each file's own units")
    d._ok()
    assert d.result["dimension_units"] == "file"


def test_display_name_edited_in_pieces_table_reaches_the_packing_list(app, monkeypatch):
    calculate_ready(app)
    pkg = app.order.packages[0]
    iid = next(i for i in pkg.order if pkg.rows[i].name == "panel.dxf")
    hidden_bbox(monkeypatch, app.tree)
    col = "#" + str([c[0] for c in gui.PIECE_COLUMNS].index("display") + 1)
    app._edit_display_name(iid, col)
    app._editor.insert(0, "  Front Panel ")
    fire_binding(app._editor, "<Return>")
    app.update()
    assert pkg.rows[iid].display_name == "Front Panel"
    assert "Front Panel" in app.tree.item(iid, "values")
    assert pkg.is_dirty
    assert pkg.pieces_spec()[pkg.order.index(iid)]["display_name"] == "Front Panel"
    app.calculate()  # results were invalidated by the rename
    app.update()
    seen = {}
    monkeypatch.setattr(gui, "render_docx", lambda rec, tpl, out, work, dims="in": (
        seen.update(rec=rec, dims=dims), Path(out).write_bytes(b"docx"))[-1])
    app.settings["dimension_units"] = "mm"
    app.answers["ask"] = [True, False]  # confirm the unmeasured part, don't open the PDF
    app.create_packing_list()
    pump(app, lambda: app.calls["convert"])
    line = next(l for l in seen["rec"]["results"]["lines"] if l["name"] == "panel.dxf")
    assert line["display_name"] == "Front Panel" and seen["dims"] == "mm"


# ---------------------------------------------------------------- File units dropdown & display units (v0.5)

def _units_col():
    return "#" + str([c[0] for c in gui.PIECE_COLUMNS].index("units") + 1)


def test_file_units_dropdown_focus_check_never_raises(app, monkeypatch):
    """While the dropdown is open, Tk's own list (<combobox>.popdown.f.l) has keyboard
    focus. tkinter's focus_get() can't look that path up (KeyError: 'popdown', the
    v0.5 crash), so the editor's focus check reads Tk's focus path instead. It keeps
    the editor open while the list has focus and closes it once focus really left."""
    errors = []
    app.report_callback_exception = lambda *exc: errors.append(exc)
    app.import_files()
    iid = app._row_order[0]
    hidden_bbox(monkeypatch, app.tree)
    app._edit_units(iid, _units_col())
    app.update()
    combo = app._editor
    popdown = combo.tk.call("ttk::combobox::PopdownWindow", combo)
    listbox = f"{popdown}.f.l"
    with pytest.raises(KeyError):
        app.nametowidget(listbox)  # what focus_get() does with that path

    # Tests never give real keyboard focus, so report where focus "is" to the check.
    focus = {"path": listbox}
    real_focused_path = gui.focused_path
    monkeypatch.setattr(gui, "focused_path", lambda widget: (real_focused_path(widget), focus["path"])[1])
    fire_binding(combo, "<FocusOut>")
    _waited(app)
    assert not errors and app._editor is combo  # the list belongs to the editor: stays open
    focus["path"] = str(app.tree)
    fire_binding(combo, "<FocusOut>")
    pump(app, lambda: app._editor is None)
    assert not errors  # focus really left: closed, no exception


def _waited(app, ms=150):
    app.after(ms)
    app.update()
    return True


def test_focused_path_reads_tk_directly(app):
    """gui.focused_path never looks the path up as a widget, and nothing in the app
    calls focus_get() (which fails for combobox dropdown lists)."""
    assert isinstance(gui.focused_path(app), str)
    src = Path(gui.__file__).parent
    assert not [p.name for p in src.glob("*.py") if re.search(r"\.focus_get\(", p.read_text(encoding="utf-8"))]


def test_file_units_column_title_and_tooltip(app):
    assert app.tree.heading("units", "text") == "File units"
    assert "relabels the numbers without converting them" in gui.FILE_UNITS_TIP


def test_pieces_table_sizes_follow_show_dimensions_in(app, dxf, monkeypatch):
    doc, msp = dxf.new(insunits=4)  # a mm file, like a LightBurn export
    rect(msp, 0, 0, 368.3, 361.95)
    path = dxf.save(doc, "lb.dxf")
    monkeypatch.setattr(gui.filedialog, "askopenfilenames", lambda **k: [path])
    app.import_files()
    iid = app._row_order[0]
    values = dict(zip([c[0] for c in gui.PIECE_COLUMNS], app.tree.item(iid, "values")))
    assert values["units"] == "Millimeters"  # File units unchanged
    assert values["bbox"] == "14.500 × 14.250 in"  # shown in inches by default
    assert values["area"].endswith("in²")
    assert app.preview.dim_units == "in"
    monkeypatch.setattr(gui.SettingsDialog, "run", lambda self: {"dimension_units": "mm"})
    app.open_settings()
    values = dict(zip([c[0] for c in gui.PIECE_COLUMNS], app.tree.item(iid, "values")))
    assert values["bbox"] == "368.3 × 361.9 mm" and values["area"].endswith("mm²")
    assert app.preview.dim_units == "mm"


def test_implausible_file_units_show_a_warning(app, dxf, monkeypatch):
    doc, msp = dxf.new(insunits=4)  # a 368 mm (14.5 in) part
    rect(msp, 0, 0, 368.3, 361.95)
    path = dxf.save(doc, "lb.dxf")
    monkeypatch.setattr(gui.filedialog, "askopenfilenames", lambda **k: [path])
    app.import_files()
    iid = app._row_order[0]
    hidden_bbox(monkeypatch, app.tree)
    app._edit_units(iid, _units_col())
    app.update()
    combo = app._editor
    combo.set("Inches")  # relabel as inches: 368 in long
    combo.event_generate("<<ComboboxSelected>>")
    app.update()
    row = app.rows[iid]
    assert row.unit == "in"
    assert app.tree.item(iid, "values")[-1].endswith("Warning")
    warning = next(m.text for m in row.messages if m.text.startswith("At this unit"))
    assert warning == "At this unit the piece would be 368.300 × 361.950 in (9,354.8 × 9,193.5 mm). Is that right?"
    assert "relabelled, not converted" in app.statusbar.cget("text")
