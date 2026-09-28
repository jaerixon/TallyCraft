"""Row model for the pieces table: a parsed DXF plus the user's overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

from .calc import AREA_SUFFIX, UNIT_LABELS, UNIT_TO_CM, area_to_cm2
from .dxf_geometry import ParsedPiece, parse_dxf
from .messages import Level, Message, worst

MTIME_SLACK_S = 2.0  # FAT/zip round-trips can shift mtimes slightly
# A File units choice that makes the longest side bigger/smaller than this gets a Warning.
PLAUSIBLE_IN = (0.05, 100.0)


def file_mtime(path: str) -> float | None:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


@dataclass
class PieceRow:
    path: str
    parsed: ParsedPiece
    unit: str  # "in" | "mm" | "unknown" — the user's current choice
    count: int = 1
    mtime: float | None = None  # current on-disk mtime
    extra: list[Message] = field(default_factory=list)  # e.g. "modified since preset saved"
    display_name: str = ""  # optional name for packing lists; "" = use the file name

    @classmethod
    def load(cls, path: str, ignored_layers=(), unit: str | None = None, count: int = 1,
             stored_mtime: float | None = None, saved_what: str = "preset", cut_colors=None,
             display_name: str = "") -> "PieceRow":
        parsed = parse_dxf(path, ignored_layers, cut_colors)
        row = cls(path=path, parsed=parsed, unit=unit or parsed.header_unit,
                  count=max(1, int(count)), mtime=file_mtime(path), display_name=(display_name or "").strip())
        if stored_mtime is not None and row.mtime is not None and abs(row.mtime - stored_mtime) > MTIME_SLACK_S:
            row.extra.append(Message(Level.WARNING,
                                     f"This file has been modified since this {saved_what} was saved — "
                                     "recommend re-importing/reviewing."))
        return row

    # ------------------------------------------------------------ derived

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def messages(self) -> list[Message]:
        msgs = []
        header = self.parsed.header_unit
        if self.parsed.bbox_raw is None:
            pass  # unreadable / no geometry: the parser's own error is the real reason
        elif self.unit not in UNIT_TO_CM:
            note = self.parsed.header_unit_note or "The units for this file are unknown."
            msgs.append(Message(Level.ERROR, f"{note} Choose Inches or Millimeters in the File units column."))
        elif self.unit != header:
            if self.parsed.units_assumed:
                said = f"doesn't say; TallyCraft assumed {UNIT_LABELS[header].lower()}"
            else:
                said = f"says {UNIT_LABELS[header].lower()}" if header in UNIT_TO_CM else "says unknown"
            msgs.append(Message(Level.INFO, f"File units manually set to {UNIT_LABELS[self.unit]} "
                                            f"(the file itself {said})."))
            longest_in = max(self.parsed.bbox_raw) * UNIT_TO_CM[self.unit] / 2.54
            if not PLAUSIBLE_IN[0] <= longest_in <= PLAUSIBLE_IN[1]:
                msgs.append(Message(Level.WARNING, f"At this unit the piece would be {self.bbox_text('in')} "
                                                   f"({self.bbox_text('mm')}). Is that right?"))
        elif self.parsed.units_assumed:
            msgs.append(Message(Level.INFO, self.parsed.header_unit_note))
        return msgs + self.parsed.messages + self.extra

    @property
    def status(self) -> Level:
        return worst(self.messages)

    @property
    def area_cm2(self) -> float | None:
        if self.parsed.net_area_raw is None or self.unit not in UNIT_TO_CM:
            return None
        return area_to_cm2(self.parsed.net_area_raw, self.unit)

    # ------------------------------------------------------------ display

    def _shown_unit(self, show: str) -> str:
        """The unit to display in: show ("in"/"mm") converted from the File units, or
        the File units themselves for "file" (and whenever the File units are unknown)."""
        return show if show in UNIT_TO_CM and self.unit in UNIT_TO_CM else self.unit

    def bbox_text(self, show: str = "file") -> str:
        """Width × height. show: "in" / "mm" (converted) or "file" (the File units)."""
        bb = self.parsed.bbox_raw
        if bb is None:
            return "—"
        target = self._shown_unit(show)
        if target not in UNIT_TO_CM:
            return f"{_num(bb[0])} × {_num(bb[1])}"
        k = UNIT_TO_CM[self.unit] / UNIT_TO_CM[target]
        if show in UNIT_TO_CM and target == "mm":
            return f"{bb[0] * k:,.1f} × {bb[1] * k:,.1f} mm"
        return f"{_num(bb[0] * k)} × {_num(bb[1] * k)} {target}"

    def area_text(self, show: str = "file") -> str:
        """Net area, in in² or mm² per show (see bbox_text)."""
        if self.parsed.net_area_raw is None:
            return "—"
        target = self._shown_unit(show)
        if target not in UNIT_TO_CM:
            return _num(self.parsed.net_area_raw)
        k = (UNIT_TO_CM[self.unit] / UNIT_TO_CM[target]) ** 2
        return f"{_num(self.parsed.net_area_raw * k)} {AREA_SUFFIX[target]}"

    def mtime_text(self) -> str:
        if self.mtime is None:
            return "—"
        return datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")

    def details_text(self) -> str:
        lines = [self.path]
        msgs = self.messages
        if not msgs:
            lines.append("OK — no problems found.")
        for m in msgs:
            lines.append(f"[{m.level.label}] {m.text}")
        return "\n".join(lines)


def _num(v: float) -> str:
    if abs(v) >= 1000:
        return f"{v:,.2f}"
    return f"{v:.3f}"
