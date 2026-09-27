"""Display-order sorting for the pieces and results tables.

Sorting only decides the order rows are *shown* in. It never touches import
order, which calculation and package presets use (see SPEC §4).
"""

from __future__ import annotations

from typing import Callable, Hashable, Sequence, TypeVar

from .calc import ResultLine, SkippedLine
from .messages import Level
from .pieces import PieceRow

K = TypeVar("K", bound=Hashable)

# Errors first, then Warnings, Info, OK (ascending sort).
STATUS_RANK = {Level.ERROR: 0, Level.WARNING: 1, Level.INFO: 2, Level.OK: 3}

PIECE_SORT_KEYS: dict[str, Callable[[PieceRow], object]] = {
    "count": lambda r: r.count,
    "file": lambda r: r.name.casefold(),
    "modified": lambda r: r.mtime,  # real timestamp, not the displayed text
    "status": lambda r: STATUS_RANK[r.status],
}

RESULT_SORT_KEYS: dict[str, Callable[[ResultLine], object]] = {
    "file": lambda l: l.name.casefold(),
    "per": lambda l: l.weight_per_piece_g,
    "count": lambda l: l.count,
    "total": lambda l: l.item_total_g,
}


def _sorted(items: Sequence[tuple[K, object]], key: Callable, descending: bool) -> list[K]:
    """Stable sort of (id, obj) pairs. Objects whose key is None (e.g. a missing
    file's timestamp) always go last, whichever direction is chosen."""
    present = [(i, o) for i, o in items if key(o) is not None]
    missing = [i for i, o in items if key(o) is None]
    present.sort(key=lambda pair: key(pair[1]), reverse=descending)  # Python's sort is stable
    return [i for i, _ in present] + missing


def sort_pieces(items: Sequence[tuple[K, PieceRow]], column: str, descending: bool) -> list[K]:
    """items: (tree id, row) in import order. Returns ids in display order."""
    return _sorted(items, PIECE_SORT_KEYS[column], descending)


def order_results(lines: Sequence[ResultLine], skipped: Sequence[SkippedLine],
                  column: str | None, descending: bool) -> list[ResultLine | SkippedLine]:
    """Calculated lines (sorted if a column is chosen), then skipped rows, which
    always stay at the bottom regardless of sort direction."""
    shown: list = list(lines)
    if column is not None:
        shown = _sorted(list(enumerate(lines)), RESULT_SORT_KEYS[column], descending)
        shown = [lines[i] for i in shown]
    return shown + list(skipped)
