from __future__ import annotations

from dataclasses import dataclass, field
import copy

from nexa.frontend import ast


@dataclass(slots=True)
class MonoCache:
    instances: dict[tuple[str, tuple[str, ...]], str] = field(default_factory=dict)


def monomorphize(module: ast.Module) -> ast.Module:
    fn_map = {f.name: f for f in module.items if isinstance(f, ast.Function) and f.generic_params}
    if not fn_map:
        return module

    cache = MonoCache()
    new_items = list(module.items)

    def walk_expr(ex: ast.Expr) -> None:
        if isinstance(ex, ast.CallExpr) and isinstance(ex.callee, ast.NameExpr):
            gfn = fn_map.get(ex.callee.name)
            if gfn:
                arg_tys = tuple((a.inferred_type or "i32") for a in ex.args)
                if all(not t.startswith("$") for t in arg_tys):
                    key = (gfn.name, arg_tys)
                    if key not in cache.instances:
                        spec_name = gfn.name + "_" + "_".join(t.replace("[", "_").replace("]", "") for t in arg_tys)
                        cache.instances[key] = spec_name
                        cloned = _clone_function(gfn, spec_name)
                        new_items.append(cloned)
                    ex.callee.name = cache.instances[key]
            for a in ex.args:
                walk_expr(a)
        elif isinstance(ex, ast.UnaryExpr) and ex.rhs:
            walk_expr(ex.rhs)
        elif isinstance(ex, ast.BinaryExpr) and ex.lhs and ex.rhs:
            walk_expr(ex.lhs); walk_expr(ex.rhs)
        elif isinstance(ex, ast.SelectExpr):
            for c in ex.cases:
                if c.channel:
                    walk_expr(c.channel)
                if c.value:
                    walk_expr(c.value)

    def walk_stmt(st: ast.Stmt) -> None:
        if isinstance(st, ast.LetStmt) and st.value:
            walk_expr(st.value)
        elif isinstance(st, ast.AssignStmt):
            walk_expr(st.value)
        elif isinstance(st, ast.ExprStmt):
            walk_expr(st.expr)
        elif isinstance(st, ast.ReturnStmt) and st.value:
            walk_expr(st.value)
        elif isinstance(st, ast.IfStmt):
            walk_expr(st.cond); [walk_stmt(s) for s in st.then_block.stmts]
            if st.else_block:
                [walk_stmt(s) for s in st.else_block.stmts]
        elif isinstance(st, ast.WhileStmt):
            walk_expr(st.cond); [walk_stmt(s) for s in st.body.stmts]
        elif isinstance(st, ast.SpawnStmt):
            walk_expr(st.expr)
        elif isinstance(st, ast.Block):
            [walk_stmt(s) for s in st.stmts]

    for item in new_items:
        if isinstance(item, ast.Function):
            for st in item.body.stmts:
                walk_stmt(st)

    module.items = new_items
    return module


def _clone_function(fn: ast.Function, new_name: str) -> ast.Function:
    # 保持教学项目实现可读性：单态化阶段只重命名并冻结 generic 参数。
    return ast.Function(fn.span, new_name, copy.deepcopy(fn.params), copy.deepcopy(fn.ret_type), copy.deepcopy(fn.body), [], {})
