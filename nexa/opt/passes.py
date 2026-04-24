from __future__ import annotations

from nexa.ir.hir import HIRFunction, HIRInstr, HIRModule


def const_fold(fn: HIRFunction) -> None:
    values: dict[str, int] = {}
    out: list[HIRInstr] = []
    for ins in fn.instrs:
        if ins.op == "const.i32" and ins.dst and ins.src1 is not None:
            values[ins.dst] = int(ins.src1)
            out.append(ins)
        elif ins.op.startswith("bin.") and ins.dst and ins.src1 in values and ins.src2 in values:
            a, b = values[ins.src1], values[ins.src2]
            op = ins.op[4:]
            if op == "+":
                c = a + b
            elif op == "-":
                c = a - b
            elif op == "*":
                c = a * b
            elif op == "/" and b != 0:
                c = a // b
            else:
                out.append(ins); continue
            values[ins.dst] = c
            out.append(HIRInstr("const.i32", ins.dst, str(c), None, "i32"))
        else:
            out.append(ins)
    fn.instrs = out


def dce(fn: HIRFunction) -> None:
    used: set[str] = set()
    for ins in fn.instrs:
        if ins.src1 and ins.src1.startswith("t"):
            used.add(ins.src1)
        if ins.src2 and ins.src2.startswith("t"):
            used.add(ins.src2)
    fn.instrs = [i for i in fn.instrs if not (i.dst and i.dst.startswith("t") and i.dst not in used and i.op.startswith("const."))]


def run_optimizations(mod: HIRModule) -> HIRModule:
    for fn in mod.functions:
        const_fold(fn)
        dce(fn)
    return mod
