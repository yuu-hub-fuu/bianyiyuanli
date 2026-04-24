from __future__ import annotations

from dataclasses import dataclass

from nexa.frontend import ast
from nexa.ir.hir import HIRFunction, HIRInstr, HIRModule


@dataclass(slots=True)
class LowerCtx:
    temp_id: int = 0

    def temp(self) -> str:
        self.temp_id += 1
        return f"t{self.temp_id}"


class HIRLowerer:
    def __init__(self) -> None:
        self.ctx = LowerCtx()

    def lower_module(self, mod: ast.Module) -> HIRModule:
        out = HIRModule()
        for item in mod.items:
            if isinstance(item, ast.FunctionDef):
                out.functions.append(self.lower_fn(item))
        return out

    def lower_fn(self, fn: ast.FunctionDef) -> HIRFunction:
        f = HIRFunction(fn.name)
        for stmt in fn.body.statements:
            self.lower_stmt(stmt, f)
        return f

    def lower_stmt(self, stmt: ast.Stmt, f: HIRFunction) -> None:
        if isinstance(stmt, ast.LetStmt):
            if stmt.init:
                val = self.lower_expr(stmt.init, f)
                f.instrs.append(HIRInstr("mov", stmt.name, val, None, stmt.type_name or "i32"))
        elif isinstance(stmt, ast.AssignStmt):
            val = self.lower_expr(stmt.value, f)
            f.instrs.append(HIRInstr("mov", stmt.target, val, None, "i32"))
        elif isinstance(stmt, ast.ReturnStmt):
            if stmt.value:
                val = self.lower_expr(stmt.value, f)
                f.instrs.append(HIRInstr("ret", None, val, None, "void"))
            else:
                f.instrs.append(HIRInstr("ret", None, None, None, "void"))
        elif isinstance(stmt, ast.ExprStmt):
            self.lower_expr(stmt.expr, f)
        elif isinstance(stmt, ast.IfStmt):
            cond = self.lower_expr(stmt.cond, f)
            f.instrs.append(HIRInstr("if", None, cond, None, "bool"))
            for s in stmt.then_branch.statements:
                self.lower_stmt(s, f)
            if stmt.else_branch:
                f.instrs.append(HIRInstr("else", None, None, None, "void"))
                for s in stmt.else_branch.statements:
                    self.lower_stmt(s, f)
            f.instrs.append(HIRInstr("endif", None, None, None, "void"))
        elif isinstance(stmt, ast.WhileStmt):
            f.instrs.append(HIRInstr("while", None, None, None, "void"))
            cond = self.lower_expr(stmt.cond, f)
            f.instrs.append(HIRInstr("while.cond", None, cond, None, "bool"))
            for s in stmt.body.statements:
                self.lower_stmt(s, f)
            f.instrs.append(HIRInstr("endwhile", None, None, None, "void"))

    def lower_expr(self, expr: ast.Expr, f: HIRFunction) -> str:
        if isinstance(expr, ast.IntLiteral):
            t = self.ctx.temp()
            f.instrs.append(HIRInstr("const.i32", t, str(expr.value), None, "i32"))
            return t
        if isinstance(expr, ast.BoolLiteral):
            t = self.ctx.temp()
            f.instrs.append(HIRInstr("const.bool", t, "1" if expr.value else "0", None, "bool"))
            return t
        if isinstance(expr, ast.NameExpr):
            return expr.name
        if isinstance(expr, ast.UnaryExpr):
            r = self.lower_expr(expr.rhs, f)
            t = self.ctx.temp()
            f.instrs.append(HIRInstr(f"unary.{expr.op}", t, r, None, "i32"))
            return t
        if isinstance(expr, ast.BinaryExpr):
            l = self.lower_expr(expr.lhs, f)
            r = self.lower_expr(expr.rhs, f)
            t = self.ctx.temp()
            f.instrs.append(HIRInstr(f"bin.{expr.op}", t, l, r, expr.inferred_type or "i32"))
            return t
        if isinstance(expr, ast.CallExpr):
            for arg in expr.args:
                a = self.lower_expr(arg, f)
                f.instrs.append(HIRInstr("arg", None, a, None, "i32"))
            t = self.ctx.temp()
            f.instrs.append(HIRInstr("call", t, expr.callee, str(len(expr.args)), "i32"))
            return t
        raise NotImplementedError(type(expr).__name__)


def lower(module: ast.Module) -> HIRModule:
    return HIRLowerer().lower_module(module)

