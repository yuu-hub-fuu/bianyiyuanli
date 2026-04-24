from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, TypeVar


class DiagnosticLevel(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"


@dataclass(slots=True, frozen=True)
class Position:
    offset: int
    line: int
    column: int


@dataclass(slots=True, frozen=True)
class Span:
    start: Position
    end: Position


@dataclass(slots=True, frozen=True)
class Token:
    kind: str
    lexeme: str
    span: Span


@dataclass(slots=True)
class Diagnostic:
    level: DiagnosticLevel
    span: Span
    message: str
    notes: list[str] = field(default_factory=list)


T = TypeVar("T")


@dataclass(slots=True)
class CompileResult(Generic[T]):
    value: T | None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(d.level == DiagnosticLevel.ERROR for d in self.diagnostics)


@dataclass(slots=True)
class Symbol:
    name: str
    category: str
    type_name: str
    scope_id: int
    slot: int | None = None
    mutable: bool = True


@dataclass(slots=True)
class SymbolTable:
    scopes: list[dict[str, Symbol]] = field(default_factory=lambda: [{}])

    def push(self) -> int:
        self.scopes.append({})
        return len(self.scopes) - 1

    def pop(self) -> None:
        if len(self.scopes) == 1:
            raise RuntimeError("cannot pop global scope")
        self.scopes.pop()

    @property
    def current_scope_id(self) -> int:
        return len(self.scopes) - 1

    def insert(self, sym: Symbol) -> bool:
        scope = self.scopes[-1]
        if sym.name in scope:
            return False
        scope[sym.name] = sym
        return True

    def lookup(self, name: str) -> Symbol | None:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

