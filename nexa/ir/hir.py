from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class HIRInstr:
    op: str
    dst: str | None
    src1: str | None
    src2: str | None
    ty: str
    span: tuple[int, int] = (0, 0)


@dataclass(slots=True)
class HIRFunction:
    name: str
    instrs: list[HIRInstr] = field(default_factory=list)


@dataclass(slots=True)
class HIRModule:
    functions: list[HIRFunction] = field(default_factory=list)
