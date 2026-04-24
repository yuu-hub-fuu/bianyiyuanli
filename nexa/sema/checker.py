from __future__ import annotations

from dataclasses import dataclass

from nexa.frontend import ast
from nexa.frontend.diagnostics import DiagnosticBag
from .symbols import ScopeStack, Symbol
from .types import BOOL, BUILTINS, I32, STR, Type, VOID, channel


@dataclass(slots=True)
class SemanticResult:
    module: ast.Module
    symbols: ScopeStack


class Checker:
    def __init__(self, diagnostics: DiagnosticBag | None = None) -> None:
        self.diag = diagnostics or DiagnosticBag()
        self.scopes = ScopeStack()
        self.functions: dict[str, tuple[list[Type], Type]] = {
            "print": ([I32], VOID),
            "panic": ([STR], VOID),
            "chan": ([I32], channel(I32)),
            "send": ([channel(I32), I32], VOID),
            "recv": ([channel(I32)], I32),
        }

    def analyze(self, module: ast.Module) -> SemanticResult:
        for item in module.items:
            if isinstance(item, ast.Function):
                ptys = [self._resolve_type(p.type_ref) for p in item.params]
                rty = self._resolve_type(item.ret_type)
                self.functions[item.name] = (ptys, rty)
        for item in module.items:
            if isinstance(item, ast.Function):
                self._check_function(item)
        return SemanticResult(module, self.scopes)

    def _check_function(self, fn: ast.Function) -> None:
        self.scopes.push()
        for p in fn.params:
            ty = self._resolve_type(p.type_ref)
            ok = self.scopes.declare(Symbol(p.name, "param", ty, self.scopes.scope_id))
            if not ok:
                self.diag.error(p.span, f"重复参数名: {p.name}")
        expected = self._resolve_type(fn.ret_type)
        self._check_block(fn.body, expected)
        self.scopes.pop()

    def _check_block(self, block: ast.Block, ret_ty: Type) -> None:
        self.scopes.push()
        for stmt in block.stmts:
            self._check_stmt(stmt, ret_ty)
        self.scopes.pop()

    def _check_stmt(self, stmt: ast.Stmt, ret_ty: Type) -> None:
        if isinstance(stmt, ast.LetStmt):
            val_ty = self._check_expr(stmt.value) if stmt.value else None
            ann = self._resolve_type(stmt.type_ref) if stmt.type_ref else val_ty
            if ann is None:
                self.diag.error(stmt.span, f"变量 {stmt.name} 缺少类型信息")
                ann = I32
            if val_ty is not None and ann != val_ty:
                self.diag.error(stmt.span, f"类型不匹配: {ann} <- {val_ty}")
            if not self.scopes.declare(Symbol(stmt.name, "var", ann, self.scopes.scope_id)):
                self.diag.error(stmt.span, f"重复声明: {stmt.name}")
        elif isinstance(stmt, ast.AssignStmt):
            sym = self.scopes.lookup(stmt.target.name)
            if sym is None:
                self.diag.error(stmt.span, f"未声明变量: {stmt.target.name}")
                return
            rhs = self._check_expr(stmt.value)
            if rhs != sym.ty:
                self.diag.error(stmt.span, f"赋值类型不匹配: {sym.ty} <- {rhs}")
        elif isinstance(stmt, ast.ExprStmt):
            self._check_expr(stmt.expr)
        elif isinstance(stmt, ast.ReturnStmt):
            got = VOID if stmt.value is None else self._check_expr(stmt.value)
            if got != ret_ty:
                self.diag.error(stmt.span, f"返回类型不匹配: 期望 {ret_ty}, 实际 {got}")
        elif isinstance(stmt, ast.IfStmt):
            cty = self._check_expr(stmt.cond)
            if cty != BOOL:
                self.diag.error(stmt.cond.span, "if 条件必须是 bool")
            self._check_block(stmt.then_block, ret_ty)
            if stmt.else_block:
                self._check_block(stmt.else_block, ret_ty)
        elif isinstance(stmt, ast.WhileStmt):
            cty = self._check_expr(stmt.cond)
            if cty != BOOL:
                self.diag.error(stmt.cond.span, "while 条件必须是 bool")
            self._check_block(stmt.body, ret_ty)
        elif isinstance(stmt, ast.Block):
            self._check_block(stmt, ret_ty)
        elif isinstance(stmt, ast.SpawnStmt):
            self._check_expr(stmt.expr)
        elif isinstance(stmt, ast.SelectStmt):
            for c in stmt.cases:
                if c.channel:
                    self._check_expr(c.channel)
                if c.value:
                    self._check_expr(c.value)
                self._check_block(c.body, ret_ty)

    def _check_expr(self, expr: ast.Expr | None) -> Type:
        if expr is None:
            return VOID
        if isinstance(expr, ast.IntLit):
            expr.inferred_type = str(I32)
            return I32
        if isinstance(expr, ast.BoolLit):
            expr.inferred_type = str(BOOL)
            return BOOL
        if isinstance(expr, ast.StrLit):
            expr.inferred_type = str(STR)
            return STR
        if isinstance(expr, ast.NameExpr):
            sym = self.scopes.lookup(expr.name)
            if sym is None:
                self.diag.error(expr.span, f"未声明标识符: {expr.name}")
                expr.inferred_type = str(I32)
                return I32
            expr.inferred_type = str(sym.ty)
            return sym.ty
        if isinstance(expr, ast.UnaryExpr):
            rhs = self._check_expr(expr.rhs)
            if expr.op == "!":
                if rhs != BOOL:
                    self.diag.error(expr.span, "! 运算需要 bool")
                expr.inferred_type = str(BOOL)
                return BOOL
            if expr.op == "-":
                if rhs != I32:
                    self.diag.error(expr.span, "负号运算需要 i32")
                expr.inferred_type = str(I32)
                return I32
        if isinstance(expr, ast.BinaryExpr):
            lt = self._check_expr(expr.lhs)
            rt = self._check_expr(expr.rhs)
            if expr.op in {"+", "-", "*", "/", "%"}:
                if lt != I32 or rt != I32:
                    self.diag.error(expr.span, "算术运算要求 i32")
                expr.inferred_type = str(I32)
                return I32
            if expr.op in {"==", "!=", "<", "<=", ">", ">="}:
                if lt != rt:
                    self.diag.error(expr.span, "比较两侧类型必须一致")
                expr.inferred_type = str(BOOL)
                return BOOL
            if expr.op in {"&&", "||"}:
                if lt != BOOL or rt != BOOL:
                    self.diag.error(expr.span, "逻辑运算要求 bool")
                expr.inferred_type = str(BOOL)
                return BOOL
        if isinstance(expr, ast.CallExpr):
            if not isinstance(expr.callee, ast.NameExpr):
                self.diag.error(expr.span, "只支持直接函数调用")
                expr.inferred_type = str(I32)
                return I32
            callee = expr.callee.name
            sig = self.functions.get(callee)
            if sig is None:
                self.diag.error(expr.span, f"未定义函数: {callee}")
                expr.inferred_type = str(I32)
                return I32
            params, ret = sig
            if len(params) != len(expr.args):
                self.diag.error(expr.span, f"参数数量不匹配: 期望 {len(params)}")
            for i, arg in enumerate(expr.args):
                aty = self._check_expr(arg)
                if i < len(params) and aty != params[i]:
                    self.diag.error(arg.span, f"参数类型不匹配: 期望 {params[i]}, 实际 {aty}")
            expr.inferred_type = str(ret)
            return ret
        self.diag.error(expr.span, "不支持的表达式")
        return I32

    def _resolve_type(self, tref: ast.TypeRef | None) -> Type:
        if tref is None:
            return VOID
        if tref.name == "Chan" and tref.params:
            return channel(self._resolve_type(tref.params[0]))
        return BUILTINS.get(tref.name, Type(tref.name))
