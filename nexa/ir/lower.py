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
        elif isinstance(st, ast.SelectStmt):
            for c in st.cases:
                if c.kind == "recv" and c.channel:
                    ch = self._lower_expr(c.channel, hf)
                    hf.instrs.append(HIRInstr("select.recv", None, ch, None, "void"))
                elif c.kind == "send" and c.channel and c.value:
                    ch = self._lower_expr(c.channel, hf)
                    v = self._lower_expr(c.value, hf)
                    hf.instrs.append(HIRInstr("select.send", None, ch, v, "void"))
                else:
                    hf.instrs.append(HIRInstr("select.default", None, None, None, "void"))

    def _lower_expr(self, ex: ast.Expr, hf: HIRFunction) -> str:
        if isinstance(ex, ast.IntLit):
            t = self._tmp(); hf.instrs.append(HIRInstr("const.i32", t, str(ex.value), None, "i32")); return t
        if isinstance(ex, ast.BoolLit):
            t = self._tmp(); hf.instrs.append(HIRInstr("const.bool", t, "1" if ex.value else "0", None, "bool")); return t
        if isinstance(ex, ast.StrLit):
            t = self._tmp(); hf.instrs.append(HIRInstr("const.str", t, ex.value, None, "str")); return t
        if isinstance(ex, ast.NameExpr):
            return ex.name
        if isinstance(ex, ast.UnaryExpr) and ex.rhs:
            r = self._lower_expr(ex.rhs, hf)
            t = self._tmp(); hf.instrs.append(HIRInstr(f"unary.{ex.op}", t, r, None, ex.inferred_type or "i32")); return t
        if isinstance(ex, ast.BinaryExpr) and ex.lhs and ex.rhs:
            l = self._lower_expr(ex.lhs, hf); r = self._lower_expr(ex.rhs, hf)
            t = self._tmp(); hf.instrs.append(HIRInstr(f"bin.{ex.op}", t, l, r, ex.inferred_type or "i32")); return t
        if isinstance(ex, ast.CallExpr) and isinstance(ex.callee, ast.NameExpr):
            args = [self._lower_expr(a, hf) for a in ex.args]
            for a in args:
                hf.instrs.append(HIRInstr("arg", None, a, None, "void"))
            t = self._tmp(); hf.instrs.append(HIRInstr("call", t, ex.callee.name, str(len(args)), ex.inferred_type or "i32")); return t
        t = self._tmp(); hf.instrs.append(HIRInstr("const.i32", t, "0", None, "i32")); return t


def hir_to_mir(hir: HIRModule) -> MIRModule:
    out = MIRModule()
    for fn in hir.functions:
        mf = MIRFunction(fn.name)
        cur = BasicBlock("entry")
        mf.blocks[cur.label] = cur
        mf.order.append(cur.label)
        for h in fn.instrs:
            if h.op == "label" and h.dst:
                if h.dst not in mf.blocks:
                    mf.blocks[h.dst] = BasicBlock(h.dst)
                    mf.order.append(h.dst)
                cur = mf.blocks[h.dst]
                continue
            args = [x for x in (h.src1, h.src2) if x is not None]
            cur.instrs.append(MIRInstr(h.op, args, h.dst))
            if h.op == "jmp" and h.dst:
                cur.succs.add(h.dst)
                mf.blocks.setdefault(h.dst, BasicBlock(h.dst)).preds.add(cur.label)
            if h.op == "br.true" and h.dst:
                cur.succs.add(h.dst)
                mf.blocks.setdefault(h.dst, BasicBlock(h.dst)).preds.add(cur.label)
        out.functions.append(mf)
    return out
