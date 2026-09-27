"""Calibration: how many grams one cm² of this plywood weighs (SPEC §4.3, §7).

Two methods produce a grams-per-cm² ratio; everything downstream (per-piece
weights, totals, lb/oz) only uses `.grams_per_cm2`:

- Control sample: a separately cut rectangle (calc.ControlSample).
- Reference piece: N already-cut pieces from the pieces table, weighed together.
  g/cm² = total_weight_g / (quantity × one piece's net area in cm²), using the
  same net area and unit handling as that row.
"""

from __future__ import annotations

from dataclasses import dataclass

from .calc import parse_positive
from .messages import Level
from .pieces import PieceRow

MODE_REFERENCE = "reference"
MODE_CONTROL = "control"
MODES = (MODE_REFERENCE, MODE_CONTROL)

TIP = "For best accuracy, weigh several pieces or a large piece."


@dataclass(frozen=True)
class ReferencePiece:
    name: str
    path: str
    quantity: int
    weight_g: float
    area_cm2: float  # net area of ONE piece
    from_preset: str | None = None  # preset name when using the saved area (file not in this package)

    @property
    def grams_per_cm2(self) -> float:
        return self.weight_g / (self.quantity * self.area_cm2)


@dataclass(frozen=True)
class SavedReference:
    """A reference-mode preset whose file isn't in the current pieces table."""
    name: str
    path: str
    area_cm2: float
    preset: str


def parse_positive_int(text: str, field_name: str) -> int:
    raw = (text or "").strip()
    if not raw:
        raise ValueError(f"{field_name} is empty. Enter how many pieces you weighed (1 or more).")
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{field_name} \"{raw}\" must be a whole number of pieces, e.g. 10.") from None
    if value < 1:
        raise ValueError(f"{field_name} must be 1 or more (you entered {raw}).")
    return value


def _parse_qty_weight(quantity: str, weight: str, errors: list[str]):
    qty = wt = None
    try:
        qty = parse_positive_int(quantity, "Quantity weighed")
    except ValueError as exc:
        errors.append(str(exc))
    try:
        wt = parse_positive(weight, "Total weight (g)")
    except ValueError as exc:
        errors.append(str(exc))
    return qty, wt


def validate_reference(row: PieceRow | None, quantity: str, weight: str,
                       saved: SavedReference | None = None,
                       removed_note: str = "") -> tuple[ReferencePiece | None, list[str], list[str]]:
    """Returns (reference, errors, warnings). `row` is the chosen table row;
    `saved` is used instead when calibrating from a preset whose file isn't loaded."""
    errors: list[str] = []
    warnings: list[str] = []
    qty, wt = _parse_qty_weight(quantity, weight, errors)

    if row is None and saved is None:
        errors.insert(0, removed_note or "Choose the reference piece you weighed from the Piece list.")
        return None, errors, warnings

    if row is not None:
        if row.status == Level.ERROR or row.area_cm2 is None:
            if row.unit not in ("in", "mm") and row.parsed.bbox_raw is not None:
                why = "its units are Unknown — choose Inches or Millimeters in the Units column"
            else:
                why = next((m.text for m in row.messages if m.level == Level.ERROR), "its area couldn't be measured")
            errors.insert(0, f"The reference piece {row.name} can't be used because its area can't be "
                             f"trusted: {why}")
            return None, errors, warnings
        warnings = [m.text for m in row.messages if m.level == Level.WARNING]
        if errors:
            return None, errors, warnings
        return ReferencePiece(row.name, row.path, qty, wt, row.area_cm2), errors, warnings

    if errors:
        return None, errors, warnings
    return ReferencePiece(saved.name, saved.path, qty, wt, saved.area_cm2, from_preset=saved.preset), [], []


def describe(cal) -> str:
    """One line describing where the ratio came from (Copy Results, status bar)."""
    g = cal.grams_per_cm2
    ratio = f"{g:.5f} g/cm² ({g * 6.4516:.5f} g/in²)"
    if isinstance(cal, ReferencePiece):
        src = f"reference piece {cal.name}, {cal.quantity} weighed, {cal.weight_g:g} g total"
        if cal.from_preset:
            src += f" (area from saved preset \"{cal.from_preset}\")"
        return f"Calibration: {src} → {ratio}"
    return (f"Calibration: control sample {cal.length:g} × {cal.width:g} {cal.unit}, "
            f"{cal.weight_g:g} g → {ratio}")
