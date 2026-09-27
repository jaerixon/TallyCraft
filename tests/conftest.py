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
