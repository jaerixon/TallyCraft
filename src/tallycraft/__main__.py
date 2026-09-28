import sys


def selftest(out_path: str, dxf_paths: list[str]) -> int:
    """Parse DXFs without opening the window and write a JSON report.
    Used to verify a packaged exe (which has no console) bundles everything."""
    import json

    from tallycraft.pieces import PieceRow

    report = []
    for p in dxf_paths:
        row = PieceRow.load(p)
        report.append({"file": row.name, "unit": row.unit, "area_raw": row.parsed.net_area_raw,
                       "status": row.status.label, "messages": [m.text for m in row.messages]})
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return 0


def _selftest_record(dxf_paths: list[str]) -> dict:
    """A one-package packing-list record from DXFs (count 1 each, 1 in x 1 in / 1 g control)."""
    from tallycraft import __version__
    from tallycraft.calc import ControlSample, PieceInput, SkippedLine, calculate
    from tallycraft.order import Order, Package, merge_order
    from tallycraft.packing import build_record, now_stamp, picture_from_parsed
    from tallycraft.pieces import PieceRow

    pkg = Package("Self-test", preset_name="Self-test")
    for i, p in enumerate(dxf_paths):
        pkg.rows[f"r{i}"] = PieceRow.load(p)
        pkg.order.append(f"r{i}")
    labels, merged = merge_order(Order([pkg]))
    rows = {r.name: r for r in pkg.ordered_rows()}
    cal = ControlSample(1, 1, "in", 1.0)
    result = calculate([PieceInput(m.name, m.area_cm2, m.total_count, m.kit_counts) for m in merged if not m.error],
                       cal, [SkippedLine(m.name, m.total_count, m.error, m.kit_counts) for m in merged if m.error],
                       tuple(labels))
    info = {m.name: {"path": m.path, "unit": rows[m.name].unit, "picture": picture_from_parsed(rows[m.name].parsed)}
            for m in merged}
    return build_record(customer={"name": "Self-test"}, shop={"name": "TallyCraft"},
                        packages=[{"name": pkg.name, "preset_name": pkg.name, "quantity": 1,
                                   "unsaved_changes": False, "pieces": pkg.pieces_spec()}],
                        calibration={"method": "control", "length": "1", "width": "1", "unit": "in",
                                     "weight_g": "1", "grams_per_cm2": cal.grams_per_cm2, "preset_name": None},
                        result=result, pieces_info=info, calculated_at=now_stamp(), created_at=now_stamp(),
                        app_version=__version__)


def selftest_docx(out_docx: str, dxf_paths: list[str]) -> int:
    """Validate the bundled template and fill it in (works without Word, e.g. on CI)."""
    import tempfile
    from tallycraft.packing_docx import bundled_template, render_docx, validate_template

    template = bundled_template()
    errors, warnings = validate_template(template)
    if errors or warnings:
        print("\n".join(errors + warnings), file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as work:
        render_docx(_selftest_record(dxf_paths), template, out_docx, work)
    return 0


def selftest_pdf(out_pdf: str, dxf_paths: list[str]) -> int:
    """Like --selftest-docx, then convert to PDF the way the app does (Automatic =
    LibreOffice if installed, else Word; TALLYCRAFT_PDF_ENGINE=word|libreoffice forces one).
    Writes the engine used to "<out>.engine.txt"."""
    import os
    from pathlib import Path
    from tallycraft.pdf_convert import convert

    docx = str(Path(out_pdf).with_suffix(".docx"))
    code = selftest_docx(docx, dxf_paths)
    if code:
        return code
    engine = convert(docx, out_pdf, os.environ.get("TALLYCRAFT_PDF_ENGINE", "auto"))
    Path(out_pdf + ".engine.txt").write_text(engine, encoding="utf-8")
    return 0


def _run_selftest(func, out: str, args: list[str]) -> int:
    """The packaged exe has no console, so failures go to "<out>.error.txt" (and exit
    code 3) instead of PyInstaller's blocking error dialog."""
    try:
        return func(out, args)
    except BaseException:
        import traceback
        with open(out + ".error.txt", "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        return 3


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        sys.exit(_run_selftest(selftest, sys.argv[2], sys.argv[3:]))
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest-docx":
        sys.exit(_run_selftest(selftest_docx, sys.argv[2], sys.argv[3:]))
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest-pdf":
        sys.exit(_run_selftest(selftest_pdf, sys.argv[2], sys.argv[3:]))
    from tallycraft.gui import main
    main()
