from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class HIRKind(Enum):
    PARAM = auto()
    CONST = auto()
    MOVE = auto()
    UNARY = auto()
    BIN = auto()
    ARG = auto()
    CALL = auto()
    RET = auto()
    LABEL = auto()
    JMP = auto()
    BR_TRUE = auto()
    BR_READY = auto()
    SPAWN = auto()
    OTHER = auto()


def infer_kind(op: str) -> HIRKind:
    if op == "param":
        return HIRKind.PARAM
    if op.startswith("const."):
        return HIRKind.CONST
    if op.startswith("mov."):
        return HIRKind.MOVE
    if op.startswith("unary."):
        return HIRKind.UNARY
    if op.startswith("bin."):
        return HIRKind.BIN
    if op == "arg":
        return HIRKind.ARG
    if op.startswith("call"):
        return HIRKind.CALL
    if op == "ret":
        return HIRKind.RET
    if op == "label":
        return HIRKind.LABEL
    if op == "jmp":
        return HIRKind.JMP
    if op == "br.true":
        return HIRKind.BR_TRUE
    if op == "br.ready":
        return HIRKind.BR_READY
    if op == "spawn":
        return HIRKind.SPAWN
    return HIRKind.OTHER


@dataclass(slots=True)
class HIRInstr:
    op: str
    dst: str | None
    src1: str | None
    src2: str | None
    ty: str
    span: tuple[int, int] = (0, 0)
    kind: HIRKind = field(init=False)
    meta: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.kind = infer_kind(self.op)
        if self.kind == HIRKind.BIN:
            self.meta.setdefault("op", self.op[4:])
        if self.kind == HIRKind.UNARY:
            self.meta.setdefault("op", self.op[6:])
        if self.kind == HIRKind.CALL and self.src1:
            self.meta.setdefault("callee", self.src1)

    @property
    def result(self) -> str | None:
        return self.dst

    @property
    def args(self) -> list[str | None]:
        return [self.src1, self.src2]

    def quad(self) -> tuple[str, str | None, str | None, str | None]:
        return (self.op, self.src1, self.src2, self.dst)


@dataclass(slots=True)
class HIRFunction:
    name: str
    instrs: list[HIRInstr] = field(default_factory=list)


@dataclass(slots=True)
class HIRModule:
    functions: list[HIRFunction] = field(default_factory=list)
