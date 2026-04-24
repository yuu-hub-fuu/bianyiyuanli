from __future__ import annotations

from nexa.ir.hir import HIRInstr, HIRModule


class ConstantFolder:
    def run(self, module: HIRModule) -> None:
        for fn in module.functions:
            consts: dict[str, int] = {}
            for ins in fn.instrs:
                if ins.op == "const.i32" and ins.dst and ins.src1 is not None:
                    consts[ins.dst] = int(ins.src1)
                elif ins.op == "bin.+" and ins.dst and ins.src1 in consts and ins.src2 in consts:
                    val = consts[ins.src1] + consts[ins.src2]
                    ins.op = "const.i32"
                    ins.src1 = str(val)
                    ins.src2 = None
                    consts[ins.dst] = val


class DeadCodeElim:
    def run(self, module: HIRModule) -> None:
        for fn in module.functions:
            live: set[str] = set()
            for ins in reversed(fn.instrs):
                if ins.op in {"ret", "arg", "call", "if", "while", "while.cond"}:
                    if ins.src1:
                        live.add(ins.src1)
                    if ins.src2:
                        live.add(ins.src2)
            pruned: list[HIRInstr] = []
            for ins in fn.instrs:
                if ins.dst and ins.dst.startswith("t") and ins.dst not in live and ins.op.startswith("const"):
                    continue
                pruned.append(ins)
            fn.instrs = pruned


def run_passes(module: HIRModule) -> HIRModule:
    ConstantFolder().run(module)
    DeadCodeElim().run(module)
    return module

