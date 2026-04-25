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
                        spec_name = gfn.name + "__" + "__".join(t.replace("[", "_").replace("]", "") for t in arg_tys)
                        cache.instances[key] = spec_name
                        new_items.append(_clone_function(gfn, spec_name, arg_tys))
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

    for item in list(new_items):
        if isinstance(item, ast.Function):
            for st in item.body.stmts:
                walk_stmt(st)

    module.items = new_items
    return module


def _clone_function(fn: ast.Function, new_name: str, arg_types: tuple[str, ...]) -> ast.Function:
    cloned = ast.Function(fn.span, new_name, copy.deepcopy(fn.params), copy.deepcopy(fn.ret_type), copy.deepcopy(fn.body), [], {})
    subst = {gp: arg_types[idx] for idx, gp in enumerate(fn.generic_params) if idx < len(arg_types)}

    def apply_typeref(t: ast.TypeRef) -> ast.TypeRef:
        if t.name in subst:
            return ast.TypeRef(t.span, subst[t.name], [])
        return ast.TypeRef(t.span, t.name, [apply_typeref(p) for p in t.params])

    cloned.params = [ast.Param(p.span, p.name, apply_typeref(p.type_ref)) for p in cloned.params]
    cloned.ret_type = apply_typeref(cloned.ret_type)
    return cloned
