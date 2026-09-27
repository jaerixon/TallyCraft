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


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        sys.exit(selftest(sys.argv[2], sys.argv[3:]))
    from tallycraft.gui import main
    main()
