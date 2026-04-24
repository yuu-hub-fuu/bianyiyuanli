from __future__ import annotations

from nexa.backend.regalloc import AllocResult
from nexa.ir.mir import MIRFunction


class X64Emitter:
    def emit_function(self, fn: MIRFunction, alloc: AllocResult) -> str:
        lines = [f"{fn.name}:", "  push rbp", "  mov rbp, rsp"]
        for block in fn.blocks:
            lines.append(f".{block.label}:")
            for ins in block.instrs:
                lines.extend(self.emit_instr(ins.op, ins.dst, ins.src1, ins.src2, alloc))
        lines.extend(["  mov rsp, rbp", "  pop rbp", "  ret"])
        return "\n".join(lines)

    def reg(self, name: str | None, alloc: AllocResult) -> str:
        if not name:
            return "0"
        mapped = alloc.mapping.get(name)
        if mapped is None:
            return f"[spill_{name}]"
        return mapped

    def emit_instr(self, op: str, dst: str | None, src1: str | None, src2: str | None, alloc: AllocResult) -> list[str]:
        if op == "const.i32" and dst and src1:
            return [f"  mov {self.reg(dst, alloc)}, {src1}"]
        if op == "mov" and dst and src1:
            return [f"  mov {self.reg(dst, alloc)}, {self.reg(src1, alloc)}"]
        if op == "bin.+" and dst and src1 and src2:
            rd = self.reg(dst, alloc)
            return [f"  mov {rd}, {self.reg(src1, alloc)}", f"  add {rd}, {self.reg(src2, alloc)}"]
        if op == "ret":
            if src1:
                return [f"  mov eax, {self.reg(src1, alloc)}"]
            return ["  mov eax, 0"]
        return [f"  ; {op} {dst} {src1} {src2}"]


def emit_asm(fn: MIRFunction, alloc: AllocResult) -> str:
    return X64Emitter().emit_function(fn, alloc)

