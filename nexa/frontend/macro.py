from __future__ import annotations

from dataclasses import dataclass

from . import ast


@dataclass(slots=True)
class MacroEnv:
    macros: dict[str, ast.Macro]


def collect_macros(module: ast.Module) -> MacroEnv:
    return MacroEnv({m.name: m for m in module.items if isinstance(m, ast.Macro)})


def expand_module(module: ast.Module) -> ast.Module:
    env = collect_macros(module)
    items = []
    for item in module.items:
        if isinstance(item, ast.Macro):
            continue
        if isinstance(item, ast.Function):
            _expand_block(item.body, env)
        items.append(item)
    module.items = items
    return module


def _expand_block(block: ast.Block, env: MacroEnv) -> None:
    for stmt in block.stmts:
        if isinstance(stmt, ast.ExprStmt):
            _expand_expr(stmt.expr, env)
        elif isinstance(stmt, ast.LetStmt) and stmt.value:
            _expand_expr(stmt.value, env)
        elif isinstance(stmt, ast.AssignStmt):
            _expand_expr(stmt.value, env)
        elif isinstance(stmt, ast.IfStmt):
            _expand_expr(stmt.cond, env)
            _expand_block(stmt.then_block, env)
            if stmt.else_block:
                _expand_block(stmt.else_block, env)
        elif isinstance(stmt, ast.WhileStmt):
            _expand_expr(stmt.cond, env)
            _expand_block(stmt.body, env)


def _expand_expr(expr: ast.Expr, env: MacroEnv) -> None:
    if isinstance(expr, ast.CallExpr) and isinstance(expr.callee, ast.NameExpr):
        m = env.macros.get(expr.callee.name)
        if m and len(m.params) == len(expr.args):
            # teaching macro: identity expansion with hygiene placeholder
            expr.callee.name = f"__macro_expanded_{m.name}"
