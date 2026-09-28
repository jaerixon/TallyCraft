"""Convert a .docx to PDF with Microsoft Word (COM automation, Windows only).

If Word isn't installed, or conversion fails, PdfConversionError carries a
plain-language reason; callers keep the .docx and say the PDF couldn't be made.
Tests mock `convert_docx_to_pdf` — they never need Word.

Note: Word's PDF export asks the Windows default printer for page metrics. With
some printers (seen with a network HP OfficeJet) that takes close to a minute.
Pointing Word at a local printer would make it fast, but Word then changes the
Windows default printer, which couldn't be restored cleanly (the print spooler
kept the new one) — so TallyCraft never touches printers. The GUI runs this in a
background thread with a progress window instead. See SPEC §9.
"""

from __future__ import annotations

from pathlib import Path

WD_EXPORT_PDF = 17  # wdExportFormatPDF


class PdfConversionError(Exception):
    """Why the PDF couldn't be made, phrased for the user."""


def convert_docx_to_pdf(docx_path, pdf_path) -> None:
    docx_path, pdf_path = Path(docx_path).resolve(), Path(pdf_path).resolve()
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        raise PdfConversionError("Microsoft Word automation isn't available on this computer.") from None

    pythoncom.CoInitialize()
    word = None
    try:
        try:
            word = win32com.client.DispatchEx("Word.Application")
        except Exception:
            raise PdfConversionError("Microsoft Word isn't installed (or couldn't be started), so the PDF "
                                     "couldn't be made.") from None
        word.Visible = False
        word.DisplayAlerts = 0  # never block on a dialog
        doc = None
        try:
            doc = word.Documents.Open(str(docx_path), ConfirmConversions=False, ReadOnly=True,
                                      AddToRecentFiles=False, Visible=False)
            doc.ExportAsFixedFormat(str(pdf_path), WD_EXPORT_PDF)
        except Exception as exc:
            if pdf_path.exists() and _is_locked(pdf_path):
                raise PdfConversionError(f"{pdf_path.name} is open in another program (a PDF viewer?). "
                                         "Close it and try again.") from None
            raise PdfConversionError(f"Word couldn't convert the document to PDF ({_com_message(exc)}).") from None
        finally:
            if doc is not None:
                try:
                    doc.Close(False)
                except Exception:
                    pass
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
    if not pdf_path.exists():
        raise PdfConversionError("Word finished but no PDF was written.")


def _is_locked(path: Path) -> bool:
    try:
        with open(path, "r+b"):
            return False
    except OSError:
        return True


def _com_message(exc) -> str:
    """The human part of a pywintypes.com_error, if there is one."""
    try:
        details = exc.args[2]
        if details and details[2]:
            return str(details[2]).strip()
    except (IndexError, TypeError, AttributeError):
        pass
    return str(exc)
