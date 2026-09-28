"""Helpers that build small DXF files on the fly for tests."""

from __future__ import annotations

import ezdxf
import pytest


class DxfBuilder:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path

    def new(self, insunits: int = 1):
        doc = ezdxf.new("R2010")
        doc.header["$INSUNITS"] = insunits
        return doc, doc.modelspace()

    def save(self, doc, name: str = "piece.dxf") -> str:
        path = self.tmp_path / name
        doc.saveas(path)
        return str(path)

    @staticmethod
    def rect_lines(msp, x0, y0, x1, y1, **attribs):
        """Rectangle as four loose LINE entities (like the user's CAD exports)."""
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for a, b in zip(pts, pts[1:] + pts[:1]):
            msp.add_line(a, b, dxfattribs=attribs)


@pytest.fixture
def dxf(tmp_path):
    return DxfBuilder(tmp_path)


# ---------------------------------------------------------------- never on the user's desktop

_TCL_DIALOGS = ("tk_messageBox", "tk_getOpenFile", "tk_getSaveFile", "tk_chooseDirectory", "tk_chooseColor",
                "tk_dialog")


def _hide_tcl_side(root) -> None:
    """In this Tk interpreter: dialogs that nobody answered fail instead of appearing, and
    combobox dropdown lists (Tk's own toplevel, with a global grab) never open."""
    for cmd in _TCL_DIALOGS:
        root.tk.eval(f'proc {cmd} {{args}} {{error "TallyCraft tests: unanswered dialog ({cmd}). '
                     f'Patch it in the test."}}')
    root.tk.eval("proc ttk::combobox::Post {args} {}")


@pytest.fixture(autouse=True)
def no_windows_on_screen(monkeypatch):
    """Testing must never show a window or take keyboard/mouse focus on the user's
    desktop (CLAUDE.md). Every Tk root and toplevel starts withdrawn and can't be shown,
    raised, focused by force, or grab input; unanswered dialogs fail the test; nothing
    opens a browser or a document."""
    import os
    import tkinter as tk
    import webbrowser
    from tkinter import simpledialog

    tk_init, top_init = tk.Tk.__init__, tk.Toplevel.__init__

    def hidden_tk(self, *a, **k):
        tk_init(self, *a, **k)
        self.withdraw()
        _hide_tcl_side(self)

    def hidden_toplevel(self, *a, **k):
        top_init(self, *a, **k)
        self.withdraw()

    monkeypatch.setattr(tk.Tk, "__init__", hidden_tk)
    monkeypatch.setattr(tk.Toplevel, "__init__", hidden_toplevel)
    for cls, names in ((tk.Wm, ("deiconify", "wm_deiconify")),
                       (tk.Misc, ("lift", "tkraise", "focus_force", "grab_set", "grab_set_global"))):
        for name in names:
            monkeypatch.setattr(cls, name, lambda self, *a, **k: None)

    def refuse(what):
        def fail(*a, **k):
            raise AssertionError(f"a test tried to {what}; patch it in the test instead")
        return fail
    for name in ("askstring", "askinteger", "askfloat"):
        monkeypatch.setattr(simpledialog, name, refuse(f"show simpledialog.{name}"))
    monkeypatch.setattr(webbrowser, "open", refuse("open a web browser"))
    monkeypatch.setattr(os, "startfile", refuse("open a file or folder on the desktop"), raising=False)
