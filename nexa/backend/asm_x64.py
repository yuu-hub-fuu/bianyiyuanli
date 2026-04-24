from __future__ import annotations

from nexa.ir.mir import MIRFunction


def _loc(name: str, alloc: dict[str, str | None], slots: dict[str, int]) -> str:
    reg = alloc.get(name)
    if reg:
        return reg
    if name not in slots:
        slots[name] = 8 * (len(slots) + 1)
    return f"[rbp-{slots[name]}]"


def emit_function(fn: MIRFunction, alloc: dict[str, str | None]) -> str:
    lines = [f"global {fn.name}", f"{fn.name}:", "  push rbp", "  mov rbp, rsp"]
    slots: dict[str, int] = {}
    for label in fn.order:
        lines.append(f"{label}:")
        for ins in fn.blocks[label].instrs:
            if ins.op == "const.i32" and ins.dst and ins.args:
                lines.append(f"  mov {_loc(ins.dst, alloc, slots)}, {ins.args[0]}")
            elif ins.op.startswith("bin.") and ins.dst and len(ins.args) == 2:
                op = ins.op[4:]
                dst = _loc(ins.dst, alloc, slots)
                a = _loc(ins.args[0], alloc, slots)
                b = _loc(ins.args[1], alloc, slots)
                lines.append(f"  mov rax, {a}")
                m = {"+": "add", "-": "sub", "*": "imul"}.get(op)
                if m:
                    lines.append(f"  {m} rax, {b}")
                    lines.append(f"  mov {dst}, rax")
            elif ins.op == "mov.i32" and ins.dst and ins.args:
                lines.append(f"  mov {_loc(ins.dst, alloc, slots)}, {_loc(ins.args[0], alloc, slots)}")
            elif ins.op == "ret":
                if ins.args:
                    lines.append(f"  mov eax, {_loc(ins.args[0], alloc, slots)}")
                lines.extend(["  leave", "  ret"])
            elif ins.op == "jmp" and ins.dst:
                lines.append(f"  jmp {ins.dst}")
            elif ins.op == "br.true" and ins.dst and ins.args:
                lines.append(f"  cmp {_loc(ins.args[0], alloc, slots)}, 0")
                lines.append(f"  jne {ins.dst}")
            elif ins.op == "call" and ins.dst and ins.args:
                lines.append(f"  call {ins.args[0]}")
                lines.append(f"  mov {_loc(ins.dst, alloc, slots)}, rax")
    return "\n".join(lines) + "\n"
