from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexa.utils.model import Span


@dataclass(slots=True)
class Node:
    span: Span


@dataclass(slots=True)
class Module(Node):
    items: list[Stmt] = field(default_factory=list)


class Stmt(Node):
    pass


class Expr(Node):
    inferred_type: str | None = None


@dataclass(slots=True)
class Block(Stmt):
    statements: list[Stmt] = field(default_factory=list)


@dataclass(slots=True)
class LetStmt(Stmt):
    name: str
    type_name: str | None
    init: Expr | None


@dataclass(slots=True)
class AssignStmt(Stmt):
    target: str
    value: Expr


@dataclass(slots=True)
class IfStmt(Stmt):
    cond: Expr
    then_branch: Block
    else_branch: Block | None


@dataclass(slots=True)
class WhileStmt(Stmt):
    cond: Expr
    body: Block


@dataclass(slots=True)
class ReturnStmt(Stmt):
    value: Expr | None


@dataclass(slots=True)
class ExprStmt(Stmt):
    expr: Expr


@dataclass(slots=True)
class FunctionDef(Stmt):
    name: str
    params: list[tuple[str, str]]
    return_type: str
    body: Block


@dataclass(slots=True)
class IntLiteral(Expr):
    value: int


@dataclass(slots=True)
class BoolLiteral(Expr):
    value: bool


@dataclass(slots=True)
class StringLiteral(Expr):
    value: str


@dataclass(slots=True)
class NameExpr(Expr):
    name: str


@dataclass(slots=True)
class UnaryExpr(Expr):
    op: str
    rhs: Expr


@dataclass(slots=True)
class BinaryExpr(Expr):
    op: str
    lhs: Expr
    rhs: Expr


@dataclass(slots=True)
class CallExpr(Expr):
    callee: str
    args: list[Expr] = field(default_factory=list)

