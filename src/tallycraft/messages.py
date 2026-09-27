"""Status levels and user-facing messages attached to a piece/row."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Level(IntEnum):
    """Severity of a row message. Higher is worse; a row's status is its worst message."""

    OK = 0
    INFO = 1  # never blocks Calculate
    WARNING = 2  # Calculate asks once for confirmation
    ERROR = 3  # blocks Calculate

    @property
    def label(self) -> str:
        return {0: "OK", 1: "Info", 2: "Warning", 3: "Error"}[int(self)]


@dataclass(frozen=True)
class Message:
    level: Level
    text: str


def worst(messages: list[Message]) -> Level:
    return max((m.level for m in messages), default=Level.OK)
