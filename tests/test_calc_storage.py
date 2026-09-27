import json
import os
import time

import pytest

from tallycraft.calc import (ControlSample, PieceInput, SkippedLine, calculate, format_lb_oz,
                             grams_to_lb_oz, parse_positive, results_as_text, validate_control)
from tallycraft.messages import Level
from tallycraft.pieces import PieceRow
from tallycraft.storage import PresetError, Storage, safe_filename

# ---------------------------------------------------------------- calc


def test_parse_positive_accepts_three_plus_decimals():
    assert parse_positive(" 4.1255 ", "Length") == 4.1255


@pytest.mark.parametrize("text, fragment", [
    ("", "empty"), ("abc", "isn't a number"), ("0", "greater than 0"),
    ("-2", "greater than 0"), ("nan", "usable"), ("inf", "usable"),
])
def test_parse_positive_rejects(text, fragment):
    with pytest.raises(ValueError, match=fragment):
        parse_positive(text, "Length")


def test_validate_control_reports_every_bad_field():
    sample, errors = validate_control("x", "0", "in", "")
    assert sample is None and len(errors) == 3
    assert any("Length" in e for e in errors) and any("Weight" in e for e in errors)


def test_mixed_units_are_normalized():
    # Control: 2 in x 4 in = 8 in² = 51.6128 cm², 20 g
    control = ControlSample(2, 4, "in", 20.0)
    # Piece: 50.8 mm x 101.6 mm (same physical size) -> same weight
    piece_cm2 = 50.8 * 101.6 * 0.01
    res = calculate([PieceInput("a", piece_cm2, 3)], control)
    assert res.lines[0].weight_per_piece_g == pytest.approx(20.0)
    assert res.lines[0].item_total_g == pytest.approx(60.0)
    assert res.total_g == pytest.approx(60.0)


def test_skipped_rows_are_excluded_and_flagged():
    control = ControlSample(2, 4, "in", 20.0)  # 20 g per 8 in²
    per_in2_cm2 = 2.54 ** 2
    res = calculate([PieceInput("a", 8 * per_in2_cm2, 2)], control,
                    skipped=[SkippedLine("bad.dxf", 3, "The outline has a gap"),
                             SkippedLine("worse.dxf", 1, "File not found")])
    assert res.total_g == pytest.approx(40.0)  # skipped rows contribute nothing
    assert res.incomplete and res.incomplete_note == "Incomplete: 2 files skipped"
    text = results_as_text(res)
    assert "bad.dxf\tSkipped - not included\t3" in text
    assert "INCOMPLETE: 2 FILES SKIPPED" in text
    assert "Skipped: worse.dxf - File not found" in text


def test_complete_result_has_no_note():
    res = calculate([PieceInput("a", 1.0, 1)], ControlSample(1, 1, "in", 1.0))
    assert not res.incomplete and res.incomplete_note == ""
    assert "INCOMPLETE" not in results_as_text(res)
    one = calculate([], ControlSample(1, 1, "in", 1.0), skipped=[SkippedLine("x", 1, "r")])
    assert one.incomplete_note == "Incomplete: 1 file skipped"


def test_lb_oz_conversion_and_carry():
    assert grams_to_lb_oz(453.59237) == (1, 0.0)
    assert grams_to_lb_oz(453.59237 * 2 - 0.5) == (2, 0.0)  # 15.98 oz rounds up and carries
    assert format_lb_oz(1000) == "2 lb 3.3 oz"
    assert format_lb_oz(0) == "0 lb 0.0 oz"

# ---------------------------------------------------------------- row model


def test_row_unit_override_reinterprets_raw_numbers(dxf):
    doc, msp = dxf.new(insunits=4)
    dxf.rect_lines(msp, 0, 0, 4, 2)
    row = PieceRow.load(dxf.save(doc))
    assert row.unit == "mm" and row.area_cm2 == pytest.approx(0.08)
    row.unit = "in"  # user says the header was wrong
    assert row.area_cm2 == pytest.approx(8 * 2.54 ** 2)
    assert row.area_text() == "8.000 in²"
    assert row.bbox_text() == "4.000 × 2.000 in"
    assert row.status == Level.INFO  # "Units manually set" note


def test_row_unknown_units_block_until_chosen(dxf):
    doc, msp = dxf.new(insunits=0)
    dxf.rect_lines(msp, 0, 0, 4, 2)
    row = PieceRow.load(dxf.save(doc))
    assert row.status == Level.ERROR and row.area_cm2 is None
    row.unit = "mm"
    assert row.status == Level.INFO and row.area_cm2 == pytest.approx(0.08)


def test_row_flags_file_modified_since_preset(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 4, 2)
    path = dxf.save(doc)
    old = os.path.getmtime(path) - 3600
    row = PieceRow.load(path, stored_mtime=old)
    assert row.status == Level.WARNING
    assert any("modified since this preset" in m.text for m in row.messages)
    same = PieceRow.load(path, stored_mtime=os.path.getmtime(path))
    assert same.status == Level.OK

# ---------------------------------------------------------------- storage


def test_safe_filename():
    assert safe_filename('XL: "Complete" Set?') == "XL_ _Complete_ Set_"
    assert safe_filename("CON") == "_CON"
    with pytest.raises(PresetError):
        safe_filename("  ")


def test_package_round_trip(tmp_path):
    s = Storage(tmp_path)
    s.ensure_folders()
    pieces = [{"path": "C:/a.dxf", "units": "in", "count": 2, "mtime": 123.0}]
    s.save_package("XL Complete Set", pieces)
    assert [e.name for e in s.list_packages()] == ["XL Complete Set"]
    data = s.load_package("XL Complete Set")
    assert data["pieces"] == pieces


def test_control_round_trip_keeps_exact_text(tmp_path):
    s = Storage(tmp_path)
    s.save_control("DixiePly 120526", "4.000", "2.0005", "in", "23.4567")
    c = s.load_control("DixiePly 120526")
    assert (c["length"], c["width"], c["unit"], c["weight_g"]) == ("4.000", "2.0005", "in", "23.4567")


def test_damaged_preset_gives_friendly_error(tmp_path):
    s = Storage(tmp_path)
    s.ensure_folders()
    (s.control_dir / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PresetError, match="damaged"):
        s.load_control("bad")


def test_wrong_kind_rejected(tmp_path):
    s = Storage(tmp_path)
    s.save_package("P", [])
    (s.control_dir).mkdir(exist_ok=True)
    (s.control_dir / "P.json").write_bytes((s.package_dir / "P.json").read_bytes())
    with pytest.raises(PresetError, match="isn't a TallyCraft control preset"):
        s.load_control("P")


@pytest.mark.parametrize("stored, expected", [(1.25, 1.25), (9, 2.5), (0.1, 0.8), ("big", 1.0),
                                              (None, 1.0), (True, 1.0)])
def test_text_scale_is_restored_and_sanitized(tmp_path, stored, expected):
    s = Storage(tmp_path)
    s.settings_path.write_text(json.dumps({"text_scale": stored}), encoding="utf-8")
    assert s.load_settings()[0]["text_scale"] == expected


def test_settings_defaults_and_corrupt_backup(tmp_path):
    s = Storage(tmp_path)
    settings, warn = s.load_settings()
    assert warn is None and settings["ignored_layer_names"] == ["CONSTRUCTION", "DEFPOINTS"]
    settings["default_control_preset"] = "X"
    s.save_settings(settings)
    assert s.load_settings()[0]["default_control_preset"] == "X"
    s.settings_path.write_text("[[[", encoding="utf-8")
    settings, warn = s.load_settings()
    assert warn and "settings.json.bak" in warn
    assert settings["default_control_preset"] is None
    assert (tmp_path / "settings.json.bak").exists()
