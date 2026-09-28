"""GUI tests: packing-list flow, Settings, and engrave lines in the preview.

Runs the real Tk app against a temporary folder with generated DXFs. PDF
conversion is mocked, and anything that would start Word or LibreOffice fails
the test (see CLAUDE.md). Skipped if Tk can't open a window.
"""

import json
import tkinter as tk
from pathlib import Path

import pytest

from tallycraft import gui, packing_ui, pdf_convert, word_pdf
from tallycraft.storage import Storage
from tallycraft.word_pdf import PdfConversionError


def _tk_available() -> bool:
    try:
        r = tk.Tk()
        r.destroy()
        return True
    except tk.TclError:
        return False


pytestmark = pytest.mark.skipif(not _tk_available(), reason="no display for Tk")


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
    """Tk on Windows sometimes fails to read its own init.tcl when many windows are
    opened in a row ("couldn't read file ... init.tcl: No error"). Retry only that."""
    import time
    for attempt in range(3):
        try:
            return gui.TallyCraftApp(storage)
        except tk.TclError as exc:
            if "init.tcl" not in str(exc) or attempt == 2:
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
    a.destroy()


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
    app.deiconify()
    app.geometry("1200x900")
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
