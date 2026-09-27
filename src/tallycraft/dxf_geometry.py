"""DXF parsing and net-area geometry.

Pipeline (see docs/SPEC.md §5):
  1. Collect LINE / ARC / CIRCLE / SPLINE / ELLIPSE (and exploded LWPOLYLINE /
     POLYLINE / INSERT) from modelspace as point chains in raw file coordinates.
  2. Tessellate arcs/circles at <= 2 degrees per segment; flatten splines and
     ellipses to an equivalent (or finer) deviation.
  3. Closed entities are their own loop; open chains are stitched end-to-end
     by matching endpoints within STITCH_TOLERANCE.
  4. Shoelace area per loop; largest loop is the outer boundary; net area =
     outer - sum(other loops).

Nothing here scales coordinates: areas and bounding boxes are in raw file
units, so a user's Units correction is a pure reinterpretation.
"""

from __future__ import annotations

import math
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .messages import Level, Message, worst

STITCH_TOLERANCE = 1e-4  # file units
ARC_STEP_DEG = 2.0
# Max deviation of a flattened spline/ellipse from the true curve, relative to
# the curve's size (control-point extent). Flattened curves come out at least
# ~5x more accurate than 2-degree arcs; measured area error is < 0.01%.
CURVE_TOLERANCE_REL = 1e-5
MAX_BLOCK_DEPTH = 16
MAX_LOCATION_MESSAGES = 5

Point = tuple[float, float]

# $INSUNITS header codes. Only inches and millimeters are selectable units;
# everything else is shown as Unknown with the header's own name in the note.
INSUNITS_NAMES = {
    0: "unitless", 1: "inches", 2: "feet", 3: "miles", 4: "millimeters",
    5: "centimeters", 6: "meters", 7: "kilometers", 8: "microinches",
    9: "mils", 10: "yards", 11: "angstroms", 12: "nanometers", 13: "microns",
    14: "decimeters", 15: "decameters", 16: "hectometers", 17: "gigameters",
    18: "astronomical units", 19: "light years", 20: "parsecs",
    21: "US survey feet", 22: "US survey inches", 23: "US survey yards",
    24: "US survey miles",
}
INSUNITS_TO_UNIT = {1: "in", 4: "mm"}

# Entity types that carry no cut geometry: skipped with an Info note.
NON_GEOMETRY_TYPES = {
    "TEXT", "MTEXT", "DIMENSION", "ARC_DIMENSION", "LARGE_RADIAL_DIMENSION",
    "LEADER", "MLEADER", "MULTILEADER", "HATCH", "POINT", "ATTDEF", "ATTRIB",
    "VIEWPORT", "IMAGE", "WIPEOUT", "TOLERANCE", "XLINE", "RAY", "OLE2FRAME",
    "OLEFRAME", "PDFUNDERLAY", "DWFUNDERLAY", "DGNUNDERLAY", "ACAD_TABLE",
    "SHAPE", "ACAD_PROXY_ENTITY",
}

FRIENDLY_TYPE_NAMES = {
    "HELIX": "helix",
    "SOLID": "filled solid",
    "TRACE": "trace",
    "3DFACE": "3D face",
    "3DSOLID": "3D solid",
    "REGION": "region",
    "BODY": "3D body",
    "MESH": "mesh",
    "SURFACE": "surface",
    "MPOLYGON": "multi-polygon",
    "POLYLINE": "3D polyline/mesh",
}


@dataclass
class ParsedPiece:
    """Result of reading one DXF file. All geometry is in raw file units."""

    path: str
    header_unit: str = "unknown"  # "in" | "mm" | "unknown"
    header_unit_note: str = ""  # why header_unit is unknown (shown by the row model)
    loops: list[list[Point]] = field(default_factory=list)
    bbox_raw: tuple[float, float] | None = None  # (width, height)
    net_area_raw: float | None = None  # None when geometry is in error
    messages: list[Message] = field(default_factory=list)
    # For the preview: the exact geometry the area was computed from.
    loop_depths: list[int] = field(default_factory=list)  # per loop; even = solid, odd = hole
    open_chains: list[list[Point]] = field(default_factory=list)  # runs that never closed
    error_points: list[Point] = field(default_factory=list)  # loose ends / bad junctions

    @property
    def status(self) -> Level:
        return worst(self.messages)

    def add(self, level: Level, text: str) -> None:
        self.messages.append(Message(level, text))


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def parse_dxf(path: str, ignored_layers: list[str] | tuple[str, ...] = ()) -> ParsedPiece:
    """Read a DXF and compute its net area. Never raises for bad input files;
    problems are reported as messages on the returned piece."""
    piece = ParsedPiece(path=path)
    try:
        doc = _read_document(path, piece)
        if doc is None:
            return piece
        _read_units(doc, piece)
        chains, closed = _collect_geometry(doc, piece, {n.strip().upper() for n in ignored_layers})
        if piece.status >= Level.ERROR and not (chains or closed):
            return piece
        _build_area(chains, closed, piece)
    except Exception as exc:  # last-resort guard: one bad file must not crash the batch
        piece.net_area_raw = None
        piece.add(Level.ERROR, f"TallyCraft couldn't read this file because of an unexpected problem: {exc}")
    return piece


# --------------------------------------------------------------------------
# File reading
# --------------------------------------------------------------------------

def _read_document(path: str, piece: ParsedPiece):
    import ezdxf
    from ezdxf import recover

    if not os.path.exists(path):
        piece.add(Level.ERROR, "File not found. It may have been moved, renamed, or deleted.")
        return None
    if os.path.isdir(path):
        piece.add(Level.ERROR, "This is a folder, not a DXF file.")
        return None
    try:
        if os.path.getsize(path) == 0:
            piece.add(Level.ERROR, "The file is empty (0 bytes).")
            return None
    except OSError as exc:
        piece.add(Level.ERROR, f"Windows wouldn't let TallyCraft read this file ({exc.strerror or exc}).")
        return None

    try:
        doc, auditor = recover.readfile(path)
    except PermissionError:
        piece.add(Level.ERROR, "Windows wouldn't let TallyCraft open this file. Is it open in another program?")
        return None
    except OSError as exc:
        piece.add(Level.ERROR, f"The file couldn't be opened ({exc.strerror or exc}).")
        return None
    except ezdxf.DXFStructureError:
        piece.add(Level.ERROR, "This doesn't look like a valid DXF file, or the file is damaged.")
        return None
    except Exception as exc:
        piece.add(Level.ERROR, f"This file couldn't be read as a DXF ({exc}).")
        return None

    if auditor.has_errors:
        piece.add(Level.WARNING,
                  f"The file had {len(auditor.errors)} internal problem(s) that were repaired "
                  "automatically while reading it. Please check the area looks right.")
    return doc


def _read_units(doc, piece: ParsedPiece) -> None:
    try:
        code = int(doc.header.get("$INSUNITS", 0))
    except (TypeError, ValueError):
        code = 0
    unit = INSUNITS_TO_UNIT.get(code)
    if unit:
        piece.header_unit = unit
        return
    piece.header_unit = "unknown"
    said = INSUNITS_NAMES.get(code, f"an unrecognized code ({code})")
    if code == 0:
        piece.header_unit_note = "The file doesn't say what units it uses."
    else:
        piece.header_unit_note = f"The file says its units are {said}, which TallyCraft doesn't support directly."


# --------------------------------------------------------------------------
# Geometry collection
# --------------------------------------------------------------------------

@dataclass
class _Collect:
    chains: list[list[Point]] = field(default_factory=list)  # open chains to stitch
    closed: list[list[Point]] = field(default_factory=list)  # already-closed loops
    ignored_types: Counter = field(default_factory=Counter)
    unsupported: Counter = field(default_factory=Counter)
    skipped_layers: Counter = field(default_factory=Counter)
    problems: list[str] = field(default_factory=list)


def _collect_geometry(doc, piece: ParsedPiece, ignored_layers: set[str]):
    hidden_layers = set()
    for layer in doc.layers:
        try:
            if layer.is_off() or layer.is_frozen():
                hidden_layers.add(layer.dxf.name.upper())
        except Exception:
            pass

    acc = _Collect()
    for entity in doc.modelspace():
        _visit(entity, acc, ignored_layers, hidden_layers, depth=0)

    for (layer_name, why), n in sorted(acc.skipped_layers.items()):
        piece.add(Level.INFO, f"Skipped {n} item(s) on layer \"{layer_name}\" ({why}).")
    if acc.ignored_types:
        parts = ", ".join(f"{n} {t}" for t, n in sorted(acc.ignored_types.items()))
        piece.add(Level.INFO, f"Ignored non-cutting items (not part of the shape): {parts}.")
    for t, n in sorted(acc.unsupported.items()):
        name = FRIENDLY_TYPE_NAMES.get(t, t.lower())
        piece.add(Level.ERROR,
                  f"Contains {n} {name} item(s) ({t}), which TallyCraft can't measure. "
                  "Re-export the design with curves converted to lines and arcs (or polylines).")
    for text in acc.problems:
        piece.add(Level.ERROR, text)
    if acc.unsupported or acc.problems:
        piece.net_area_raw = None
    return acc.chains, acc.closed


def _visit(entity, acc: _Collect, ignored_layers, hidden_layers, depth: int) -> None:
    t = entity.dxftype()
    layer = str(entity.dxf.get("layer", "0"))
    layer_key = layer.upper()
    if layer_key in ignored_layers:
        acc.skipped_layers[(layer, "listed as an ignored layer in settings")] += 1
        return
    if layer_key in hidden_layers:
        acc.skipped_layers[(layer, "layer is turned off or frozen")] += 1
        return

    if t == "LINE":
        s, e = entity.dxf.start, entity.dxf.end
        acc.chains.append([(s.x, s.y), (e.x, e.y)])
    elif t == "ARC":
        pts = _arc_points(entity)
        if pts is None:  # start == end angle: a full circle drawn as an arc
            acc.closed.append(_circle_points(entity))
        else:
            acc.chains.append(pts)
    elif t == "CIRCLE":
        if entity.dxf.radius <= 0:
            return
        acc.closed.append(_circle_points(entity))
    elif t in ("SPLINE", "ELLIPSE"):
        try:
            pts = _curve_points(entity)
        except Exception as exc:
            acc.problems.append(f"A {t.lower()} curve couldn't be converted into line segments ({exc}).")
            return
        if len(pts) < 2:
            return
        if len(pts) >= 4 and _close(pts[0], pts[-1]):
            acc.closed.append(pts[:-1])  # closed spline / full ellipse is its own loop
        else:
            acc.chains.append(pts)
    elif t == "LWPOLYLINE" or (t == "POLYLINE" and _is_flat_polyline(entity)):
        _visit_polyline(entity, acc)
    elif t == "INSERT":
        if depth >= MAX_BLOCK_DEPTH:
            acc.problems.append("Block references are nested too deeply to read safely.")
            return
        try:
            children = list(entity.virtual_entities())
        except Exception as exc:
            acc.problems.append(f"A block reference (INSERT \"{entity.dxf.get('name', '?')}\") "
                                f"couldn't be expanded ({exc}).")
            return
        for child in children:
            _visit(child, acc, ignored_layers, hidden_layers, depth + 1)
    elif t in NON_GEOMETRY_TYPES:
        acc.ignored_types[t] += 1
    else:
        acc.unsupported[t] += 1


def _is_flat_polyline(entity) -> bool:
    if entity.is_2d_polyline:
        return True
    if entity.is_3d_polyline:
        zs = {round(v.dxf.location.z, 9) for v in entity.vertices}
        return len(zs) <= 1
    return False  # polyface / polygon mesh


def _visit_polyline(entity, acc: _Collect) -> None:
    pts: list[Point] = []
    for sub in entity.virtual_entities():
        st = sub.dxftype()
        if st == "LINE":
            seg = [(sub.dxf.start.x, sub.dxf.start.y), (sub.dxf.end.x, sub.dxf.end.y)]
        elif st == "ARC":
            seg = _arc_points(sub) or _circle_points(sub)
        else:
            acc.unsupported[st] += 1
            continue
        if pts and _close(pts[-1], seg[0]):
            pts.extend(seg[1:])
        elif pts and _close(pts[-1], seg[-1]):
            pts.extend(reversed(seg[:-1]))
        else:
            if pts:
                acc.chains.append(pts)
            pts = list(seg)
    if len(pts) < 2:
        return
    if entity.is_closed and _close(pts[0], pts[-1]) and len(pts) >= 4:
        acc.closed.append(pts[:-1])
    else:
        acc.chains.append(pts)


def _arc_points(arc) -> list[Point] | None:
    start = arc.dxf.start_angle % 360.0
    sweep = (arc.dxf.end_angle - arc.dxf.start_angle) % 360.0
    if sweep < 1e-9 or arc.dxf.radius <= 0:
        return None if arc.dxf.radius > 0 else [(arc.dxf.center.x, arc.dxf.center.y)] * 2
    n = max(1, math.ceil(sweep / ARC_STEP_DEG))
    angles = [start + sweep * i / n for i in range(n + 1)]
    return [(v.x, v.y) for v in arc.vertices(angles)]  # vertices() returns WCS (handles mirrored OCS)


def _curve_points(entity) -> list[Point]:
    """Flatten a SPLINE or ELLIPSE into WCS points. ezdxf evaluates the exact
    start and end of the curve, so its endpoints meet neighbors like any line."""
    if entity.dxftype() == "ELLIPSE":
        size = 2.0 * entity.dxf.major_axis.magnitude
        distance = max(size * CURVE_TOLERANCE_REL, 1e-12)
        return [(v.x, v.y) for v in entity.flattening(distance, segments=16)]
    defining = list(entity.control_points) or list(entity.fit_points)
    size = 0.0
    if defining:
        xs = [v[0] for v in defining]
        ys = [v[1] for v in defining]
        size = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    distance = max(size * CURVE_TOLERANCE_REL, 1e-12)
    return [(v.x, v.y) for v in entity.flattening(distance, segments=8)]


def _circle_points(circle) -> list[Point]:
    n = math.ceil(360.0 / ARC_STEP_DEG)
    angles = [360.0 * i / n for i in range(n)]
    return [(v.x, v.y) for v in circle.vertices(angles)]


def _close(a: Point, b: Point, tol: float = STITCH_TOLERANCE) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol and math.dist(a, b) <= tol


# --------------------------------------------------------------------------
# Stitching and area
# --------------------------------------------------------------------------

def _build_area(chains: list[list[Point]], closed: list[list[Point]], piece: ParsedPiece) -> None:
    all_pts = [p for c in chains for p in c] + [p for c in closed for p in c]
    if all_pts:
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        piece.bbox_raw = (max(xs) - min(xs), max(ys) - min(ys))

    chains, closed = _drop_degenerate_and_duplicates(chains, closed, piece)
    result = stitch(chains)
    loops = closed + result.loops
    piece.loops = loops
    piece.open_chains = result.open_chains
    piece.error_points = result.error_points
    for text in result.errors:
        piece.add(Level.ERROR, text)

    if not loops and not result.errors:
        if piece.status < Level.ERROR:
            piece.add(Level.ERROR, "No cut lines were found in this file (no lines, arcs, or curves).")
        return
    if result.errors or piece.status >= Level.ERROR:
        if loops:
            piece.loop_depths = _nesting(loops)[2]
        piece.net_area_raw = None
        return
    piece.net_area_raw = _net_area(loops, piece)


def _drop_degenerate_and_duplicates(chains, closed, piece: ParsedPiece):
    seen = set()
    dupes = 0

    def keep(c, is_closed):
        nonlocal dupes
        if _chain_length(c) <= STITCH_TOLERANCE:
            return False
        key = (is_closed, _chain_key(sorted(c) if is_closed else c))
        if key in seen:
            dupes += 1
            return False
        seen.add(key)
        return True

    chains = [c for c in chains if keep(c, False)]
    closed = [c for c in closed if keep(c, True)]
    if dupes:
        piece.add(Level.INFO, f"Removed {dupes} duplicate line(s)/arc(s)/circle(s) drawn exactly on top of another.")
    return chains, closed


def _chain_length(c: list[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(c, c[1:]))


def _chain_key(c: list[Point]):
    def r(p):
        return (round(p[0] / STITCH_TOLERANCE), round(p[1] / STITCH_TOLERANCE))
    fwd = (r(c[0]), r(c[len(c) // 2]), r(c[-1]), len(c))
    rev = (r(c[-1]), r(c[(len(c) - 1) - len(c) // 2]), r(c[0]), len(c))
    return min(fwd, rev)


class _NodeIndex:
    """Merges endpoints lying within tolerance of each other into shared nodes."""

    def __init__(self, tol: float):
        self.tol = tol
        self.grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        self.points: list[Point] = []

    def node_for(self, p: Point) -> int:
        cx, cy = math.floor(p[0] / self.tol), math.floor(p[1] / self.tol)
        best, best_d = None, None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for idx in self.grid.get((cx + dx, cy + dy), ()):
                    d = math.dist(p, self.points[idx])
                    if d <= self.tol and (best_d is None or d < best_d):
                        best, best_d = idx, d
        if best is not None:
            return best
        self.points.append(p)
        idx = len(self.points) - 1
        self.grid[(cx, cy)].append(idx)
        return idx


@dataclass
class StitchResult:
    loops: list[list[Point]]
    errors: list[str]
    open_chains: list[list[Point]]  # runs that couldn't be closed into a loop
    error_points: list[Point]  # loose ends and ambiguous junctions


def stitch(chains: list[list[Point]], tol: float = STITCH_TOLERANCE) -> StitchResult:
    """Join open chains into closed loops."""
    index = _NodeIndex(tol)
    ends: list[tuple[int, int]] = []
    adjacency: dict[int, list[int]] = defaultdict(list)  # node -> chain indices
    for i, c in enumerate(chains):
        a, b = index.node_for(c[0]), index.node_for(c[-1])
        ends.append((a, b))
        adjacency[a].append(i)
        adjacency[b].append(i)

    errors: list[str] = []
    dangling = [n for n, cs in adjacency.items() if len(cs) == 1]
    junctions = [n for n, cs in adjacency.items() if len(cs) > 2]

    if dangling:
        errors.extend(_gap_messages(dangling, index.points))
    if junctions:
        locs = ", ".join(_fmt(index.points[n]) for n in junctions[:MAX_LOCATION_MESSAGES])
        more = f" (and {len(junctions) - MAX_LOCATION_MESSAGES} more)" if len(junctions) > MAX_LOCATION_MESSAGES else ""
        errors.append(f"Found {len(junctions)} spot(s) where three or more lines meet, so the outline "
                      f"is ambiguous — near {locs}{more}. Check for overlapping or branching lines.")

    loops: list[list[Point]] = []
    open_chains: list[list[Point]] = []
    used = [False] * len(chains)
    bad_nodes = set(dangling) | set(junctions)
    # Walk from each loose end first so open runs are traced end to end,
    # then walk whatever is left (closed loops).
    walks = [(adjacency[n][0], n) for n in dangling] + [(i, None) for i in range(len(chains))]
    for start, from_node in walks:
        if used[start]:
            continue
        reverse = from_node is not None and ends[start][1] == from_node and ends[start][0] != from_node
        pts, ok = _walk(start, chains, ends, adjacency, used, bad_nodes, reverse=reverse)
        if ok and len(pts) >= 3:
            loops.append(pts)
        else:
            open_chains.append(pts)
    error_points = [index.points[n] for n in dangling + junctions]
    return StitchResult(loops, errors, open_chains, error_points)


def _walk(start, chains, ends, adjacency, used, bad_nodes, reverse=False):
    """Follow chains from `start` until returning to the start node (a loop), or
    until running out of connections (an open run, returned with ok=False)."""
    first_node, node = ends[start]
    pts = list(chains[start])
    if reverse:
        first_node, node = node, first_node
        pts.reverse()
    used[start] = True
    ok = first_node not in bad_nodes and node not in bad_nodes
    current = start
    while node != first_node:
        if node in bad_nodes:
            ok = False
        nxt = next((c for c in adjacency[node] if c != current and not used[c]), None)
        if nxt is None:
            return pts, False  # open run: keep every point
        a, b = ends[nxt]
        seg = chains[nxt] if a == node else list(reversed(chains[nxt]))
        pts.extend(seg[1:])
        node = b if a == node else a
        used[nxt] = True
        current = nxt
    return pts[:-1], ok  # drop repeated closing point


def _gap_messages(dangling: list[int], points: list[Point]) -> list[str]:
    msgs = []
    remaining = list(dangling)
    reported = set()
    for n in remaining:
        if n in reported or len(msgs) >= MAX_LOCATION_MESSAGES:
            continue
        p = points[n]
        others = [m for m in remaining if m != n and m not in reported]
        if others:
            m = min(others, key=lambda k: math.dist(p, points[k]))
            reported.update((n, m))
            msgs.append(f"The outline has a gap: lines don't connect between {_fmt(p)} and "
                        f"{_fmt(points[m])} (gap of {math.dist(p, points[m]):.4g} file units).")
        else:
            reported.add(n)
            msgs.append(f"The outline has a loose end near {_fmt(p)} that doesn't connect to anything.")
    left = len([n for n in dangling if n not in reported])
    if left:
        msgs.append(f"...and {left} more loose end(s).")
    return msgs


def _fmt(p: Point) -> str:
    return f"({p[0]:.4g}, {p[1]:.4g})"


def polygon_area(pts: list[Point]) -> float:
    """Absolute shoelace area."""
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def point_in_polygon(p: Point, poly: list[Point]) -> bool:
    x, y = p
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _bbox(pts: list[Point]):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _loop_inside(inner: list[Point], outer: list[Point], inner_bb=None, outer_bb=None) -> bool:
    """True if `inner` lies inside `outer`. Uses a majority vote over a sample of
    vertices so a cutout that merely touches the outline still counts as inside."""
    ib = inner_bb or _bbox(inner)
    ob = outer_bb or _bbox(outer)
    t = STITCH_TOLERANCE
    if ib[0] < ob[0] - t or ib[1] < ob[1] - t or ib[2] > ob[2] + t or ib[3] > ob[3] + t:
        return False
    step = max(1, len(inner) // 16)
    sample = inner[::step]
    hits = sum(1 for p in sample if point_in_polygon(p, outer))
    return hits * 2 > len(sample)


def _nesting(loops: list[list[Point]]):
    """Returns (areas, order largest-first, depth per loop, inside_outer map).
    Depth = number of larger loops containing a loop: even = solid, odd = hole."""
    areas = [polygon_area(l) for l in loops]
    order = sorted(range(len(loops)), key=lambda i: areas[i], reverse=True)
    outer_i = order[0]
    bbs = [_bbox(l) for l in loops]
    inside_outer = {i: _loop_inside(loops[i], loops[outer_i], bbs[i], bbs[outer_i]) for i in order[1:]}
    depth = [0] * len(loops)
    for rank, i in enumerate(order[1:], start=1):
        depth[i] = sum(1 for j in order[:rank]
                       if (inside_outer[i] if j == outer_i else _loop_inside(loops[i], loops[j], bbs[i], bbs[j])))
    return areas, order, depth, inside_outer


def _net_area(loops: list[list[Point]], piece: ParsedPiece) -> float | None:
    areas, order, depth, inside_outer = _nesting(loops)
    piece.loop_depths = depth
    outer_i = order[0]
    outer_area = areas[outer_i]
    if outer_area <= 0:
        piece.add(Level.ERROR, "The outline encloses no area.")
        return None

    others = order[1:]
    single_group = all(depth[i] == 1 and inside_outer[i] for i in others)

    if single_group:
        holes = sum(areas[i] for i in others)
        if any(areas[i] >= outer_area for i in others):
            piece.add(Level.ERROR, "A cutout is as large as the outer outline — the file probably "
                                   "contains a duplicate outline. Please review it.")
            return None
        if holes >= outer_area:
            piece.add(Level.ERROR, "The cutouts add up to more than the outer outline, which "
                                   "shouldn't be possible. The file probably didn't read correctly.")
            return None
        if others:
            piece.add(Level.INFO, f"Outer outline with {len(others)} cutout(s) subtracted.")
        return outer_area - holes

    # Several separate shapes: warn and use even-odd nesting so the number is still sensible.
    tops = sum(1 for i in order if depth[i] % 2 == 0)
    net = sum(areas[i] if depth[i] % 2 == 0 else -areas[i] for i in order)
    if net <= 0:
        piece.add(Level.ERROR, "The shapes in this file don't form a sensible outline "
                               "(the cutouts are larger than the solid parts).")
        return None
    piece.add(Level.WARNING,
              f"This file seems to contain {tops} separate shapes rather than one piece with "
              "cutouts. The area shown adds up the separate shapes (minus their own cutouts). "
              "Please check this file is really one piece.")
    return net
