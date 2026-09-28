import json
import os

import pytest

from tallycraft.calc import (ControlSample, PieceInput, SkippedLine, calculate, results_as_text)
from tallycraft.messages import Level
from tallycraft.order import Order, Package, merge_order, norm_path
from tallycraft.pieces import PieceRow
from tallycraft.storage import PresetError, Storage
from tallycraft.table_sort import order_results

_ids = iter(range(10_000))


def add(pkg: Package, row: PieceRow) -> str:
    iid = f"r{next(_ids)}"
    pkg.rows[iid] = row
    pkg.order.append(iid)
    return iid


@pytest.fixture
def files(dxf):
    """Three DXFs: side (4x2 in), floor (6x3 in), gap (broken)."""
    def rect(name, w, h, units=1):
        doc, msp = dxf.new(insunits=units)
        dxf.rect_lines(msp, 0, 0, w, h)
        return dxf.save(doc, name)
    doc, msp = dxf.new()
    msp.add_line((0, 0), (4, 0))
    msp.add_line((4, 0), (4, 2))
    return {"side": rect("side.dxf", 4, 2), "floor": rect("floor.dxf", 6, 3), "gap": dxf.save(doc, "gap.dxf")}


# ---------------------------------------------------------------- step 1: model

def test_startup_order_is_one_blank_package():
    order = Order.with_blank_package()
    assert len(order.packages) == 1 and order.is_single_blank()
    assert order.packages[0].name == "New Package 1" and order.packages[0].quantity == 1
    assert order.packages[0].status_summary() == "Empty"


def test_blank_names_are_unique():
    order = Order.with_blank_package()
    order.packages.append(Package(order.unique_name("New Package")))
    assert [p.name for p in order.packages] == ["New Package 1", "New Package 2"]
    assert order.unique_name("XL Standard Box") == "XL Standard Box"


def test_unsaved_changes_tracks_edits_and_undo(files):
    pkg = Package("XL Standard Box", preset_name="XL Standard Box")
    add(pkg, PieceRow.load(files["side"], count=2))
    pkg.set_baseline(pkg.pieces_spec())
    assert not pkg.is_dirty and pkg.status_summary() == "OK"
    pkg.ordered_rows()[0].count = 3
    assert pkg.is_dirty and pkg.status_summary() == "unsaved changes"
    pkg.ordered_rows()[0].count = 2  # undoing the edit clears the marker
    assert not pkg.is_dirty
    pkg.ordered_rows()[0].unit = "mm"
    assert pkg.is_dirty
    pkg.ordered_rows()[0].unit = "in"
    add(pkg, PieceRow.load(files["floor"]))
    assert pkg.is_dirty


def test_baseline_without_units_means_header_units(files):
    pkg = Package("P", preset_name="P")
    add(pkg, PieceRow.load(files["side"]))
    pkg.set_baseline([{"path": files["side"], "units": None, "count": 1}])  # hand-written preset
    assert not pkg.is_dirty


def test_paths_are_normalized_case_insensitively(files):
    p = files["side"]
    assert norm_path(p) == norm_path(p.upper()) == norm_path(os.path.join(os.path.dirname(p), ".", "side.dxf"))


def test_mark_saved_links_preset_and_clears_marker(files):
    pkg = Package("New Package 1")
    add(pkg, PieceRow.load(files["side"]))
    assert pkg.is_dirty  # never saved
    pkg.mark_saved("Mini Tunnel + Ramp")
    assert (pkg.name, pkg.preset_name, pkg.is_dirty) == ("Mini Tunnel + Ramp", "Mini Tunnel + Ramp", False)


def test_status_summary_counts(files):
    pkg = Package("P", preset_name="P")
    add(pkg, PieceRow.load(files["gap"]))
    add(pkg, PieceRow.load(files["side"], stored_mtime=os.path.getmtime(files["side"]) - 3600))
    pkg.set_baseline(pkg.pieces_spec())
    assert pkg.status_summary() == "1 piece with errors · 1 warning"
    assert pkg.status_summary(conflicts=2) == "1 piece with errors · 1 warning · 2 units conflicts"


# ---------------------------------------------------------------- step 3: merge

def make_order(files, qty_a=2, qty_b=1):
    a = Package("XL Standard Box", quantity=qty_a, preset_name="XL Standard Box")
    add(a, PieceRow.load(files["side"], count=2))
    add(a, PieceRow.load(files["floor"], count=1))
    b = Package("Mini Tunnel + Ramp", quantity=qty_b, preset_name="Mini Tunnel + Ramp")
    add(b, PieceRow.load(files["side"].upper(), count=3))  # same file, different spelling
    return Order([a, b])


def test_kit_labels():
    order = Order([Package("XL Standard Box", quantity=2), Package("Mini Tunnel + Ramp", quantity=1)])
    assert order.kit_labels() == ["XL Standard Box (1 of 2)", "XL Standard Box (2 of 2)", "Mini Tunnel + Ramp"]


def test_merge_one_row_per_file_with_per_kit_counts(files):
    labels, merged = merge_order(make_order(files))
    assert labels == ["XL Standard Box (1 of 2)", "XL Standard Box (2 of 2)", "Mini Tunnel + Ramp"]
    by_name = {m.name: m for m in merged}
    assert set(by_name) == {"side.dxf", "floor.dxf"}
    side, floor = by_name["side.dxf"], by_name["floor.dxf"]
    assert side.kit_counts == (2, 2, 3) and side.total_count == 2 * 2 + 3
    assert floor.kit_counts == (1, 1, None) and floor.total_count == 2  # Mini doesn't use it
    assert side.error == "" and side.area_cm2 == pytest.approx(8 * 2.54 ** 2)


def test_merged_totals_equal_sum_of_kits(files):
    order = make_order(files)
    labels, merged = merge_order(order)
    control = ControlSample(2, 4, "in", 20.0)  # 2.5 g per in²
    res = calculate([PieceInput(m.name, m.area_cm2, m.total_count, m.kit_counts) for m in merged],
                    control, kit_labels=tuple(labels))
    # 2 XL kits: 2 sides (8 in²) + 1 floor (18 in²) = 34 in² each; 1 Mini: 3 sides = 24 in²
    assert res.total_g == pytest.approx((2 * 34 + 24) * 2.5)


def test_units_conflict_is_an_error_for_that_piece(files):
    order = make_order(files)
    order.packages[1].ordered_rows()[0].unit = "mm"
    _labels, merged = merge_order(order)
    side = next(m for m in merged if m.name == "side.dxf")
    assert "Units conflict" in side.error and "Millimeters in 'Mini Tunnel + Ramp'" in side.error
    assert side.area_cm2 is None
    assert order.units_conflicts() == {norm_path(files["side"]): {"XL Standard Box", "Mini Tunnel + Ramp"}}


def test_error_in_any_package_skips_piece(files):
    order = make_order(files)
    extra = PieceRow.load(files["gap"])
    add(order.packages[1], extra)
    _labels, merged = merge_order(order)
    gap = next(m for m in merged if m.name == "gap.dxf")
    assert gap.error and "(in package \"Mini Tunnel + Ramp\")" in gap.error
    assert gap.kit_counts == (None, None, 1)


def test_same_file_name_in_different_folders_is_disambiguated(tmp_path, dxf):
    import ezdxf
    paths = []
    for folder in ("XL", "Mini"):
        (tmp_path / folder).mkdir()
        doc = ezdxf.new(); doc.header["$INSUNITS"] = 1
        dxf.rect_lines(doc.modelspace(), 0, 0, 1, 1)
        doc.saveas(tmp_path / folder / "Pin.dxf")
        paths.append(str(tmp_path / folder / "Pin.dxf"))
    a, b = Package("A"), Package("B")
    add(a, PieceRow.load(paths[0]))
    add(b, PieceRow.load(paths[1]))
    _labels, merged = merge_order(Order([a, b]))
    assert sorted(m.name for m in merged) == ["Pin.dxf — Mini", "Pin.dxf — XL"]


def test_warnings_are_collected_with_package(files):
    order = make_order(files)
    order.packages[0].ordered_rows()[1].extra.append(
        __import__("tallycraft.messages", fromlist=["Message"]).Message(Level.WARNING, "check me"))
    _labels, merged = merge_order(order)
    floor = next(m for m in merged if m.name == "floor.dxf")
    assert floor.warnings == ("check me (in package \"XL Standard Box\")",)


def test_kit_columns_sort_numerically_and_skipped_stay_last(files):
    order = make_order(files)
    labels, merged = merge_order(order)
    res = calculate([PieceInput(m.name, m.area_cm2, m.total_count, m.kit_counts) for m in merged],
                    ControlSample(1, 1, "in", 1.0),
                    skipped=[SkippedLine("zz.dxf", 5, "gap", (None, None, 5))], kit_labels=tuple(labels))
    # Mini column (kit2): floor has a dash (= 0), side has 3
    assert [l.name for l in order_results(res.lines, res.skipped, "kit2", False)] == ["floor.dxf", "side.dxf", "zz.dxf"]
    assert [l.name for l in order_results(res.lines, res.skipped, "kit2", True)] == ["side.dxf", "floor.dxf", "zz.dxf"]


def test_copy_text_includes_per_kit_columns(files):
    labels, merged = merge_order(make_order(files))
    res = calculate([PieceInput(m.name, m.area_cm2, m.total_count, m.kit_counts) for m in merged],
                    ControlSample(1, 1, "in", 1.0),
                    skipped=[SkippedLine("gap.dxf", 1, "gap", (None, None, 1))], kit_labels=tuple(labels))
    lines = results_as_text(res).splitlines()
    assert lines[0] == ("File Name\tXL Standard Box (1 of 2)\tXL Standard Box (2 of 2)\tMini Tunnel + Ramp\t"
                        "Total Count\tWeight per piece (g)\tItem Total (g)")
    floor = next(l for l in lines if l.startswith("floor.dxf"))
    assert floor.split("\t")[1:5] == ["1", "1", "—", "2"]
    assert "gap.dxf\t—\t—\t1\t1\tSkipped - not included" in results_as_text(res)


# ---------------------------------------------------------------- step 4: order files

def test_order_round_trip(tmp_path, files):
    s = Storage(tmp_path)
    s.ensure_folders()
    assert (tmp_path / "order_presets").is_dir()
    order = make_order(files)
    payload = [{"name": p.name, "preset_name": p.preset_name, "quantity": p.quantity,
                "unsaved_changes": p.is_dirty, "pieces": p.pieces_spec()} for p in order.packages]
    s.save_order("Order 1234", payload)
    assert [e.name for e in s.list_orders()] == ["Order 1234"]
    data = s.load_order("Order 1234")
    assert [(p["name"], p["preset_name"], p["quantity"]) for p in data["packages"]] == [
        ("XL Standard Box", "XL Standard Box", 2), ("Mini Tunnel + Ramp", "Mini Tunnel + Ramp", 1)]
    assert data["packages"][0]["pieces"][0]["count"] == 2  # embedded pieces, not just the preset name


@pytest.mark.parametrize("packages, fragment", [([], "doesn't list any packages"),
                                                ([{"name": "x"}], "missing its list of pieces"),
                                                ([{"pieces": [{"count": 1}]}], "missing its file path")])
def test_bad_order_files(tmp_path, packages, fragment):
    s = Storage(tmp_path)
    s.ensure_folders()
    (s.order_dir / "bad.json").write_text(json.dumps({"type": "tallycraft.order", "packages": packages}),
                                          encoding="utf-8")
    with pytest.raises(PresetError, match=fragment):
        s.load_order("bad")


def test_existing_package_presets_load_unchanged(tmp_path):
    s = Storage(tmp_path)
    s.ensure_folders()
    v01 = {"type": "tallycraft.package", "version": 1, "name": "XL Standard Box", "saved_at": "2026-09-27T13:00:00",
           "pieces": [{"path": "C:/a.dxf", "units": "in", "count": 2, "mtime": 1790000000.0}]}
    (s.package_dir / "XL Standard Box.json").write_text(json.dumps(v01), encoding="utf-8")
    assert s.load_package("XL Standard Box") == {"name": "XL Standard Box", "pieces": v01["pieces"]}
