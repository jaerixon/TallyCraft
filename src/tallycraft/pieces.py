"""Row model for the pieces table: a parsed DXF plus the user's overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

from .calc import AREA_SUFFIX, UNIT_LABELS, UNIT_TO_CM, area_to_cm2
from .dxf_geometry import ParsedPiece, parse_dxf
from .messages import Level, Message, worst

MTIME_SLACK_S = 2.0  # FAT/zip round-trips can shift mtimes slightly


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

    @classmethod
    def load(cls, path: str, ignored_layers=(), unit: str | None = None, count: int = 1,
             stored_mtime: float | None = None) -> "PieceRow":
        parsed = parse_dxf(path, ignored_layers)
        row = cls(path=path, parsed=parsed, unit=unit or parsed.header_unit,
                  count=max(1, int(count)), mtime=file_mtime(path))
        if stored_mtime is not None and row.mtime is not None and abs(row.mtime - stored_mtime) > MTIME_SLACK_S:
            row.extra.append(Message(Level.WARNING,
                                     "This file has been modified since this preset was saved — "
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
        if self.unit not in UNIT_TO_CM:
            note = self.parsed.header_unit_note or "The units for this file are unknown."
            msgs.append(Message(Level.ERROR, f"{note} Choose Inches or Millimeters in the Units column."))
        elif self.unit != header:
            said = UNIT_LABELS[header].lower() if header in UNIT_TO_CM else "unknown"
            msgs.append(Message(Level.INFO, f"Units manually set to {UNIT_LABELS[self.unit]} "
                                            f"(the file itself says {said})."))
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

    def bbox_text(self) -> str:
        bb = self.parsed.bbox_raw
        if bb is None:
            return "—"
        suffix = {"in": " in", "mm": " mm"}.get(self.unit, "")
        return f"{_num(bb[0])} × {_num(bb[1])}{suffix}"

    def area_text(self) -> str:
        if self.parsed.net_area_raw is None:
            return "—"
        return f"{_num(self.parsed.net_area_raw)} {AREA_SUFFIX.get(self.unit, '')}".strip()

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
