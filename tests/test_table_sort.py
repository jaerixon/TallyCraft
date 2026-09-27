from types import SimpleNamespace

from tallycraft.calc import ResultLine, SkippedLine
from tallycraft.messages import Level
from tallycraft.table_sort import order_results, sort_pieces


def row(name, count=1, mtime=0.0, status=Level.OK):
    # sort_pieces only reads these attributes, so a stand-in keeps the test independent of DXFs
    return SimpleNamespace(name=name, count=count, mtime=mtime, status=status)


ROWS = [
    ("a", row("beta.dxf", count=10, mtime=300.0, status=Level.OK)),
    ("b", row("Alpha.dxf", count=2, mtime=100.0, status=Level.ERROR)),
    ("c", row("gamma.dxf", count=2, mtime=None, status=Level.WARNING)),   # missing file
    ("d", row("ALPHA2.dxf", count=9, mtime=200.0, status=Level.INFO)),
]


def test_count_is_numeric_not_text():
    assert sort_pieces(ROWS, "count", False) == ["b", "c", "d", "a"]  # 2, 2, 9, 10 (ties keep import order)
    assert sort_pieces(ROWS, "count", True) == ["a", "d", "b", "c"]


def test_file_name_case_insensitive():
    assert sort_pieces(ROWS, "file", False) == ["b", "d", "a", "c"]
    assert sort_pieces(ROWS, "file", True) == ["c", "a", "d", "b"]


def test_date_modified_uses_timestamp_and_missing_stays_last():
    assert sort_pieces(ROWS, "modified", False) == ["b", "d", "a", "c"]
    assert sort_pieces(ROWS, "modified", True) == ["a", "d", "b", "c"]


def test_status_errors_first():
    assert sort_pieces(ROWS, "status", False) == ["b", "c", "d", "a"]
    assert sort_pieces(ROWS, "status", True) == ["a", "d", "c", "b"]


LINES = [ResultLine("b.dxf", 9.5, 2, 19.0), ResultLine("A.dxf", 100.25, 1, 100.25),
         ResultLine("c.dxf", 10.0, 3, 30.0)]
SKIPPED = [SkippedLine("zz.dxf", 1, "gap"), SkippedLine("aa.dxf", 4, "bad")]


def names(seq):
    return [x.name for x in seq]


def test_results_numeric_sorts_and_skipped_stay_at_bottom():
    # 9.5 < 10.0 < 100.25 numerically (as text "100.25" < "9.5")
    assert names(order_results(LINES, SKIPPED, "per", False)) == ["b.dxf", "c.dxf", "A.dxf", "zz.dxf", "aa.dxf"]
    assert names(order_results(LINES, SKIPPED, "per", True)) == ["A.dxf", "c.dxf", "b.dxf", "zz.dxf", "aa.dxf"]
    assert names(order_results(LINES, SKIPPED, "total", True)) == ["A.dxf", "c.dxf", "b.dxf", "zz.dxf", "aa.dxf"]
    assert names(order_results(LINES, SKIPPED, "count", False)) == ["A.dxf", "b.dxf", "c.dxf", "zz.dxf", "aa.dxf"]
    assert names(order_results(LINES, SKIPPED, "file", True)) == ["c.dxf", "b.dxf", "A.dxf", "zz.dxf", "aa.dxf"]


def test_results_unsorted_keeps_calculation_order():
    assert names(order_results(LINES, SKIPPED, None, False)) == ["b.dxf", "A.dxf", "c.dxf", "zz.dxf", "aa.dxf"]
