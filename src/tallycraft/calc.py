"""Units, control-sample validation, and the weight calculation (SPEC §7).

All areas are converted to cm² before any division, so the control sample and
each piece may use different units.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

UNIT_TO_CM = {"in": 2.54, "mm": 0.1}
UNIT_LABELS = {"in": "Inches", "mm": "Millimeters", "unknown": "Unknown"}
LABEL_TO_UNIT = {v: k for k, v in UNIT_LABELS.items()}
AREA_SUFFIX = {"in": "in²", "mm": "mm²", "unknown": "units²"}

GRAMS_PER_POUND = 453.59237
GRAMS_PER_OUNCE = GRAMS_PER_POUND / 16  # 28.349523125


def area_to_cm2(area: float, unit: str) -> float:
    s = UNIT_TO_CM[unit]
    return area * s * s


def parse_positive(text: str, field_name: str) -> float:
    """Parse a user-entered number that must be > 0. Raises ValueError with a
    plain-language message naming the field."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError(f"{field_name} is empty. Please enter a number greater than 0.")
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{field_name} \"{raw}\" isn't a number. Use digits and a decimal point, e.g. 4.125.") from None
    if not math.isfinite(value):
        raise ValueError(f"{field_name} \"{raw}\" isn't a usable number.")
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0 (you entered {raw}).")
    return value


@dataclass(frozen=True)
class ControlSample:
    length: float
    width: float
    unit: str  # "in" | "mm"
    weight_g: float

    @property
    def area_cm2(self) -> float:
        return area_to_cm2(self.length * self.width, self.unit)

    @property
    def grams_per_cm2(self) -> float:
        return self.weight_g / self.area_cm2


def validate_control(length: str, width: str, unit: str, weight: str) -> tuple[ControlSample | None, list[str]]:
    """Returns (sample, []) when valid, else (None, [one message per problem])."""
    errors: list[str] = []
    values = {}
    for key, label, text in (("length", "Control Length", length),
                             ("width", "Control Width", width),
                             ("weight_g", "Control Weight (g)", weight)):
        try:
            values[key] = parse_positive(text, label)
        except ValueError as exc:
            errors.append(str(exc))
    if unit not in UNIT_TO_CM:
        errors.append("Choose Inches or mm for the control sample's Length/Width.")
    if errors:
        return None, errors
    return ControlSample(unit=unit, **values), []


@dataclass(frozen=True)
class PieceInput:
    name: str
    area_cm2: float
    count: int  # total pieces across the whole order
    kit_counts: tuple = ()  # per individual kit: that kit's count, or None if unused


@dataclass(frozen=True)
class ResultLine:
    name: str
    weight_per_piece_g: float
    count: int
    item_total_g: float
    kit_counts: tuple = ()


@dataclass(frozen=True)
class SkippedLine:
    """A piece left out of the total because it has an Error."""
    name: str
    count: int
    reason: str
    kit_counts: tuple = ()


@dataclass(frozen=True)
class CalcResult:
    lines: list[ResultLine]
    total_g: float
    grams_per_cm2: float
    skipped: list[SkippedLine] = ()
    kit_labels: tuple = ()  # one per individual kit, e.g. "XL Standard Box (1 of 2)"

    @property
    def incomplete(self) -> bool:
        return bool(self.skipped)

    @property
    def incomplete_note(self) -> str:
        """Shown beside the total so a partial weight is never mistaken for a complete one."""
        n = len(self.skipped)
        return f"Incomplete: {n} file{'s' if n != 1 else ''} skipped" if n else ""


def calculate(pieces: list[PieceInput], control: ControlSample,
              skipped: list[SkippedLine] = (), kit_labels: tuple = ()) -> CalcResult:
    """`control` is any calibration with a .grams_per_cm2 (control sample or reference piece)."""
    gpc = control.grams_per_cm2
    lines = []
    for p in pieces:
        per = gpc * p.area_cm2
        lines.append(ResultLine(p.name, per, p.count, per * p.count, tuple(p.kit_counts)))
    return CalcResult(lines, sum(l.item_total_g for l in lines), gpc, list(skipped), tuple(kit_labels))


SKIPPED_LABEL = "Skipped - not included"


def kit_cell(count) -> str:
    """A per-kit count cell: the kit's own count, or a dash if the kit doesn't use the piece."""
    return "—" if count is None else str(count)


def results_as_text(result: CalcResult, calibration_note: str = "") -> str:
    """Tab-separated table for pasting into a spreadsheet or email. Columns match
    the Results table: File Name, one column per kit, Total Count, weights."""
    kits = list(result.kit_labels)

    def kit_cells(counts) -> list[str]:
        counts = list(counts) + [None] * (len(kits) - len(counts))
        return [kit_cell(c) for c in counts[:len(kits)]]

    out = ["\t".join(["File Name", *kits, "Total Count", "Weight per piece (g)", "Item Total (g)"])]
    out += ["\t".join([l.name, *kit_cells(l.kit_counts), str(l.count), f"{l.weight_per_piece_g:.2f}",
                       f"{l.item_total_g:.2f}"]) for l in result.lines]
    out += ["\t".join([s.name, *kit_cells(s.kit_counts), str(s.count), SKIPPED_LABEL, SKIPPED_LABEL])
            for s in result.skipped]
    total = "\t".join(["Package Total", *[""] * len(kits), "", "",
                       f"{result.total_g:.1f} g ({format_lb_oz(result.total_g)})"])
    if result.incomplete:
        total += f"\t{result.incomplete_note.upper()} - NOT A COMPLETE SHIPPING WEIGHT"
    out.append(total)
    for s in result.skipped:
        out.append(f"Skipped: {s.name} - {s.reason}")
    if calibration_note:
        out.append(calibration_note)
    return "\n".join(out)


def grams_to_lb_oz(grams: float, oz_decimals: int = 1) -> tuple[int, float]:
    """Split grams into whole pounds + ounces, rounding ounces and carrying 16 oz."""
    total_oz = round(grams / GRAMS_PER_OUNCE, oz_decimals)
    lb = int(total_oz // 16)
    oz = round(total_oz - lb * 16, oz_decimals)
    if oz >= 16:
        lb, oz = lb + 1, round(oz - 16, oz_decimals)
    return lb, oz


def format_lb_oz(grams: float) -> str:
    lb, oz = grams_to_lb_oz(grams)
    return f"{lb} lb {oz:.1f} oz"
