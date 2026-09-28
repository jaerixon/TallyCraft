"""The ONE test that launches real Word / LibreOffice. Opt-in, run manually:

    set TALLYCRAFT_REAL_CONVERSION=1
    .venv\\Scripts\\python -m pytest -q tests/test_real_conversion.py

Everything else mocks PDF conversion (see CLAUDE.md). Each engine that's
installed converts the starter template filled with a small order, and the
test checks no Word/LibreOffice process it started is left running.
"""

import os
import subprocess

import pytest

from tallycraft.packing_docx import bundled_template, render_docx
from test_packing import make_record  # noqa: E402
from test_packing import order  # noqa: F401,F811  (pytest fixture)

pytestmark = pytest.mark.skipif(os.environ.get("TALLYCRAFT_REAL_CONVERSION") != "1",
                                reason="real Word/LibreOffice conversion is opt-in (TALLYCRAFT_REAL_CONVERSION=1)")


def _pids(image: str) -> set[int]:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return {int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"')}


@pytest.mark.parametrize("engine", ["word", "libreoffice"])
def test_real_conversion(order, tmp_path, engine):  # noqa: F811
    from tallycraft.pdf_convert import convert, find_soffice
    if engine == "libreoffice" and find_soffice() is None:
        pytest.skip("LibreOffice isn't installed")
    before = {img: _pids(img) for img in ("WINWORD.EXE", "soffice.exe", "soffice.bin")}
    docx = tmp_path / "list.docx"
    render_docx(make_record(order), bundled_template(), docx, tmp_path / "work")
    pdf = tmp_path / "list.pdf"
    assert convert(docx, pdf, engine) == engine
    assert pdf.read_bytes()[:5] == b"%PDF-" and pdf.stat().st_size > 10_000
    import time
    deadline = time.time() + 15  # Word/LibreOffice can take a few seconds to exit after quitting
    while True:
        leftover = {img: _pids(img) - pids for img, pids in before.items()}
        if not any(leftover.values()) or time.time() > deadline:
            break
        time.sleep(0.5)
    assert not any(leftover.values()), f"left running: {leftover}"
