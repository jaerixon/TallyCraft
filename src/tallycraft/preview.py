"""Canvas preview of one piece, drawn from the exact loops the area was
computed from (ParsedPiece.loops / loop_depths / open_chains / error_points)."""

from __future__ import annotations

import tkinter as tk

from .messages import Level
from .pieces import PieceRow

BG = "#ffffff"
SOLID_FILL = "#ecd3ad"      # plywood
SOLID_LINE = "#6b4423"      # outer boundary (and islands)
HOLE_LINE = "#1f6fb2"       # holes / cutouts
OPEN_LINE = "#e07b00"       # runs that never closed
ENGRAVE_LINE = "#7fa07f"    # engrave-only artwork: drawn thin and light, never measured
ERROR_MARK = "#d00000"      # loose ends / bad junctions
TEXT = "#333333"
HINT = "#777777"

MARGIN = 14
FOOTER = 26  # room for the dimension label and legend
MARK_R = 6


class PiecePreview(tk.Canvas):
    def __init__(self, parent, **kw):
        kw.setdefault("background", BG)
        kw.setdefault("highlightthickness", 1)
        kw.setdefault("highlightbackground", "#b8b8b8")
        super().__init__(parent, **kw)
        self._row: PieceRow | None = None
        self._placeholder = "Select a piece to preview it."
        self.bind("<Configure>", lambda e: self.redraw())

    def show(self, row: PieceRow | None, placeholder: str | None = None) -> None:
        self._row = row
        if placeholder:
            self._placeholder = placeholder
        elif row is None:
            self._placeholder = "Select a piece to preview it."
        self.redraw()

    # ------------------------------------------------------------------ drawing

    def redraw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 40 or h < 40:
            return
        row = self._row
        if row is None:
            self._center_text(self._placeholder, HINT)
            return

        piece = row.parsed
        if not piece.loops and not piece.open_chains and not piece.engrave:
            reason = next((m.text for m in row.messages if m.level == Level.ERROR),
                          "No geometry was found in this file.")
            self._center_text(f"No preview available\n\n{reason}", TEXT, title=True)
            return

        pts = ([p for l in piece.loops for p in l] + [p for c in piece.open_chains for p in c] + piece.error_points
               + [p for e in piece.engrave for p in e])
        minx = min(p[0] for p in pts)
        maxx = max(p[0] for p in pts)
        miny = min(p[1] for p in pts)
        maxy = max(p[1] for p in pts)
        bw, bh = max(maxx - minx, 1e-12), max(maxy - miny, 1e-12)
        avail_w, avail_h = w - 2 * MARGIN, h - 2 * MARGIN - FOOTER
        if avail_w < 10 or avail_h < 10:
            return
        scale = min(avail_w / bw, avail_h / bh)
        ox = MARGIN + (avail_w - bw * scale) / 2
        oy = MARGIN + (avail_h - bh * scale) / 2

        def tx(p):  # flip Y: DXF y grows upward, canvas y grows downward
            return ox + (p[0] - minx) * scale, oy + (maxy - p[1]) * scale

        def flat(seq):
            out = []
            for p in seq:
                out.extend(tx(p))
            return out

        depths = piece.loop_depths if len(piece.loop_depths) == len(piece.loops) else [0] * len(piece.loops)
        measured = piece.net_area_raw is not None
        solid_fill = SOLID_FILL if measured else ""  # unmeasured pieces are drawn as outlines only
        has_hole = False
        # Shallow loops first so holes paint over solids and islands over holes.
        for i in sorted(range(len(piece.loops)), key=lambda k: depths[k]):
            loop = piece.loops[i]
            if len(loop) < 3:
                continue
            if depths[i] % 2 == 0:
                self.create_polygon(flat(loop), fill=solid_fill, outline=SOLID_LINE, width=2)
            else:
                has_hole = True
                self.create_polygon(flat(loop), fill=BG if measured else "", outline=HOLE_LINE, width=1.5)
        for line in piece.engrave:  # on top of the fill, thinner than cut lines
            if len(line) >= 2:
                self.create_line(flat(line), fill=ENGRAVE_LINE, width=1)
        for chain in piece.open_chains:
            if len(chain) >= 2:
                self.create_line(flat(chain), fill=OPEN_LINE, width=2, dash=(6, 3))
        for p in piece.error_points:
            x, y = tx(p)
            self.create_oval(x - MARK_R, y - MARK_R, x + MARK_R, y + MARK_R, outline=ERROR_MARK, width=2)
            self.create_oval(x - 2, y - 2, x + 2, y + 2, fill=ERROR_MARK, outline=ERROR_MARK)

        # Footer: dimensions (in the row's current unit) + legend
        dims = row.bbox_text()
        if row.unit not in ("in", "mm"):
            dims += "  (units unknown)"
        fy = h - MARGIN - FOOTER / 2 + 4
        self.create_text(MARGIN, fy, text=dims, anchor="w", fill=TEXT, font=("Segoe UI", 10, "bold"))
        legend = [("outline", SOLID_LINE, "rect")]
        if has_hole:
            legend.append(("hole", HOLE_LINE, "rect"))
        if piece.engrave:
            legend.append(("engrave", ENGRAVE_LINE, "thin"))
        if piece.open_chains:
            legend.append(("unclosed", OPEN_LINE, "line"))
        if piece.error_points:
            legend.append(("problem", ERROR_MARK, "dot"))
        x = w - MARGIN
        for label, color, kind in reversed(legend):
            t = self.create_text(x, fy, text=label, anchor="e", fill=HINT, font=("Segoe UI", 9))
            x0 = self.bbox(t)[0]
            if kind == "rect":
                self.create_rectangle(x0 - 16, fy - 5, x0 - 5, fy + 5, outline=color, width=2)
            elif kind == "thin":
                self.create_line(x0 - 18, fy, x0 - 4, fy, fill=color, width=1)
            elif kind == "line":
                self.create_line(x0 - 18, fy, x0 - 4, fy, fill=color, width=2, dash=(4, 2))
            else:
                self.create_oval(x0 - 15, fy - 5, x0 - 5, fy + 5, outline=color, width=2)
            x = x0 - 24

    def _center_text(self, text: str, color: str, title: bool = False) -> None:
        w, h = self.winfo_width(), self.winfo_height()
        self.create_text(w / 2, h / 2, text=text, fill=color, justify="center", width=max(60, w - 2 * MARGIN),
                         font=("Segoe UI", 10, "bold" if title else "normal"))
