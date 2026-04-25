from __future__ import annotations

from nexa.frontend import ast
from .hir import HIRFunction, HIRInstr, HIRModule
from .mir import BasicBlock, MIRFunction, MIRInstr, MIRModule


class Lowerer:
    def __init__(self) -> None:
        self.temp_id = 0

    def lower_module(self, module: ast.Module) -> HIRModule:
        out = HIRModule()
        for item in module.items:
            if isinstance(item, ast.Function):
                out.functions.append(self._lower_fn(item))
        return out

    def _tmp(self) -> str:
        self.temp_id += 1
        return f"t{self.temp_id}"

    def _lower_fn(self, fn: ast.Function) -> HIRFunction:
        hf = HIRFunction(fn.name)
        for p in fn.params:
            hf.instrs.append(HIRInstr("param", p.name, None, None, p.type_ref.name))
        for st in fn.body.stmts:
            self._lower_stmt(st, hf)
        if not hf.instrs or hf.instrs[-1].op != "ret":
            hf.instrs.append(HIRInstr("ret", None, "0", None, "i32"))
        return hf

    def _lower_stmt(self, st: ast.Stmt, hf: HIRFunction) -> None:
        if isinstance(st, ast.LetStmt):
            if st.value:
                src = self._lower_expr(st.value, hf)
                ty = st.type_ref.name if st.type_ref else (st.value.inferred_type or "i32")
                hf.instrs.append(HIRInstr(f"mov.{ty}", st.name, src, None, ty))
        elif isinstance(st, ast.AssignStmt):
            src = self._lower_expr(st.value, hf)
            ty = st.value.inferred_type or "i32"
            hf.instrs.append(HIRInstr(f"mov.{ty}", st.target.name, src, None, ty))
        elif isinstance(st, ast.ExprStmt):
            self._lower_expr(st.expr, hf)
        elif isinstance(st, ast.ReturnStmt):
            if st.value:
                src = self._lower_expr(st.value, hf)
                hf.instrs.append(HIRInstr("ret", None, src, None, st.value.inferred_type or "i32"))
            else:
                hf.instrs.append(HIRInstr("ret", None, None, None, "void"))
        elif isinstance(st, ast.IfStmt):
            c = self._lower_expr(st.cond, hf)
            l_then, l_else, l_end = self._tmp(), self._tmp(), self._tmp()
            hf.instrs.append(HIRInstr("br.true", l_then, c, None, "bool"))
            hf.instrs.append(HIRInstr("jmp", l_else, None, None, "void"))
            hf.instrs.append(HIRInstr("label", l_then, None, None, "void"))
            for s in st.then_block.stmts:
                self._lower_stmt(s, hf)
            hf.instrs.append(HIRInstr("jmp", l_end, None, None, "void"))
            hf.instrs.append(HIRInstr("label", l_else, None, None, "void"))
            if st.else_block:
                for s in st.else_block.stmts:
                    self._lower_stmt(s, hf)
            hf.instrs.append(HIRInstr("jmp", l_end, None, None, "void"))
            hf.instrs.append(HIRInstr("label", l_end, None, None, "void"))
        elif isinstance(st, ast.WhileStmt):
            l_head, l_body, l_end = self._tmp(), self._tmp(), self._tmp()
            hf.instrs.append(HIRInstr("label", l_head, None, None, "void"))
            c = self._lower_expr(st.cond, hf)
            hf.instrs.append(HIRInstr("br.true", l_body, c, None, "bool"))
            hf.instrs.append(HIRInstr("jmp", l_end, None, None, "void"))
            hf.instrs.append(HIRInstr("label", l_body, None, None, "void"))
            for s in st.body.stmts:
                self._lower_stmt(s, hf)
            hf.instrs.append(HIRInstr("jmp", l_head, None, None, "void"))
            hf.instrs.append(HIRInstr("label", l_end, None, None, "void"))
        elif isinstance(st, ast.Block):
            for s in st.stmts:
                self._lower_stmt(s, hf)
        elif isinstance(st, ast.SpawnStmt):
            fn = self._lower_expr(st.expr, hf)
            hf.instrs.append(HIRInstr("spawn", None, fn, None, "void"))

    def _lower_select_expr(self, ex: ast.SelectExpr, hf: HIRFunction) -> str:
        """Lower select to runtime-subset primitives.

        Teaching/full-mode semantics:
        - select { recv(ch) => {...} default => {...} }
          lowers to call.select_recv(ch, default_val)
        - send-cases are lowered as side-effect call.send and value expression.
        """
        res = self._tmp()
        recv_case = next((c for c in ex.cases if c.kind == "recv" and c.channel), None)
        default_case = next((c for c in ex.cases if c.kind == "default"), None)

        if recv_case is not None:
            ch = self._lower_expr(recv_case.channel, hf)
            default_val = "0"
            if default_case and default_case.body.stmts:
                # support expression-stmt default like `{ 0; }`
                st = default_case.body.stmts[0]
                if isinstance(st, ast.ExprStmt):
                    default_val = self._lower_expr(st.expr, hf)
            hf.instrs.append(HIRInstr("call.select_recv", res, ch, default_val, ex.inferred_type or "i32", (ex.span.line, ex.span.col)))
            for s in recv_case.body.stmts:
                self._lower_stmt(s, hf)
        else:
            hf.instrs.append(HIRInstr("const.i32", res, "0", None, ex.inferred_type or "i32"))

        # keep send/default side effects as teaching subset
        for c in ex.cases:
            if c.kind == "send" and c.channel and c.value:
                ch = self._lower_expr(c.channel, hf)
                v = self._lower_expr(c.value, hf)
                hf.instrs.append(HIRInstr("call.send", None, ch, v, "void"))
            elif c.kind == "default" and c is not default_case:
                for s in c.body.stmts:
                    self._lower_stmt(s, hf)
        return res

    def _lower_expr(self, ex: ast.Expr, hf: HIRFunction) -> str:
        if isinstance(ex, ast.IntLit):
            t = self._tmp(); hf.instrs.append(HIRInstr("const.i32", t, str(ex.value), None, "i32", (ex.span.line, ex.span.col))); return t
        if isinstance(ex, ast.BoolLit):
            t = self._tmp(); hf.instrs.append(HIRInstr("const.bool", t, "1" if ex.value else "0", None, "bool", (ex.span.line, ex.span.col))); return t
        if isinstance(ex, ast.StrLit):
            t = self._tmp(); hf.instrs.append(HIRInstr("const.str", t, ex.value, None, "str", (ex.span.line, ex.span.col))); return t
        if isinstance(ex, ast.NameExpr):
            return ex.name
        if isinstance(ex, ast.SelectExpr):
            return self._lower_select_expr(ex, hf)
        if isinstance(ex, ast.UnaryExpr) and ex.rhs:
            r = self._lower_expr(ex.rhs, hf)
            t = self._tmp(); hf.instrs.append(HIRInstr(f"unary.{ex.op}", t, r, None, ex.inferred_type or "i32", (ex.span.line, ex.span.col))); return t
        if isinstance(ex, ast.BinaryExpr) and ex.lhs and ex.rhs:
            l = self._lower_expr(ex.lhs, hf); r = self._lower_expr(ex.rhs, hf)
            t = self._tmp(); hf.instrs.append(HIRInstr(f"bin.{ex.op}", t, l, r, ex.inferred_type or "i32", (ex.span.line, ex.span.col))); return t
        if isinstance(ex, ast.CallExpr) and isinstance(ex.callee, ast.NameExpr):
            args = [self._lower_expr(a, hf) for a in ex.args]
            for a in args:
                hf.instrs.append(HIRInstr("arg", None, a, None, "void"))
            t = self._tmp(); hf.instrs.append(HIRInstr("call", t, ex.callee.name, str(len(args)), ex.inferred_type or "i32", (ex.span.line, ex.span.col))); return t
        t = self._tmp(); hf.instrs.append(HIRInstr("const.i32", t, "0", None, "i32", (ex.span.line, ex.span.col))); return t


def hir_to_mir(hir: HIRModule) -> MIRModule:
    out = MIRModule()
    for fn in hir.functions:
        mf = MIRFunction(fn.name)
        current = BasicBlock("entry")
        mf.blocks[current.label] = current
        mf.order.append(current.label)

        def ensure_block(name: str) -> BasicBlock:
            if name not in mf.blocks:
                mf.blocks[name] = BasicBlock(name)
                mf.order.append(name)
            return mf.blocks[name]

        for h in fn.instrs:
            if h.op == "label" and h.dst:
                current = ensure_block(h.dst)
                continue

            args = [x for x in (h.src1, h.src2) if x is not None]
            mi = MIRInstr(h.op, args, h.dst)
            current.instrs.append(mi)

            if h.op == "br.true" and h.dst:
                tblock = ensure_block(h.dst)
                current.succs.add(h.dst); tblock.preds.add(current.label)
                fall = ensure_block(f"fall_{len(mf.order)}")
                current.succs.add(fall.label); fall.preds.add(current.label)
                current = fall
            elif h.op == "jmp" and h.dst:
                tblock = ensure_block(h.dst)
                current.succs.add(h.dst); tblock.preds.add(current.label)
                current = ensure_block(f"after_jmp_{len(mf.order)}")
            elif h.op == "ret":
                current = ensure_block(f"after_ret_{len(mf.order)}")

        # prune empty synthetic blocks without predecessors
        for name in list(mf.blocks.keys()):
            b = mf.blocks[name]
            if not b.instrs and not b.preds and name not in {"entry"}:
                del mf.blocks[name]
                if name in mf.order:
                    mf.order.remove(name)
        out.functions.append(mf)
    return out
