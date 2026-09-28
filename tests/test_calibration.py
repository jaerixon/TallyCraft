import json
import os

import pytest

from tallycraft.calc import ControlSample, PieceInput, calculate, results_as_text
from tallycraft.calibration import (ReferencePiece, SavedReference, describe, parse_positive_int,
                                    validate_reference)
from tallycraft.pieces import PieceRow
from tallycraft.storage import PresetError, Storage

IN2_TO_CM2 = 2.54 ** 2


@pytest.fixture
def rect_row(dxf):
    """A 4 × 2 in rectangle: net area 8 in² = 51.6128 cm²."""
    doc, msp = dxf.new(insunits=1)
    dxf.rect_lines(msp, 0, 0, 4, 2)
    return PieceRow.load(dxf.save(doc, "rect.dxf"))


# ---------------------------------------------------------------- math

def test_reference_ratio_math(rect_row):
    ref, errors, warnings = validate_reference(rect_row, "10", "234.56")
    assert errors == [] and warnings == []
    assert ref.grams_per_cm2 == pytest.approx(234.56 / (10 * 8 * IN2_TO_CM2))


def test_reference_and_control_agree_for_same_material(rect_row):
    # A 2x4 in control sample weighing 23.456 g, and 10 of the 4x2 pieces weighing 234.56 g,
    # describe the same plywood, so every downstream weight must match.
    control = ControlSample(2, 4, "in", 23.456)
    ref, _, _ = validate_reference(rect_row, "10", "234.56")
    pieces = [PieceInput("a", 100.0, 3), PieceInput("b", 12.5, 7)]
    a, b = calculate(pieces, control), calculate(pieces, ref)
    assert b.total_g == pytest.approx(a.total_g)
    assert [l.weight_per_piece_g for l in b.lines] == pytest.approx([l.weight_per_piece_g for l in a.lines])


def test_reference_uses_row_units_and_overrides(dxf):
    doc, msp = dxf.new(insunits=4)  # header says mm
    dxf.rect_lines(msp, 0, 0, 100, 50)
    row = PieceRow.load(dxf.save(doc))
    ref, _, _ = validate_reference(row, "1", "10")
    assert ref.area_cm2 == pytest.approx(50.0)  # 5000 mm² = 50 cm²
    row.unit = "in"  # the user corrects the Units column
    ref2, _, _ = validate_reference(row, "1", "10")
    assert ref2.area_cm2 == pytest.approx(5000 * IN2_TO_CM2)


def test_reference_uses_net_area_with_holes(dxf):
    doc, msp = dxf.new(insunits=1)
    dxf.rect_lines(msp, 0, 0, 10, 10)
    dxf.rect_lines(msp, 2, 2, 4, 4)
    row = PieceRow.load(dxf.save(doc))
    ref, _, _ = validate_reference(row, "2", "100")
    assert ref.area_cm2 == pytest.approx(96 * IN2_TO_CM2)


# ---------------------------------------------------------------- validation

@pytest.mark.parametrize("qty, weight, fragment", [
    ("", "10", "Quantity weighed is empty"), ("2.5", "10", "whole number"), ("0", "10", "1 or more"),
    ("-3", "10", "1 or more"), ("abc", "10", "whole number"),
    ("5", "", "Total weight (g) is empty"), ("5", "0", "greater than 0"), ("5", "x", "isn't a number"),
])
def test_bad_quantity_or_weight(rect_row, qty, weight, fragment):
    ref, errors, _ = validate_reference(rect_row, qty, weight)
    assert ref is None and any(fragment in e for e in errors), errors


def test_no_piece_selected():
    ref, errors, _ = validate_reference(None, "1", "10")
    assert ref is None and "Choose the reference piece" in errors[0]


def test_removed_piece_reason_is_reported():
    ref, errors, _ = validate_reference(None, "1", "10", removed_note="The reference piece x.dxf was removed")
    assert errors[0].startswith("The reference piece x.dxf was removed")


def test_error_row_is_rejected(dxf):
    doc, msp = dxf.new()
    msp.add_line((0, 0), (4, 0))
    msp.add_line((4, 0), (4, 2))
    row = PieceRow.load(dxf.save(doc, "gap.dxf"))
    ref, errors, _ = validate_reference(row, "1", "10")
    assert ref is None and "can't be trusted" in errors[0] and "gap" in errors[0]


def test_unknown_units_row_is_rejected(dxf):
    doc, msp = dxf.new(insunits=0)
    dxf.rect_lines(msp, 0, 0, 4, 2)
    row = PieceRow.load(dxf.save(doc))
    ref, errors, _ = validate_reference(row, "1", "10")
    assert ref is None and "units are Unknown" in errors[0]


def test_warning_row_is_usable_but_reports_warning(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 4, 2)
    path = dxf.save(doc)
    row = PieceRow.load(path, stored_mtime=os.path.getmtime(path) - 3600)  # "modified since preset"
    ref, errors, warnings = validate_reference(row, "1", "10")
    assert ref is not None and errors == []
    assert any("modified since this preset" in w for w in warnings)


def test_saved_fallback_uses_saved_area():
    saved = SavedReference("Front.dxf", "C:/x/Front.dxf", area_cm2=50.0, preset="Batch 7")
    ref, errors, _ = validate_reference(None, "4", "100", saved=saved)
    assert errors == [] and ref.from_preset == "Batch 7"
    assert ref.grams_per_cm2 == pytest.approx(100 / (4 * 50.0))


def test_parse_positive_int():
    assert parse_positive_int(" 12 ", "Q") == 12


def test_describe_lines():
    ref = ReferencePiece("Front.dxf", "p", 10, 234.56, 51.6128)
    assert describe(ref).startswith("Calibration: reference piece Front.dxf, 10 weighed, 234.56 g total")
    saved = ReferencePiece("Front.dxf", "p", 10, 234.56, 51.6128, from_preset="B7")
    assert "area from saved preset \"B7\"" in describe(saved)
    assert describe(ControlSample(2, 4, "in", 23.456)).startswith("Calibration: control sample 2 × 4 in, 23.456 g")


def test_copy_text_includes_calibration_line():
    res = calculate([PieceInput("a", 1.0, 1)], ControlSample(1, 1, "in", 1.0))
    assert results_as_text(res, "Calibration: x").splitlines()[-1] == "Calibration: x"
    assert "Calibration" not in results_as_text(res)


# ---------------------------------------------------------------- presets & settings

def test_reference_preset_round_trip(tmp_path):
    s = Storage(tmp_path)
    s.save_reference("Batch 7", "C:/kits/Front.dxf", "Front.dxf", "10", "234.560", 0.4545, 51.6128)
    d = s.load_control("Batch 7")
    assert d == {"method": "reference", "name": "Batch 7", "reference_path": "C:/kits/Front.dxf",
                 "reference_name": "Front.dxf", "quantity": "10", "weight_g": "234.560",
                 "grams_per_cm2": 0.4545, "area_cm2": 51.6128}


def test_old_control_preset_without_method_still_loads(tmp_path):
    s = Storage(tmp_path)
    s.ensure_folders()
    legacy = {"type": "tallycraft.control", "version": 1, "name": "Old", "length": "4.000",
              "width": "2", "unit": "in", "weight_g": "23.456"}  # v0.1.0 format
    (s.control_dir / "Old.json").write_text(json.dumps(legacy), encoding="utf-8")
    d = s.load_control("Old")
    assert d == {"method": "control", "name": "Old", "length": "4.000", "width": "2", "unit": "in",
                 "weight_g": "23.456"}


def test_new_control_preset_records_method(tmp_path):
    s = Storage(tmp_path)
    s.save_control("C", "4", "2", "mm", "1.5")
    assert json.loads(s.control_path("C").read_text())["method"] == "control"
    assert s.load_control("C")["method"] == "control"


@pytest.mark.parametrize("patch, fragment", [
    ({"reference_path": ""}, "which reference piece"),
    ({"grams_per_cm2": 0}, "g/cm²"),
    ({"grams_per_cm2": "abc"}, "g/cm²"),
    ({"method": "guess"}, "unknown calibration method"),
])
def test_bad_reference_presets(tmp_path, patch, fragment):
    s = Storage(tmp_path)
    s.save_reference("B", "C:/a.dxf", "a.dxf", "1", "2", 0.5, 4.0)
    data = json.loads(s.control_path("B").read_text())
    data.update(patch)
    s.control_path("B").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(PresetError, match=fragment):
        s.load_control("B")


def test_reference_preset_missing_area_is_tolerated(tmp_path):
    s = Storage(tmp_path)
    s.save_reference("B", "C:/a.dxf", "a.dxf", "1", "2", 0.5, 4.0)
    data = json.loads(s.control_path("B").read_text())
    del data["reference_area_cm2"]
    s.control_path("B").write_text(json.dumps(data), encoding="utf-8")
    assert s.load_control("B")["area_cm2"] is None


@pytest.mark.parametrize("stored, mode, split_in, split_out", [
    ("control", "control", 0.4, 0.4), ("weird", "reference", 5, 0.85), (None, "reference", "x", None),
    ("reference", "reference", 0.01, 0.15),
])
def test_settings_mode_and_split(tmp_path, stored, mode, split_in, split_out):
    s = Storage(tmp_path)
    s.settings_path.write_text(json.dumps({"calibration_mode": stored, "main_split": split_in}), encoding="utf-8")
    loaded = s.load_settings()[0]
    assert loaded["calibration_mode"] == mode and loaded["main_split"] == split_out


def test_settings_defaults_include_new_keys(tmp_path):
    loaded = Storage(tmp_path).load_settings()[0]
    assert loaded["calibration_mode"] == "reference" and loaded["main_split"] is None
