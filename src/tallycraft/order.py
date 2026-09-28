"""Orders: a list of packages (product definitions), each with a quantity.

A *Package* is a product definition — DXF pieces with per-kit counts — i.e.
what a package preset stores. An *Order* is what ships: packages × quantity.
A normal single-item sale is an order with one package at quantity 1.

Editing a package in an order changes only the order's copy. "Unsaved
changes" is derived by comparing the package's current contents with the
baseline it was loaded from / last saved as, so undoing an edit clears it.
See SPEC §4.0 and §6.3.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .messages import Level
from .pieces import PieceRow

BLANK_NAME = "New Package"


def norm_path(path: str) -> str:
    """Identity of a DXF file: absolute, normalized, case-insensitive on Windows."""
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


# ============================================================================ package

@dataclass
class Package:
    name: str
    quantity: int = 1
    preset_name: str | None = None  # the package preset this came from / was saved as
    rows: dict[str, PieceRow] = field(default_factory=dict)  # tree id -> row
    order: list[str] = field(default_factory=list)  # tree ids in import order
    # What the preset contains, for the "unsaved changes" marker:
    # [(norm path, units|None, count, display name)]
    baseline: list[tuple[str, str | None, int, str]] = field(default_factory=list)

    def ordered_rows(self) -> list[PieceRow]:
        return [self.rows[i] for i in self.order]

    def pieces_spec(self) -> list[dict]:
        """The package-preset "pieces" list for the current contents."""
        out = []
        for r in self.ordered_rows():
            entry = {"path": os.path.abspath(r.path), "units": r.unit, "count": r.count, "mtime": r.mtime}
            if r.display_name:
                entry["display_name"] = r.display_name
            out.append(entry)
        return out

    def set_baseline(self, pieces: list[dict]) -> None:
        self.baseline = [(norm_path(p["path"]), p.get("units"), int(p.get("count", 1)),
                          (p.get("display_name") or "").strip()) for p in pieces]

    def mark_saved(self, preset_name: str) -> None:
        self.preset_name = preset_name
        self.name = preset_name
        self.set_baseline(self.pieces_spec())

    @property
    def is_dirty(self) -> bool:
        headers = {norm_path(r.path): r.parsed.header_unit for r in self.ordered_rows()}
        current = sorted((norm_path(r.path), r.unit, r.count, r.display_name) for r in self.ordered_rows())
        # A preset entry without units means "whatever the file's header says".
        base = sorted((p, u if u is not None else headers.get(p), c, d) for p, u, c, d in self.baseline)
        return current != base

    def status_summary(self, conflicts: int = 0) -> str:
        rows = self.ordered_rows()
        parts = []
        if not rows:
            parts.append("Empty")
        errors = sum(1 for r in rows if r.status == Level.ERROR)
        warnings = sum(1 for r in rows if r.status == Level.WARNING)
        if errors:
            parts.append(f"{errors} piece{'s' if errors != 1 else ''} with errors")
        if warnings:
            parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")
        if conflicts:
            parts.append(f"{conflicts} units conflict{'s' if conflicts != 1 else ''}")
        if self.is_dirty:
            parts.append("unsaved changes")
        return " · ".join(parts) if parts else "OK"


# ============================================================================ order

@dataclass
class Order:
    packages: list[Package] = field(default_factory=list)

    @classmethod
    def with_blank_package(cls) -> "Order":
        order = cls()
        order.packages.append(Package(order.unique_name(BLANK_NAME)))
        return order

    def unique_name(self, base: str) -> str:
        taken = {p.name for p in self.packages}
        if base not in taken and base != BLANK_NAME:
            return base
        n = 1
        while f"{base} {n}" in taken:
            n += 1
        return f"{base} {n}"

    def find_preset(self, preset_name: str) -> Package | None:
        return next((p for p in self.packages if p.preset_name == preset_name), None)

    def is_single_blank(self) -> bool:
        """True for the startup state: one empty, never-saved package at quantity 1."""
        return (len(self.packages) == 1 and not self.packages[0].order
                and self.packages[0].preset_name is None and self.packages[0].quantity == 1)

    def kit_labels(self) -> list[str]:
        """One label per individual kit: "Name" for qty 1, "Name (k of n)" otherwise."""
        labels = []
        for p in self.packages:
            if p.quantity == 1:
                labels.append(p.name)
            else:
                labels.extend(f"{p.name} ({k} of {p.quantity})" for k in range(1, p.quantity + 1))
        return labels

    def all_rows(self):
        """(package, tree id, row) for every piece in every package."""
        for p in self.packages:
            for iid in p.order:
                yield p, iid, p.rows[iid]

    def find_row(self, iid: str):
        for p in self.packages:
            if iid in p.rows:
                return p, p.rows[iid]
        return None, None

    def units_conflicts(self) -> dict[str, set[str]]:
        """norm path -> names of packages involved, for files whose Units differ between packages."""
        units = defaultdict(dict)  # path -> {package name: unit}
        for p, _iid, r in self.all_rows():
            units[norm_path(r.path)][p.name] = r.unit
        return {path: set(by_pkg) for path, by_pkg in units.items() if len(set(by_pkg.values())) > 1}


# ============================================================================ merge

@dataclass(frozen=True)
class MergedPiece:
    name: str  # file name (folder added if two files share a name)
    path: str
    kit_counts: tuple[int | None, ...]  # this kit's count, or None if the kit doesn't use it
    total_count: int
    area_cm2: float | None
    error: str = ""  # non-empty -> skipped from the totals
    warnings: tuple[str, ...] = ()
    display_name: str = ""  # from the pieces table ("" = use the file name)


def merge_order(order: Order) -> tuple[list[str], list[MergedPiece]]:
    """One entry per unique DXF file across the order (same file = same normalized
    path). Returns (kit column labels, pieces in first-seen order)."""
    labels = order.kit_labels()
    groups: dict[str, list[tuple[Package, PieceRow]]] = {}
    for p, _iid, r in order.all_rows():
        groups.setdefault(norm_path(r.path), []).append((p, r))

    basenames = defaultdict(set)
    for key, members in groups.items():
        basenames[os.path.basename(members[0][1].path).casefold()].add(key)

    merged = []
    for key, members in groups.items():
        first = members[0][1]
        name = first.name
        if len(basenames[name.casefold()]) > 1:
            name = f"{name} — {Path(first.path).parent.name}"

        kit_counts: list[int | None] = []
        total = 0
        for p in order.packages:
            c = sum(r.count for q, r in members if q is p) if any(q is p for q, _ in members) else None
            kit_counts.extend([c] * p.quantity)
            total += (c or 0) * p.quantity

        error = ""
        for p, r in members:
            if r.status == Level.ERROR:
                first_err = next(m.text for m in r.messages if m.level == Level.ERROR)
                error = f"{first_err} (in package \"{p.name}\")"
                break
        units = {}
        for p, r in members:
            units.setdefault(r.unit, []).append(p.name)
        if not error and len(units) > 1:
            from .calc import UNIT_LABELS
            detail = "; ".join(f"{UNIT_LABELS.get(u, u)} in {', '.join(repr(n) for n in names)}"
                               for u, names in units.items())
            error = (f"Units conflict: this file is set to different Units in different packages ({detail}). "
                     "Set the same Units in every package.")
        areas = {round(r.area_cm2, 9) for _p, r in members if r.area_cm2 is not None}
        if not error and len(areas) > 1:
            error = ("This file was read at different times and its shape differs between packages. "
                     "Use Re-read Selected in each package so they match.")
        warnings = tuple(f"{m.text} (in package \"{p.name}\")" for p, r in members
                         for m in r.messages if m.level == Level.WARNING)
        names = list(dict.fromkeys(r.display_name for _p, r in members if r.display_name))
        if len(names) > 1:
            warnings += (f"Different display names in different packages ({', '.join(repr(n) for n in names)}); "
                         f"packing lists use {names[0]!r}.",)
        merged.append(MergedPiece(name, first.path, tuple(kit_counts), total,
                                  None if error else first.area_cm2, error, warnings,
                                  names[0] if names else ""))
    return labels, merged
