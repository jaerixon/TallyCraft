import json
import math

import pytest

from tallycraft.calc import ControlSample, PieceInput, SkippedLine, calculate
from tallycraft.order import Order, Package, merge_order
from tallycraft.packing import (RecordError, build_record, calibration_text, default_filename, items_ordered,
                                parse_order_date, part_name, picture_from_parsed, simplify, validate_record)
from tallycraft.pieces import PieceRow
from tallycraft.storage import PresetError, Storage

_ids = iter(range(100_000))


def add(pkg, row):
    iid = f"r{next(_ids)}"
    pkg.rows[iid] = row
    pkg.order.append(iid)


@pytest.fixture
def order(dxf):
    def rect(name, w, h, hole=False):
        doc, msp = dxf.new(insunits=1)
        dxf.rect_lines(msp, 0, 0, w, h)
        if hole:
            msp.add_circle((w / 2, h / 2), min(w, h) / 4)
        return dxf.save(doc, name)
    doc, msp = dxf.new()
    msp.add_line((0, 0), (4, 0))
    msp.add_line((4, 0), (4, 2))
    gap = dxf.save(doc, "gap.dxf")
    a = Package("XL Standard Box", quantity=2, preset_name="XL Standard Box")
    add(a, PieceRow.load(rect("side.dxf", 4, 2, hole=True), count=2))
    add(a, PieceRow.load(rect("floor.dxf", 6, 3), count=1))
    b = Package("XL Tunnel + Ramp", quantity=1, preset_name="XL Tunnel + Ramp")
    add(b, PieceRow.load(rect("side.dxf", 4, 2, hole=True), count=3))
    add(b, PieceRow.load(gap, count=1))
    return Order([a, b])


def make_record(order, **over):
    labels, merged = merge_order(order)
    rows = {r.path: r for _p, _i, r in order.all_rows()}
    cal = ControlSample(4, 2, "in", 23.456)
    res = calculate([PieceInput(m.name, m.area_cm2, m.total_count, m.kit_counts) for m in merged if not m.error],
                    cal, [SkippedLine(m.name, m.total_count, m.error, m.kit_counts) for m in merged if m.error],
                    tuple(labels))
    info = {m.name: {"path": m.path, "unit": rows[m.path].unit, "picture": picture_from_parsed(rows[m.path].parsed)}
            for m in merged}
    kw = dict(customer={"name": "Jordan Rivera", "address": "123 Maple St\nSpringfield, IL", "etsy_order": "3141592",
                        "order_date": "2026-09-27", "note": "Thanks!"},
              shop={"name": "Bun Homes Co.", "logo": None},
              packages=[{"name": p.name, "preset_name": p.preset_name, "quantity": p.quantity,
                         "unsaved_changes": False, "pieces": p.pieces_spec()} for p in order.packages],
              calibration={"method": "control", "length": "4", "width": "2", "unit": "in", "weight_g": "23.456",
                           "grams_per_cm2": cal.grams_per_cm2, "preset_name": "DixiePly"},
              result=res, pieces_info=info, calculated_at="2026-09-28T10:15:00", created_at="2026-09-28T10:20:00",
              app_version="0.4.0")
    kw.update(over)
    return build_record(**kw)


# ---------------------------------------------------------------- record

def test_record_contents(order):
    rec = make_record(order)
    assert validate_record(rec) is rec
    assert rec["order"]["items_ordered"] == "2x XL Standard Box, 1x XL Tunnel + Ramp"
    assert rec["results"]["kit_labels"] == ["XL Standard Box (1 of 2)", "XL Standard Box (2 of 2)", "XL Tunnel + Ramp"]
    lines = {l["name"]: l for l in rec["results"]["lines"]}
    assert lines["side.dxf"]["kit_counts"] == [2, 2, 3] and lines["side.dxf"]["total_count"] == 7
    gap = lines["gap.dxf"]
    assert gap["skipped"] and gap["weight_per_piece_g"] is None and gap["kit_counts"] == [None, None, 1]
    assert "gap" in gap["reason"]
    assert rec["results"]["skipped_count"] == 1
    side_pic = lines["side.dxf"]["picture"]
    assert sorted(side_pic["depths"]) == [0, 1] and side_pic["bbox"] == [4.0, 2.0]
    assert rec["order"]["packages"][0]["pieces"][0]["count"] == 2  # full order embedded


def test_record_is_plain_json(order):
    rec = make_record(order)
    assert json.loads(json.dumps(rec)) == rec


@pytest.mark.parametrize("breakage, fragment", [
    (lambda r: r.update(type="x"), "isn't a TallyCraft packing list"),
    (lambda r: r.update(version=99), "different TallyCraft version"),
    (lambda r: r.pop("results"), "missing its results"),
    (lambda r: r["customer"].update(name="  "), "no customer name"),
    (lambda r: r["results"].update(lines="x"), "damaged"),
])
def test_validate_record_rejects(order, breakage, fragment):
    rec = make_record(order)
    breakage(rec)
    with pytest.raises(RecordError, match=fragment):
        validate_record(rec)


# ---------------------------------------------------------------- helpers

def test_simplify_keeps_shape_and_drops_collinear():
    line = [(i / 10, 0.0) for i in range(101)]
    assert simplify(line, 1e-6) == [(0.0, 0.0), (10.0, 0.0)]
    circle = [(math.cos(t / 90 * math.pi), math.sin(t / 90 * math.pi)) for t in range(181)]
    s = simplify(circle, 0.01)
    assert 8 < len(s) < 60 and s[0] == circle[0] and s[-1] == circle[-1]


def test_filenames_and_dates():
    assert default_filename("2026-09-27", "Jordan Rivera", "3141592") == "2026-09-27 - Jordan Rivera - 3141592"
    assert default_filename("2026-09-27", "A/B: C?", "") == "2026-09-27 - A_B_ C_"
    assert parse_order_date(" 2026-09-27 ") == "2026-09-27"
    with pytest.raises(ValueError, match="year-month-day"):
        parse_order_date("9/27/2026")
    assert items_ordered([{"name": "A", "quantity": 2}, {"name": "B", "quantity": 1}]) == "2x A, 1x B"
    assert part_name("Front Panel.DXF") == "Front Panel" and part_name("readme.txt") == "readme.txt"


def test_calibration_text():
    ref = {"method": "reference", "piece_name": "Rear Panel.DXF", "package": "XL Standard Box", "quantity": "10",
           "weight_g": "1234.567", "area_cm2": 1272.98, "grams_per_cm2": 0.1, "preset_name": "Batch 7"}
    text = calibration_text(ref)
    assert "reference piece \"Rear Panel.DXF\" from package \"XL Standard Box\", 10 weighed, total 1234.567 g" in text
    assert "0.10000 g/cm²" in text and "Calibration preset: \"Batch 7\"" in text


# ---------------------------------------------------------------- storage

def test_packing_paths_never_overwrite(tmp_path, order):
    s = Storage(tmp_path)
    s.ensure_folders()
    j1, p1 = s.packing_paths("2026-09-27 - Jordan - 1")
    s.save_packing_record(j1, make_record(order))
    j2, p2 = s.packing_paths("2026-09-27 - Jordan - 1")
    assert j2.name == "2026-09-27 - Jordan - 1 (2).json" and p2.suffix == ".pdf"
    assert [e.name for e in s.list_packing_lists()] == ["2026-09-27 - Jordan - 1"]
    assert s.load_packing_record(j1)["customer"]["name"] == "Jordan Rivera"


def test_load_bad_record(tmp_path):
    s = Storage(tmp_path)
    s.ensure_folders()
    (s.packing_dir / "x.json").write_text('{"type": "nope"}', encoding="utf-8")
    with pytest.raises(PresetError, match="isn't a TallyCraft packing list"):
        s.load_packing_record(s.packing_dir / "x.json")


def test_settings_new_keys(tmp_path):
    s = Storage(tmp_path)
    loaded = s.load_settings()[0]
    assert loaded["shop_name"] == "" and loaded["logo_path"] is None and loaded["default_note"]
    s.settings_path.write_text(json.dumps({"shop_name": 5, "logo_path": "  ", "default_note": None}), encoding="utf-8")
    loaded = s.load_settings()[0]
    assert loaded["shop_name"] == "" and loaded["logo_path"] is None and loaded["default_note"] == "Thank you for your order!"
