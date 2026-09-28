"""PDF engine choice and LibreOffice handling — all mocked; nothing is launched."""

import json
import subprocess
from pathlib import Path

import pytest

from tallycraft import pdf_convert
from tallycraft.storage import Storage
from tallycraft.word_pdf import PdfConversionError


@pytest.fixture
def fake_soffice(monkeypatch, tmp_path):
    exe = tmp_path / "LibreOffice" / "program" / "soffice.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setattr(pdf_convert, "find_soffice", lambda: exe)
    return exe


def test_automatic_prefers_libreoffice(fake_soffice):
    assert pdf_convert.resolve_engine("auto") == "libreoffice"
    assert pdf_convert.resolve_engine("word") == "word"


def test_automatic_falls_back_to_word(monkeypatch):
    monkeypatch.setattr(pdf_convert, "find_soffice", lambda: None)
    assert pdf_convert.resolve_engine("auto") == "word"
    assert pdf_convert.resolve_engine("libreoffice") == "libreoffice"  # explicit choice is kept


def test_convert_dispatches(monkeypatch, fake_soffice, tmp_path):
    calls = []
    monkeypatch.setattr(pdf_convert, "convert_with_word", lambda d, p: calls.append(("word", d, p)))
    monkeypatch.setattr(pdf_convert, "convert_with_libreoffice", lambda d, p: calls.append(("lo", d, p)))
    assert pdf_convert.convert("a.docx", "a.pdf", "auto") == "libreoffice"
    assert pdf_convert.convert("a.docx", "a.pdf", "word") == "word"
    assert [c[0] for c in calls] == ["lo", "word"]


def test_libreoffice_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf_convert, "find_soffice", lambda: None)
    with pytest.raises(PdfConversionError, match="LibreOffice isn't installed"):
        pdf_convert.convert_with_libreoffice(tmp_path / "a.docx", tmp_path / "a.pdf")


class FakeProc:
    def __init__(self, cmd, returncode=0, write_pdf=True, hang=False, stderr=b""):
        self.cmd, self.returncode, self.pid = cmd, returncode, 4242
        self._hang, self._stderr = hang, stderr
        if write_pdf:
            outdir = Path(cmd[cmd.index("--outdir") + 1])
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / (Path(cmd[-1]).stem + ".pdf")).write_bytes(b"%PDF-1.7 fake")

    def communicate(self, timeout=None):
        if self._hang and timeout is not None:
            self._hang = False
            raise subprocess.TimeoutExpired(self.cmd, timeout)
        return b"", self._stderr


def test_libreoffice_success_headless_isolated_profile(monkeypatch, fake_soffice, tmp_path):
    seen = {}

    def popen(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return FakeProc(cmd)
    monkeypatch.setattr(pdf_convert.subprocess, "Popen", popen)
    pdf = tmp_path / "out" / "list.pdf"
    pdf.parent.mkdir()
    pdf_convert.convert_with_libreoffice(tmp_path / "list.docx", pdf)
    assert pdf.read_bytes().startswith(b"%PDF")
    cmd = seen["cmd"]
    assert "--headless" in cmd and "--convert-to" in cmd and cmd[cmd.index("--convert-to") + 1] == "pdf"
    assert any(a.startswith("-env:UserInstallation=file:") for a in cmd)  # throwaway profile
    assert seen["kw"]["env"]["SAL_DISABLE_DEFAULTPRINTER"] == "1"  # printer lookups off, for this process only
    assert seen["kw"]["creationflags"] & getattr(subprocess, "CREATE_NO_WINDOW", 0) == \
        getattr(subprocess, "CREATE_NO_WINDOW", 0)


def test_libreoffice_failure_is_plain(monkeypatch, fake_soffice, tmp_path):
    monkeypatch.setattr(pdf_convert.subprocess, "Popen",
                        lambda cmd, **kw: FakeProc(cmd, returncode=1, write_pdf=False, stderr=b"Error: source file could not be loaded"))
    with pytest.raises(PdfConversionError, match="source file could not be loaded"):
        pdf_convert.convert_with_libreoffice(tmp_path / "a.docx", tmp_path / "a.pdf")


def test_libreoffice_timeout_kills_process_tree(monkeypatch, fake_soffice, tmp_path):
    killed = []
    monkeypatch.setattr(pdf_convert.subprocess, "Popen", lambda cmd, **kw: FakeProc(cmd, write_pdf=False, hang=True))
    monkeypatch.setattr(pdf_convert, "_kill_tree", lambda pid: killed.append(pid))
    with pytest.raises(PdfConversionError, match="didn't finish within 5 seconds"):
        pdf_convert.convert_with_libreoffice(tmp_path / "a.docx", tmp_path / "a.pdf", timeout=5)
    assert killed == [4242]


def test_engine_setting_default_and_sanitized(tmp_path):
    s = Storage(tmp_path)
    assert s.load_settings()[0]["pdf_engine"] == "auto"
    s.settings_path.write_text(json.dumps({"pdf_engine": "typewriter"}), encoding="utf-8")
    assert s.load_settings()[0]["pdf_engine"] == "auto"
    s.settings_path.write_text(json.dumps({"pdf_engine": "libreoffice"}), encoding="utf-8")
    assert s.load_settings()[0]["pdf_engine"] == "libreoffice"
