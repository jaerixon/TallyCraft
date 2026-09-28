"""Turn a filled-in packing-list .docx into a PDF with Word or LibreOffice.

Settings > "Make PDFs with": Automatic (LibreOffice if installed, otherwise
Word) / Word / LibreOffice. Every failure is a PdfConversionError with a plain
reason; callers keep the .docx and say the PDF couldn't be made.

LibreOffice runs headless with a timeout and a throwaway user profile, so it
never shows first-run dialogs, never interferes with a LibreOffice window the
user has open, and leaves no background processes (on timeout the whole
process tree is ended). Tests mock `convert`; they never launch Word or
LibreOffice. See SPEC §9.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .word_pdf import PdfConversionError, convert_docx_to_pdf as convert_with_word

ENGINES = {"auto": "Automatic", "word": "Word", "libreoffice": "LibreOffice"}
LIBREOFFICE_TIMEOUT_S = 120
# LibreOffice asks the Windows default printer for page metrics when it loads a
# document; some printers (seen: a network HP OfficeJet) take ~50 s to answer.
# These switches turn that off for the LibreOffice process TallyCraft starts
# (nothing system-wide changes). Page size still comes from the template.
LIBREOFFICE_ENV = {"SAL_DISABLE_PRINTERLIST": "1", "SAL_DISABLE_DEFAULTPRINTER": "1"}


def find_soffice() -> Path | None:
    """LibreOffice's soffice.exe: on PATH, or in the usual install folders."""
    found = shutil.which("soffice") or shutil.which("soffice.exe")
    if found:
        return Path(found)
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        candidate = Path(base) / "LibreOffice" / "program" / "soffice.exe"
        if candidate.exists():
            return candidate
    return None


def resolve_engine(choice: str) -> str:
    """ "auto" -> "libreoffice" when installed, else "word"."""
    if choice == "word" or choice == "libreoffice":
        return choice
    return "libreoffice" if find_soffice() else "word"


def convert(docx_path, pdf_path, choice: str = "auto") -> str:
    """Convert with the chosen engine. Returns the engine used ("word" / "libreoffice")."""
    engine = resolve_engine(choice)
    if engine == "libreoffice":
        convert_with_libreoffice(docx_path, pdf_path)
    else:
        convert_with_word(docx_path, pdf_path)
    return engine


def convert_with_libreoffice(docx_path, pdf_path, timeout: float = LIBREOFFICE_TIMEOUT_S) -> None:
    soffice = find_soffice()
    if soffice is None:
        raise PdfConversionError("LibreOffice isn't installed (soffice.exe wasn't found), so the PDF couldn't "
                                 "be made. Install it, or choose Word in File > Settings.")
    docx_path, pdf_path = Path(docx_path).resolve(), Path(pdf_path).resolve()
    with tempfile.TemporaryDirectory(prefix="tallycraft_lo_") as work:
        work = Path(work)
        profile = (work / "profile").as_uri()  # isolated: no dialogs, no clash with an open LibreOffice
        cmd = [str(soffice), "--headless", "--norestore", "--nologo", "--nodefault", "--nolockcheck",
               f"-env:UserInstallation={profile}", "--convert-to", "pdf", "--outdir", str(work / "out"),
               str(docx_path)]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags,
                                    env={**os.environ, **LIBREOFFICE_ENV})
        except OSError as exc:
            raise PdfConversionError(f"LibreOffice couldn't be started ({exc}).") from None
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc.pid)
            proc.communicate()
            raise PdfConversionError(f"LibreOffice didn't finish within {int(timeout)} seconds, so it was stopped. "
                                     "The PDF couldn't be made.") from None
        result = work / "out" / (docx_path.stem + ".pdf")
        if proc.returncode != 0 or not result.exists():
            detail = (err or out or b"").decode("utf-8", "replace").strip().splitlines()
            reason = detail[-1] if detail else f"exit code {proc.returncode}"
            raise PdfConversionError(f"LibreOffice couldn't convert the document to PDF ({reason}).")
        try:
            os.replace(result, pdf_path)
        except PermissionError:
            raise PdfConversionError(f"{pdf_path.name} is open in another program (a PDF viewer?). Close it and "
                                     "try again.") from None
        except OSError:
            shutil.copyfile(result, pdf_path)


def _kill_tree(pid: int) -> None:
    """End soffice.exe and its soffice.bin child."""
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=30)
    except Exception:
        pass
