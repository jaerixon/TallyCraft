import math

import pytest

from tallycraft.dxf_geometry import parse_dxf, polygon_area, stitch
from tallycraft.messages import Level

# Tessellation at 2 degrees under-reports circle area by ~0.02%.
CIRCLE_RTOL = 5e-4
# Flattened splines/ellipses must match analytic areas to 0.01%.
SPLINE_RTOL = 1e-4


def texts(piece, level=None):
    return [m.text for m in piece.messages if level is None or m.level == level]


# ---------------------------------------------------------------- basics

def test_rectangle_from_loose_lines(dxf):
    doc, msp = dxf.new(insunits=1)
    dxf.rect_lines(msp, 0, 0, 4, 2)
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK, p.messages
    assert p.header_unit == "in"
    assert p.net_area_raw == pytest.approx(8.0)
    assert p.bbox_raw == pytest.approx((4.0, 2.0))


def test_lines_drawn_in_random_directions_and_order(dxf):
    doc, msp = dxf.new()
    msp.add_line((4, 2), (4, 0))
    msp.add_line((0, 0), (0, 2))
    msp.add_line((4, 0), (0, 0))
    msp.add_line((4, 2), (0, 2))
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK
    assert p.net_area_raw == pytest.approx(8.0)


def test_endpoints_within_tolerance_are_joined(dxf):
    doc, msp = dxf.new()
    msp.add_line((0, 0), (4, 0))
    msp.add_line((4.00005, 0), (4, 2))
    msp.add_line((4, 2), (0, 2.00003))
    msp.add_line((0, 2), (0, 0))
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK, p.messages
    assert p.net_area_raw == pytest.approx(8.0, rel=1e-4)


def test_millimeter_header(dxf):
    doc, msp = dxf.new(insunits=4)
    dxf.rect_lines(msp, 0, 0, 100, 50)
    p = parse_dxf(dxf.save(doc))
    assert p.header_unit == "mm"
    assert p.net_area_raw == pytest.approx(5000.0)


# ---------------------------------------------------------------- arcs / holes

def test_rounded_rectangle_with_arcs(dxf):
    # 10x6 slot-ish shape: straight edges plus four quarter-arc corners of r=1
    doc, msp = dxf.new()
    r = 1
    msp.add_line((1, 0), (9, 0))
    msp.add_line((10, 1), (10, 5))
    msp.add_line((9, 6), (1, 6))
    msp.add_line((0, 5), (0, 1))
    msp.add_arc((9, 1), r, 270, 0)
    msp.add_arc((9, 5), r, 0, 90)
    msp.add_arc((1, 5), r, 90, 180)
    msp.add_arc((1, 1), r, 180, 270)
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK, p.messages
    expected = 10 * 6 - (4 - math.pi) * r * r
    assert p.net_area_raw == pytest.approx(expected, rel=CIRCLE_RTOL)


def test_holes_are_subtracted_not_added(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 10, 10)
    dxf.rect_lines(msp, 1, 1, 3, 3)  # 4
    msp.add_circle((7, 7), 1)  # pi
    p = parse_dxf(dxf.save(doc))
    assert p.status <= Level.INFO, p.messages
    assert p.net_area_raw == pytest.approx(100 - 4 - math.pi, rel=CIRCLE_RTOL)


def test_many_vent_holes(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 100, 100)
    n = 0
    for i in range(10):
        for j in range(10):
            msp.add_circle((5 + i * 10, 5 + j * 10), 2)
            n += 1
    p = parse_dxf(dxf.save(doc))
    assert p.status <= Level.INFO, p.messages
    assert p.net_area_raw == pytest.approx(10000 - n * math.pi * 4, rel=CIRCLE_RTOL)


def test_hole_touching_outline_still_counts_as_hole(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 10, 10)
    msp.add_circle((5, 9), 1)  # tangent to the top edge at (5, 10)
    p = parse_dxf(dxf.save(doc))
    assert p.status <= Level.INFO, p.messages
    assert p.net_area_raw == pytest.approx(100 - math.pi, rel=CIRCLE_RTOL)


def test_mirrored_arc_extrusion(dxf):
    # Arc with extrusion (0,0,-1) — common in mirrored CAD exports.
    doc, msp = dxf.new()
    # Half-disc of radius 2 centered at origin, flat side on the x axis (y >= 0).
    # In OCS with -Z extrusion, x is mirrored: WCS (2,0) is OCS (-2,0) -> angle 180.
    msp.add_arc((0, 0), 2, 0, 180, dxfattribs={"extrusion": (0, 0, -1)})
    msp.add_line((-2, 0), (2, 0))
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK, p.messages
    assert p.net_area_raw == pytest.approx(math.pi * 2, rel=CIRCLE_RTOL)


# ---------------------------------------------------------------- polylines & blocks

def test_closed_lwpolyline_with_bulge(dxf):
    doc, msp = dxf.new()
    # 4x2 rectangle whose right side is a semicircular bulge (bulge=1 -> 180 deg)
    msp.add_lwpolyline([(0, 0, 0), (4, 0, 1), (4, 2, 0), (0, 2, 0)], format="xyb", close=True)
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK, p.messages
    assert p.net_area_raw == pytest.approx(8 + math.pi / 2, rel=CIRCLE_RTOL)


def test_open_polylines_stitched_with_lines(dxf):
    doc, msp = dxf.new()
    msp.add_lwpolyline([(0, 0), (4, 0), (4, 2)])
    msp.add_line((4, 2), (0, 2))
    msp.add_line((0, 2), (0, 0))
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK, p.messages
    assert p.net_area_raw == pytest.approx(8.0)


def test_old_style_2d_polyline(dxf):
    doc, msp = dxf.new()
    msp.add_polyline2d([(0, 0), (3, 0), (3, 3), (0, 3)], close=True)
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK, p.messages
    assert p.net_area_raw == pytest.approx(9.0)


def test_block_insert_is_expanded(dxf):
    doc, msp = dxf.new()
    blk = doc.blocks.new("PART")
    dxf.rect_lines(blk, 0, 0, 2, 2)
    msp.add_blockref("PART", (10, 10), dxfattribs={"xscale": 2, "yscale": 2})
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK, p.messages
    assert p.net_area_raw == pytest.approx(16.0)


# ---------------------------------------------------------------- errors & warnings

def test_gap_is_an_error_with_location(dxf):
    doc, msp = dxf.new()
    msp.add_line((0, 0), (4, 0))
    msp.add_line((4, 0), (4, 2))
    msp.add_line((4, 2), (0, 2))
    msp.add_line((0, 2), (0, 0.01))  # 0.01 short of closing
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.ERROR
    assert p.net_area_raw is None
    msg = " ".join(texts(p, Level.ERROR))
    assert "gap" in msg and "(0, 0.01)" in msg


def test_branching_junction_is_an_error(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 4, 2)
    msp.add_line((0, 0), (2, 1))
    msp.add_line((2, 1), (4, 2))  # diagonal splitting the rectangle
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.ERROR
    assert any("three or more" in t for t in texts(p))


def test_duplicate_lines_are_dropped_with_info(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 4, 2)
    msp.add_line((4, 0), (0, 0))  # duplicate of bottom edge, reversed
    msp.add_circle((2, 1), 0.5)
    msp.add_circle((2, 1), 0.5)
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.INFO, p.messages
    assert p.net_area_raw == pytest.approx(8 - math.pi * 0.25, rel=CIRCLE_RTOL)
    assert any("duplicate" in t for t in texts(p, Level.INFO))


@pytest.mark.parametrize("adder, name", [
    (lambda m: m.add_3dface([(0, 0), (1, 0), (1, 1), (0, 1)]), "3DFACE"),
    (lambda m: m.add_solid([(0, 0), (1, 0), (1, 1)]), "SOLID"),
])
def test_unsupported_geometry_is_named(dxf, adder, name):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 10, 10)
    adder(msp)
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.ERROR
    assert p.net_area_raw is None
    assert any(name in t for t in texts(p, Level.ERROR))


# ---------------------------------------------------------------- splines & ellipses

# A NURBS circle: degree 2, 9 control points, exact (not approximate) circle.
_W = math.sqrt(2) / 2
_CIRCLE_WEIGHTS = [1, _W, 1, _W, 1, _W, 1, _W, 1]
_CIRCLE_KNOTS = [0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 4]


def _nurbs_circle(msp, cx, cy, r):
    unit = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0)]
    pts = [(cx + r * x, cy + r * y) for x, y in unit]
    return msp.add_rational_spline(pts, _CIRCLE_WEIGHTS, degree=2, knots=_CIRCLE_KNOTS)


def test_open_spline_joins_lines(dxf):
    # 4x2 rectangle whose top edge is a quadratic spline (a parabola) bulging up.
    # The parabola's apex is 1 above the chord (half the control point's offset of 2),
    # so it adds exactly 2/3 * chord * height = 2/3 * 4 * 1.
    doc, msp = dxf.new()
    msp.add_line((0, 0), (4, 0))
    msp.add_line((4, 0), (4, 2))
    msp.add_open_spline([(4, 2), (2, 4), (0, 2)], degree=2)
    msp.add_line((0, 2), (0, 0))
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK, p.messages
    assert p.net_area_raw == pytest.approx(8 + 8 / 3, rel=SPLINE_RTOL)


def test_two_splines_joining_each_other(dxf):
    # Same shape, but the top edge is split into two cubic splines that meet
    # each other (not a line) in the middle, as in the user's real panels.
    doc, msp = dxf.new()
    msp.add_line((0, 0), (4, 0))
    msp.add_line((4, 0), (4, 2))
    msp.add_open_spline([(4, 2), (3.5, 3), (2.5, 3), (2, 3)], degree=3)
    msp.add_open_spline([(2, 3), (1.5, 3), (0.5, 3), (0, 2)], degree=3)
    msp.add_line((0, 2), (0, 0))
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK, p.messages
    # Independent value: integrate the exact cubic Beziers with Green's theorem.
    def bez_area_term(p0, p1, p2, p3, n=20000):
        s = 0.0
        prev = p0
        for i in range(1, n + 1):
            t = i / n
            mt = 1 - t
            x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
            y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
            s += prev[0] * y - x * prev[1]
            prev = (x, y)
        return s
    edges = [((0, 0), (4, 0)), ((4, 0), (4, 2)), ((0, 2), (0, 0))]
    total = sum(a[0] * b[1] - b[0] * a[1] for a, b in edges)
    total += bez_area_term((4, 2), (3.5, 3), (2.5, 3), (2, 3))
    total += bez_area_term((2, 3), (1.5, 3), (0.5, 3), (0, 2))
    assert p.net_area_raw == pytest.approx(abs(total) / 2, rel=SPLINE_RTOL)


def test_closed_spline_as_hole(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 10, 10)
    _nurbs_circle(msp, 5, 5, 2)
    p = parse_dxf(dxf.save(doc))
    assert p.status <= Level.INFO, p.messages
    assert p.net_area_raw == pytest.approx(100 - math.pi * 4, rel=SPLINE_RTOL)


def test_closed_spline_as_outline(dxf):
    doc, msp = dxf.new()
    _nurbs_circle(msp, 0, 0, 3)
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK, p.messages
    assert p.net_area_raw == pytest.approx(math.pi * 9, rel=SPLINE_RTOL)


def test_full_ellipse_as_hole(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 10, 10)
    msp.add_ellipse((5, 5), major_axis=(3, 0), ratio=0.5)  # a=3, b=1.5
    p = parse_dxf(dxf.save(doc))
    assert p.status <= Level.INFO, p.messages
    assert p.net_area_raw == pytest.approx(100 - math.pi * 3 * 1.5, rel=SPLINE_RTOL)


def test_half_ellipse_joined_to_line(dxf):
    doc, msp = dxf.new()
    msp.add_ellipse((0, 0), major_axis=(4, 0), ratio=0.5, start_param=0, end_param=math.pi)
    msp.add_line((-4, 0), (4, 0))
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.OK, p.messages
    assert p.net_area_raw == pytest.approx(math.pi * 4 * 2 / 2, rel=SPLINE_RTOL)


def test_spline_gap_still_reported(dxf):
    doc, msp = dxf.new()
    msp.add_line((0, 0), (4, 0))
    msp.add_line((4, 0), (4, 2))
    msp.add_open_spline([(4, 2), (2, 4), (0.01, 2)], degree=2)  # stops 0.01 short
    msp.add_line((0, 2), (0, 0))
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.ERROR
    assert any("gap" in t for t in texts(p, Level.ERROR))


# ---------------------------------------------------------------- preview data

def test_preview_data_for_good_piece(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 10, 10)
    msp.add_circle((5, 5), 1)
    p = parse_dxf(dxf.save(doc))
    assert len(p.loops) == 2
    assert sorted(p.loop_depths) == [0, 1]
    assert p.open_chains == [] and p.error_points == []


def test_preview_data_for_gap(dxf):
    doc, msp = dxf.new()
    msp.add_line((0, 0), (4, 0))
    msp.add_line((4, 0), (4, 2))
    msp.add_line((4, 2), (0, 2))
    msp.add_line((0, 2), (0, 0.5))
    p = parse_dxf(dxf.save(doc))
    assert len(p.open_chains) == 1 and len(p.open_chains[0]) == 5  # traced end to end
    assert sorted(p.error_points) == [(0, 0), (0, 0.5)]


def test_text_and_dimensions_are_ignored_with_info(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 4, 2)
    msp.add_text("SIDE PANEL")
    msp.add_mtext("note")
    dim = msp.add_linear_dim(base=(0, -1), p1=(0, 0), p2=(4, 0))
    dim.render()
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.INFO
    assert p.net_area_raw == pytest.approx(8.0)
    info = " ".join(texts(p, Level.INFO))
    assert "TEXT" in info and "DIMENSION" in info


def test_two_separate_shapes_is_a_warning(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 4, 2)
    dxf.rect_lines(msp, 10, 0, 12, 2)
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.WARNING
    assert p.net_area_raw == pytest.approx(12.0)
    assert any("separate shapes" in t for t in texts(p, Level.WARNING))


def test_island_inside_hole_is_a_warning(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 10, 10)
    dxf.rect_lines(msp, 2, 2, 8, 8)   # hole 36
    dxf.rect_lines(msp, 4, 4, 6, 6)   # island 4 inside the hole
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.WARNING
    assert p.net_area_raw == pytest.approx(100 - 36 + 4)


def test_ignored_and_hidden_layers(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 4, 2, layer="CUT")
    dxf.rect_lines(msp, -5, -5, 20, 20, layer="Construction")
    doc.layers.add("OFFLAYER")
    doc.layers.get("OFFLAYER").off()
    msp.add_line((100, 100), (200, 200), dxfattribs={"layer": "OFFLAYER"})
    p = parse_dxf(dxf.save(doc), ignored_layers=["CONSTRUCTION"])
    assert p.status == Level.INFO, p.messages
    assert p.net_area_raw == pytest.approx(8.0)
    info = " ".join(texts(p, Level.INFO))
    assert "Construction" in info and "OFFLAYER" in info


def test_unknown_units_still_computes_area(dxf):
    doc, msp = dxf.new(insunits=0)
    dxf.rect_lines(msp, 0, 0, 4, 2)
    p = parse_dxf(dxf.save(doc))
    assert p.header_unit == "unknown"
    assert "doesn't say" in p.header_unit_note
    assert p.net_area_raw == pytest.approx(8.0)  # the user can fix units in the table


def test_centimeter_header_reports_what_it_said(dxf):
    doc, msp = dxf.new(insunits=5)
    dxf.rect_lines(msp, 0, 0, 4, 2)
    p = parse_dxf(dxf.save(doc))
    assert p.header_unit == "unknown"
    assert "centimeters" in p.header_unit_note


def test_no_geometry(dxf):
    doc, msp = dxf.new()
    msp.add_text("hello")
    p = parse_dxf(dxf.save(doc))
    assert p.status == Level.ERROR
    assert any("No cut lines" in t for t in texts(p))


# ---------------------------------------------------------------- file-level errors

def test_missing_file(tmp_path):
    p = parse_dxf(str(tmp_path / "nope.dxf"))
    assert p.status == Level.ERROR and "not found" in texts(p)[0]


def test_empty_file(tmp_path):
    f = tmp_path / "empty.dxf"
    f.write_bytes(b"")
    p = parse_dxf(str(f))
    assert p.status == Level.ERROR and "empty" in texts(p)[0]


def test_garbage_file(tmp_path):
    f = tmp_path / "junk.dxf"
    f.write_bytes(b"\x00\x01this is not a dxf at all\xff" * 50)
    p = parse_dxf(str(f))
    assert p.status == Level.ERROR
    assert p.net_area_raw is None


def test_truncated_file(dxf):
    doc, msp = dxf.new()
    dxf.rect_lines(msp, 0, 0, 4, 2)
    path = dxf.save(doc)
    data = open(path, "rb").read()
    open(path, "wb").write(data[: len(data) // 3])
    p = parse_dxf(path)  # must not raise
    assert p.status >= Level.WARNING


# ---------------------------------------------------------------- pure helpers

def test_polygon_area_orientation_independent():
    sq = [(0, 0), (2, 0), (2, 2), (0, 2)]
    assert polygon_area(sq) == 4
    assert polygon_area(list(reversed(sq))) == 4


def test_stitch_returns_error_for_single_dangling_end():
    r = stitch([[(0, 0), (1, 0)], [(1, 0), (1, 1)]])
    assert r.loops == [] and r.errors
    assert r.open_chains == [[(0, 0), (1, 0), (1, 1)]] or r.open_chains == [[(1, 1), (1, 0), (0, 0)]]
    assert sorted(r.error_points) == [(0, 0), (1, 1)]
