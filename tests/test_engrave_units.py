"""Color rule (black = cut, other colors = engrave only), LightBurn exports, and
the millimeter assumption for unitless files (SPEC §5.1, §5.4)."""

import math
from pathlib import Path

import ezdxf
import pytest

from tallycraft.dxf_geometry import (DEFAULT_CUT_COLORS, cut_colors_from_settings, parse_color_spec, parse_dxf,
                                     polygon_area)
from tallycraft.messages import Level
from tallycraft.packing import picture_from_parsed
from tallycraft.pieces import PieceRow

CIRCLE_RTOL = 5e-4
LB_FILE = Path(__file__).parent / "fixtures_private" / "Main Box - Front Panel - LB Test.dxf"


def texts(p, level=None):
    return [m.text for m in p.messages if level is None or m.level == level]


def rect(msp, x0, y0, x1, y1, **attribs):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for a, b in zip(pts, pts[1:] + pts[:1]):
        msp.add_line(a, b, dxfattribs=attribs)


# ---------------------------------------------------------------- the color rule

def test_aci7_bylayer_on_layer0_is_cut(dxf):
    doc, msp = dxf.new()
    rect(msp, 0, 0, 4, 2)  # default: BYLAYER on layer "0", which is ACI 7
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK and p.net_area_raw == pytest.approx(8.0) and p.engrave == []


def test_engraved_closed_shape_inside_panel_does_not_change_area(dxf):
    doc, msp = dxf.new()
    rect(msp, 0, 0, 10, 10)
    msp.add_circle((5, 5), 2, dxfattribs={"color": 3})  # green: engrave artwork, not a hole
    msp.add_lwpolyline([(1, 1), (3, 1), (3, 3), (1, 3)], close=True, dxfattribs={"color": 5})
    p = parse_dxf(dxf.save(doc))
    assert p.net_area_raw == pytest.approx(100.0)  # nothing subtracted
    assert len(p.loops) == 1 and len(p.engrave) == 2
    assert "2 engrave-only items drawn but not counted in weight." in texts(p, Level.INFO)
    assert p.status == Level.INFO


def test_open_engrave_lines_never_cause_gap_or_junction_errors(dxf):
    doc, msp = dxf.new()
    rect(msp, 0, 0, 10, 10)
    msp.add_line((0, 0), (5, 5), dxfattribs={"color": 1})  # touches a corner: would be a junction if cut
    msp.add_line((20, 20), (21, 25), dxfattribs={"color": 1})  # dangling: would be a gap if cut
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.INFO and p.net_area_raw == pytest.approx(100.0)
    assert not any("gap" in t or "three or more" in t for t in texts(p))


def test_true_color_black_is_cut_and_overrides_aci(dxf):
    doc, msp = dxf.new()
    rect(msp, 0, 0, 4, 2, color=1, true_color=0x000000)  # ACI red, but true color black -> cut
    msp.add_circle((2, 1), 0.5, dxfattribs={"color": 7, "true_color": 0xFF0000})  # true red -> engrave
    p = parse_dxf(dxf.save(doc))
    assert p.net_area_raw == pytest.approx(8.0) and len(p.engrave) == 1


def test_bylayer_resolution(dxf):
    doc, msp = dxf.new()
    doc.layers.add("CUT", color=7)
    doc.layers.add("ETCH", color=5)
    rect(msp, 0, 0, 4, 2, layer="CUT")
    msp.add_circle((2, 1), 0.5, dxfattribs={"layer": "ETCH"})  # BYLAYER -> blue -> engrave
    p = parse_dxf(dxf.save(doc))
    assert p.net_area_raw == pytest.approx(8.0) and len(p.engrave) == 1


def test_layer_true_color_black_is_cut(dxf):
    doc, msp = dxf.new()
    layer = doc.layers.add("TRUEBLACK", color=2)
    layer.dxf.true_color = 0x000000
    rect(msp, 0, 0, 4, 2, layer="TRUEBLACK")
    p = parse_dxf(dxf.save(doc))
    assert p.net_area_raw == pytest.approx(8.0) and p.engrave == []


@pytest.mark.parametrize("insert_color, cut", [(7, True), (3, False)])
def test_byblock_takes_the_block_references_color(dxf, insert_color, cut):
    doc, msp = dxf.new()
    blk = doc.blocks.new("PART")
    rect(blk, 0, 0, 2, 2, color=0)  # BYBLOCK
    msp.add_blockref("PART", (0, 0), dxfattribs={"color": insert_color})
    if not cut:
        rect(msp, -10, -10, 10, 10)  # something black so the file isn't all-engrave
    p = parse_dxf(dxf.save(doc))
    if cut:
        assert p.net_area_raw == pytest.approx(4.0) and p.engrave == []
    else:
        assert p.net_area_raw == pytest.approx(400.0) and len(p.engrave) == 4


def test_no_black_geometry_is_an_error(dxf):
    doc, msp = dxf.new()
    rect(msp, 0, 0, 4, 2, color=3)
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.ERROR and p.net_area_raw is None
    assert "No cut (black) lines found. Check the colors in this file." in texts(p, Level.ERROR)


def test_custom_cut_colors(dxf):
    doc, msp = dxf.new()
    rect(msp, 0, 0, 4, 2, color=1)  # red outline
    msp.add_circle((2, 1), 0.5)  # black circle
    path = dxf.save(doc)
    default = parse_dxf(path)  # default: only black cuts -> the red outline is engrave, the circle is the piece
    assert default.net_area_raw == pytest.approx(math.pi * 0.25, rel=CIRCLE_RTOL) and len(default.engrave) == 4
    red_and_black = parse_dxf(path, cut_colors=cut_colors_from_settings(["ACI 1", "ACI 7"]))
    assert red_and_black.net_area_raw == pytest.approx(8 - math.pi * 0.25, rel=CIRCLE_RTOL)


def test_engrave_spline_that_cant_be_drawn_is_not_an_error(dxf):
    doc, msp = dxf.new()
    rect(msp, 0, 0, 10, 10)
    msp.add_3dface([(1, 1), (2, 1), (2, 2), (1, 2)], dxfattribs={"color": 3})  # engrave-colored oddity
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.INFO and p.net_area_raw == pytest.approx(100.0)


@pytest.mark.parametrize("spec, key", [("ACI 7", ("aci", 7)), ("7", ("aci", 7)), ("aci  250", ("aci", 250)),
                                       ("RGB 0,0,0", ("rgb", (0, 0, 0))), ("12, 34, 56", ("rgb", (12, 34, 56)))])
def test_parse_color_spec(spec, key):
    assert parse_color_spec(spec) == key


@pytest.mark.parametrize("bad", ["", "black", "0", "256", "1,2", "300,0,0", "RGB a,b,c"])
def test_parse_color_spec_rejects(bad):
    with pytest.raises(ValueError):
        parse_color_spec(bad)


def test_cut_colors_from_settings_falls_back_to_black():
    assert cut_colors_from_settings([]) == DEFAULT_CUT_COLORS
    assert cut_colors_from_settings(["nonsense"]) == DEFAULT_CUT_COLORS
    assert cut_colors_from_settings(["ACI 7", "RGB 0,0,0"]) == DEFAULT_CUT_COLORS


def test_picture_includes_engrave(dxf):
    doc, msp = dxf.new()
    rect(msp, 0, 0, 10, 10)
    msp.add_circle((5, 5), 2, dxfattribs={"color": 3})
    pic = picture_from_parsed(parse_dxf(dxf.save(doc)))
    assert len(pic["engrave"]) == 1 and pic["bbox"] == [10.0, 10.0]  # bbox is cut geometry only


# ---------------------------------------------------------------- LightBurn-style export (synthetic)

def _lightburn_like(tmp_path, name="lb.dxf", duplicate_handles=True):
    """R12, Layer_N layers, closed POLYLINEs with bulges, no $INSUNITS, mm coordinates."""
    doc = ezdxf.new("R12")
    doc.layers.add("Layer_0", color=7)
    doc.layers.add("Layer_3", color=3)
    msp = doc.modelspace()
    # 100 x 80 mm panel with rounded (bulged) right side, and a 20 x 10 mm window
    msp.add_polyline2d([(0, 0), (100, 0), (100, 80), (0, 80)], close=True,
                       dxfattribs={"layer": "Layer_0", "color": 7})
    msp.add_polyline2d([(40, 30), (60, 30), (60, 40), (40, 40)], close=True,
                       dxfattribs={"layer": "Layer_0", "color": 7})
    msp.add_polyline2d([(10, 10), (30, 10), (30, 20)], dxfattribs={"layer": "Layer_3", "color": 3})  # engrave
    circle = msp.add_polyline2d([(70, 50, 0, 0, 1), (80, 50, 0, 0, 1)], format="xyseb", close=True,
                                dxfattribs={"layer": "Layer_3", "color": 3})  # bulged engrave circle
    assert circle
    doc.header.pop("$INSUNITS", None) if hasattr(doc.header, "pop") else None
    path = tmp_path / name
    doc.saveas(path)
    text = path.read_text(encoding="cp1252")
    text = _drop_insunits(text)
    if duplicate_handles:
        text = _reuse_polyline_handles(text)
    path.write_text(text, encoding="cp1252")
    return path


def _drop_insunits(text: str) -> str:
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        if lines[i].strip() == "9" and i + 1 < len(lines) and lines[i + 1].strip() == "$INSUNITS":
            i += 4  # 9 / $INSUNITS / 70 / value
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out) + "\n"


def _reuse_polyline_handles(text: str) -> str:
    """Give each VERTEX/SEQEND its POLYLINE's handle, like LightBurn does."""
    lines = text.splitlines()
    pairs = [(lines[i], lines[i + 1]) for i in range(0, len(lines) - 1, 2)]
    out, current, parent = [], None, None
    for code, value in pairs:
        if code.strip() == "0":
            current = value.strip()
        if code.strip() == "5":
            if current == "POLYLINE":
                parent = value
            elif current in ("VERTEX", "SEQEND") and parent is not None:
                value = parent
        out += [code, value]
    return "\n".join(out) + "\n"


def test_lightburn_like_export(tmp_path):
    path = _lightburn_like(tmp_path)
    assert "$INSUNITS" not in path.read_text(encoding="cp1252")
    p = parse_dxf(str(path))
    assert p.header_unit == "mm" and p.units_assumed
    assert "Units not stated in file, assumed millimeters" in p.header_unit_note
    assert p.bbox_raw == pytest.approx((100.0, 80.0))
    assert p.net_area_raw == pytest.approx(100 * 80 - 20 * 10)
    assert len(p.engrave) == 2
    assert p.status == Level.INFO


def test_readfile_is_used_before_recover(tmp_path):
    """ezdxf.recover loses LightBurn geometry with reused handles; the parser must not."""
    from ezdxf import recover
    path = _lightburn_like(tmp_path)
    recovered, _aud = recover.readfile(path)
    parsed = parse_dxf(str(path))
    assert parsed.net_area_raw == pytest.approx(7800.0)
    # Documents the ezdxf behavior this guards against (if ezdxf ever fixes it, this still passes).
    assert len(recovered.modelspace()) <= len(ezdxf.readfile(path).modelspace())


# ---------------------------------------------------------------- units

def test_unitless_small_non_lightburn_stays_unknown(dxf):
    doc, msp = dxf.new(insunits=0)
    rect(msp, 0, 0, 12, 8)
    p = parse_dxf(dxf.save(doc))
    assert p.header_unit == "unknown" and not p.units_assumed


def test_unitless_too_big_for_inches_assumes_mm(dxf):
    doc, msp = dxf.new(insunits=0)
    rect(msp, 0, 0, 368.3, 361.95)
    p = parse_dxf(dxf.save(doc))
    assert p.header_unit == "mm" and p.units_assumed and "over 5 feet in inches" in p.header_unit_note


def test_stated_units_are_never_second_guessed(dxf):
    doc, msp = dxf.new(insunits=1)  # says inches, even though it's large
    rect(msp, 0, 0, 368.3, 361.95)
    p = parse_dxf(dxf.save(doc))
    assert p.header_unit == "in" and not p.units_assumed


def test_row_shows_assumed_units_and_allows_override(tmp_path):
    row = PieceRow.load(str(_lightburn_like(tmp_path)))
    assert row.unit == "mm"
    assert any(m.level == Level.INFO and "assumed millimeters" in m.text for m in row.messages)
    assert row.area_cm2 == pytest.approx(78.0)  # 7800 mm²
    row.unit = "in"
    assert any("the file itself doesn't say; TallyCraft assumed millimeters" in m.text for m in row.messages)


# ---------------------------------------------------------------- the real LightBurn file (not committed)

@pytest.mark.skipif(not LB_FILE.exists(), reason="private LightBurn sample not present (tests/fixtures_private/)")
def test_real_lightburn_front_panel():
    p = parse_dxf(str(LB_FILE))
    assert p.header_unit == "mm" and p.units_assumed
    assert p.bbox_raw == pytest.approx((368.30, 361.95), abs=0.01)
    assert p.net_area_raw == pytest.approx(79_273, rel=1e-4)
    assert p.net_area_raw / 645.16 == pytest.approx(122.87, abs=0.01)
    areas = sorted(polygon_area(l) for l in p.loops)
    assert len(areas) == 23
    assert sum(areas[:-1]) / 645.16 == pytest.approx(20.67, abs=0.01)
    assert len(p.engrave) == 151
    assert "151 engrave-only items drawn but not counted in weight." in texts(p, Level.INFO)
    assert p.status == Level.INFO
