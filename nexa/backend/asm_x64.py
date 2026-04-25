from __future__ import annotations

from nexa.ir.mir import MIRFunction

ARG_REGS = ["rdi", "rsi", "rdx", "rcx", "r8", "r9"]


def _loc(name: str, alloc: dict[str, str | None], slots: dict[str, int]) -> str:
    reg = alloc.get(name)
    if reg:
        return reg
    if name not in slots:
        slots[name] = 8 * (len(slots) + 1)
    return f"qword [rbp-{slots[name]}]"


def emit_function(fn: MIRFunction, alloc: dict[str, str | None]) -> str:
    lines = [f"global {fn.name}", f"{fn.name}:", "  push rbp", "  mov rbp, rsp", "  sub rsp, 256"]
    slots: dict[str, int] = {}
    arg_buf: list[str] = []
    param_idx = 0

    for label in fn.order:
        block = fn.blocks.get(label)
        if block is None:
            continue
        lines.append(f"{label}:")
        for ins in block.instrs:
            if ins.op == "param" and ins.dst:
                src = ARG_REGS[param_idx] if param_idx < len(ARG_REGS) else f"qword [rbp+{16 + 8*(param_idx-len(ARG_REGS))}]"
                lines.append(f"  mov {_loc(ins.dst, alloc, slots)}, {src}")
                param_idx += 1
            elif ins.op == "arg" and ins.args:
                arg_buf.append(ins.args[0])
            elif ins.op in {"call", "call.recv", "call.send", "call.select_recv"}:
                callee = ins.args[0] if ins.args else ""
                if ins.op == "call.recv":
                    callee = "rt_chan_recv"
                    arg_buf = [ins.args[0]] if ins.args else []
                elif ins.op == "call.send":
                    callee = "rt_chan_send"
                    arg_buf = [ins.args[0], ins.args[1]] if len(ins.args) > 1 else arg_buf
                elif ins.op == "call.select_recv":
                    callee = "rt_select_recv"
                    arg_buf = [ins.args[0], ins.args[1]] if len(ins.args) > 1 else arg_buf
                for idx, a in enumerate(arg_buf):
                    if idx < len(ARG_REGS):
                        lines.append(f"  mov {ARG_REGS[idx]}, {_loc(a, alloc, slots)}")
                if callee == "send":
                    callee = "rt_chan_send"
                elif callee == "recv":
                    callee = "rt_chan_recv"
                lines.append(f"  call {callee}")
                if ins.dst:
                    lines.append(f"  mov {_loc(ins.dst, alloc, slots)}, rax")
                arg_buf.clear()
            elif ins.op == "const.i32" and ins.dst and ins.args:
                lines.append(f"  mov {_loc(ins.dst, alloc, slots)}, {ins.args[0]}")
            elif ins.op == "const.bool" and ins.dst and ins.args:
                lines.append(f"  mov {_loc(ins.dst, alloc, slots)}, {ins.args[0]}")
            elif ins.op.startswith("bin.") and ins.dst and len(ins.args) == 2:
                op = ins.op[4:]
                dst = _loc(ins.dst, alloc, slots)
                a = _loc(ins.args[0], alloc, slots)
                b = _loc(ins.args[1], alloc, slots)
                lines.append(f"  mov rax, {a}")
                if op in {"+", "-", "*"}:
                    m = {"+": "add", "-": "sub", "*": "imul"}[op]
                    lines.append(f"  {m} rax, {b}")
                elif op == "/":
                    lines.append("  cqo")
                    lines.append(f"  idiv {b}")
                elif op in {"==", "!=", "<", "<=", ">", ">="}:
                    lines.append(f"  cmp rax, {b}")
                    setop = {"==": "sete", "!=": "setne", "<": "setl", "<=": "setle", ">": "setg", ">=": "setge"}[op]
                    lines.append(f"  {setop} al")
                    lines.append("  movzx rax, al")
                lines.append(f"  mov {dst}, rax")
            elif ins.op.startswith("unary.") and ins.dst and ins.args:
                dst = _loc(ins.dst, alloc, slots)
                src = _loc(ins.args[0], alloc, slots)
                lines.append(f"  mov rax, {src}")
                if ins.op.endswith("-"):
                    lines.append("  neg rax")
                else:
                    lines.extend(["  cmp rax, 0", "  sete al", "  movzx rax, al"])
                lines.append(f"  mov {dst}, rax")
            elif ins.op.startswith("mov.") and ins.dst and ins.args:
                lines.append(f"  mov {_loc(ins.dst, alloc, slots)}, {_loc(ins.args[0], alloc, slots)}")
            elif ins.op == "ret":
                if ins.args:
                    lines.append(f"  mov rax, {_loc(ins.args[0], alloc, slots)}")
                lines.extend(["  leave", "  ret"])
            elif ins.op == "jmp" and ins.dst:
                lines.append(f"  jmp {ins.dst}")
            elif ins.op == "br.true" and ins.dst and ins.args:
                lines.append(f"  cmp {_loc(ins.args[0], alloc, slots)}, 0")
                lines.append(f"  jne {ins.dst}")
            elif ins.op == "br.ready" and ins.dst and ins.args:
                lines.append(f"  mov rdi, {_loc(ins.args[0], alloc, slots)}")
                lines.append("  call rt_chan_ready")
                lines.append("  cmp rax, 0")
                lines.append(f"  jne {ins.dst}")
    return "\n".join(lines) + "\n"
