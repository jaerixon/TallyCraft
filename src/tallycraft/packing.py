"""Packing lists: a record of one actual shipment (SPEC §9).

The JSON *record* is the source of truth. Documents are always generated from
the record (packing_docx.render_docx fills the user's Word template; word_pdf
converts it), both when the list is created and on re-print, so a re-print
never re-reads DXF files. Part pictures are therefore stored in the record,
simplified to thumbnail precision.
"""

from __future__ import annotations

import base64
import math
import re
from datetime import date

from .calc import CalcResult, SkippedLine

RECORD_KIND = "tallycraft.packing_list"
RECORD_VERSION = 1
PICTURE_TOLERANCE_REL = 1 / 1500  # of the part's bounding-box diagonal: invisible at thumbnail size

Point = tuple[float, float]


# ---------------------------------------------------------------- geometry for pictures

def simplify(points: list[Point], tol: float) -> list[Point]:
    """Ramer–Douglas–Peucker simplification of a polyline (iterative)."""
    if len(points) < 3 or tol <= 0:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = points[a], points[b]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        best, best_d = None, tol
        for i in range(a + 1, b):
            px, py = points[i]
            d = (abs(dy * (px - x1) - dx * (py - y1)) / norm) if norm else math.hypot(px - x1, py - y1)
            if d > best_d:
                best, best_d = i, d
        if best is not None:
            keep[best] = True
            stack += [(a, best), (best, b)]
    return [p for p, k in zip(points, keep) if k]


def _simplify_loop(loop: list[Point], tol: float) -> list[Point]:
    # Split a closed loop at its farthest point from the start so both halves have real endpoints.
    if len(loop) < 4:
        return list(loop)
    far = max(range(len(loop)), key=lambda i: math.dist(loop[0], loop[i]))
    first = simplify(loop[:far + 1], tol)
    second = simplify(loop[far:] + [loop[0]], tol)
    out = first[:-1] + second[:-1]
    return out if len(out) >= 3 else list(loop)


def picture_from_parsed(parsed) -> dict:
    """Outline/hole geometry for a part picture, in raw file units."""
    engrave = getattr(parsed, "engrave", None) or []
    pts = ([p for l in parsed.loops for p in l] + [p for c in parsed.open_chains for p in c]
           + [p for e in engrave for p in e])
    if not pts:
        return {"loops": [], "depths": [], "open": [], "engrave": [], "bbox": None}
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    tol = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) * PICTURE_TOLERANCE_REL

    def r(seq):
        return [[round(x, 5), round(y, 5)] for x, y in seq]

    depths = parsed.loop_depths if len(parsed.loop_depths) == len(parsed.loops) else [0] * len(parsed.loops)
    return {"loops": [r(_simplify_loop(l, tol)) for l in parsed.loops],
            "depths": list(depths),
            "open": [r(simplify(c, tol)) for c in parsed.open_chains],
            "engrave": [r(simplify(e, tol)) for e in engrave],  # drawn lighter; never measured
            "bbox": list(parsed.bbox_raw) if parsed.bbox_raw else None}


# ---------------------------------------------------------------- text helpers

def items_ordered(packages: list[dict]) -> str:
    """e.g. "2x XL Standard Box, 1x XL Tunnel + Ramp"."""
    return ", ".join(f"{p['quantity']}x {p['name']}" for p in packages)


def default_filename(order_date: str, customer: str, order_number: str) -> str:
    """ "<date> - <customer name> - <order #>" (order # left out when blank), safe for Windows."""
    parts = [order_date.strip(), customer.strip(), order_number.strip()]
    name = " - ".join(p for p in parts if p)
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .")[:150] or "Packing list"


def parse_order_date(text: str) -> str:
    """Accepts YYYY-MM-DD; returns it normalized. Raises ValueError with a plain message."""
    raw = (text or "").strip()
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        raise ValueError(f"Order date \"{raw}\" should look like {date.today().isoformat()} (year-month-day).") from None


def encode_logo(data: bytes, filename: str) -> dict:
    ext = filename.rsplit(".", 1)[-1].lower()
    return {"filename": filename, "format": "jpeg" if ext in ("jpg", "jpeg") else ext,
            "data_base64": base64.b64encode(data).decode("ascii")}


def decode_logo(logo: dict | None) -> bytes | None:
    if not logo or not logo.get("data_base64"):
        return None
    try:
        return base64.b64decode(logo["data_base64"])
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------- record

def build_record(*, customer: dict, shop: dict, packages: list[dict], calibration: dict, result: CalcResult,
                 pieces_info: dict[str, dict], calculated_at: str, created_at: str, app_version: str) -> dict:
    """Everything needed to reproduce the packing list exactly.

    pieces_info: result line name -> {"path", "unit", "picture"} (picture from picture_from_parsed).
    """
    lines = []
    for item in list(result.lines) + list(result.skipped):
        skipped = isinstance(item, SkippedLine)
        info = pieces_info.get(item.name, {})
        lines.append({
            "name": item.name,
            "display_name": info.get("display_name", "") or "",
            "path": info.get("path", ""),
            "unit": info.get("unit", ""),
            "kit_counts": list(item.kit_counts),
            "total_count": item.count,
            "weight_per_piece_g": None if skipped else item.weight_per_piece_g,
            "item_total_g": None if skipped else item.item_total_g,
            "skipped": skipped,
            "reason": item.reason if skipped else "",
            "picture": info.get("picture") or {"loops": [], "depths": [], "open": [], "bbox": None},
        })
    return {
        "type": RECORD_KIND, "version": RECORD_VERSION,
        "app_version": app_version,
        "created_at": created_at,
        "calculated_at": calculated_at,
        "customer": {k: customer.get(k, "") for k in ("name", "address", "etsy_order", "order_date", "note")},
        "shop": {"name": shop.get("name", ""), "logo": shop.get("logo")},
        "order": {"items_ordered": items_ordered(packages), "packages": packages},
        "calibration": calibration,
        "results": {
            "kit_labels": list(result.kit_labels),
            "lines": lines,
            "total_g": result.total_g,
            "grams_per_cm2": result.grams_per_cm2,
            "skipped_count": len(result.skipped),
        },
    }


class RecordError(ValueError):
    """A packing-list record that can't be used, phrased for the user."""


def validate_record(data) -> dict:
    if not isinstance(data, dict) or data.get("type") != RECORD_KIND:
        raise RecordError("This isn't a TallyCraft packing list record.")
    if data.get("version") != RECORD_VERSION:
        raise RecordError(f"This packing list was made by a different TallyCraft version "
                          f"(record version {data.get('version')!r}).")
    for key in ("customer", "order", "calibration", "results"):
        if not isinstance(data.get(key), dict):
            raise RecordError(f"The packing list record is missing its {key} section.")
    res = data["results"]
    if not isinstance(res.get("lines"), list) or not isinstance(res.get("kit_labels"), list):
        raise RecordError("The packing list record's results are damaged.")
    if not str(data["customer"].get("name", "")).strip():
        raise RecordError("The packing list record has no customer name.")
    return data


# ---------------------------------------------------------------- shared text helpers (viewer + template)

def now_stamp() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def stamp(iso) -> str:
    """ "2026-09-28T10:15:00" -> "2026-09-28 10:15"."""
    text = str(iso or "")
    return text[:16].replace("T", " ") if len(text) >= 16 else text


def part_name(file_name: str) -> str:
    """Part names without the .dxf extension read better on paper."""
    import os
    root, ext = os.path.splitext(file_name)
    return root if ext.lower() == ".dxf" else file_name


def calibration_text(cal: dict) -> str:
    """One sentence describing the calibration, for the shop record and viewer."""
    g = cal.get("grams_per_cm2")
    ratio = f"{g:.5f} g/cm² ({g * 6.4516:.5f} g/in²)" if isinstance(g, (int, float)) else "unknown"
    if cal.get("method") == "reference":
        pkg = f" from package \"{cal['package']}\"" if cal.get("package") else ""
        src = (f"reference piece \"{cal.get('piece_name', '')}\"{pkg}, "
               f"{cal.get('quantity', '')} weighed, total {cal.get('weight_g', '')} g")
        if cal.get("area_cm2"):
            src += f", piece net area {cal['area_cm2']:.4f} cm²"
        if cal.get("from_preset"):
            src += f" (area taken from saved preset \"{cal['from_preset']}\")"
    else:
        src = (f"control sample {cal.get('length', '')} × {cal.get('width', '')} {cal.get('unit', '')}, "
               f"weight {cal.get('weight_g', '')} g")
    preset = f" Calibration preset: \"{cal['preset_name']}\"." if cal.get("preset_name") else ""
    return f"Calibration: {src} → {ratio}.{preset}"
