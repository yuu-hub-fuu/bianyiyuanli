from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .tokens import Span


class Level(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"


@dataclass(slots=True)
class Diagnostic:
    level: Level
    span: Span
    message: str
    notes: list[str] = field(default_factory=list)
    fixits: list[str] = field(default_factory=list)


class DiagnosticBag:
    def __init__(self) -> None:
        self.items: list[Diagnostic] = []

    def error(self, span: Span, message: str, *notes: str) -> None:
        self.items.append(Diagnostic(Level.ERROR, span, message, list(notes), []))

    def warn(self, span: Span, message: str, *notes: str) -> None:
        self.items.append(Diagnostic(Level.WARNING, span, message, list(notes), []))

    def has_errors(self) -> bool:
        return any(d.level == Level.ERROR for d in self.items)
