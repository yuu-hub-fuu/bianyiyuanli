from __future__ import annotations

from nexa.ir.hir import HIRModule


def emit_llvm_ir(module: HIRModule) -> str:
    lines = ["; Nexa LLVM IR"]
    for fn in module.functions:
        params = [i.dst for i in fn.instrs if i.op == "param" and i.dst]
        param_decl = ", ".join(f"i32 %{p}" for p in params)
        lines.append(f"define i32 @{fn.name}({param_decl}) {{")
        lines.append("entry:")
        reg_map = {p: f"%{p}" for p in params}
        arg_stack: list[str] = []
        last_ret = "0"
        for ins in fn.instrs:
            if ins.op == "param":
                continue
            if ins.op == "const.i32" and ins.dst and ins.src1 is not None:
                reg_map[ins.dst] = f"%{ins.dst}"
                lines.append(f"  %{ins.dst} = add i32 0, {ins.src1}")
            elif ins.op.startswith("bin.") and ins.dst and ins.src1 and ins.src2:
                reg_map[ins.dst] = f"%{ins.dst}"
                a = reg_map.get(ins.src1, f"%{ins.src1}")
                b = reg_map.get(ins.src2, f"%{ins.src2}")
                op = ins.op[4:]
                if op in {"+", "-", "*"}:
                    m = {"+": "add", "-": "sub", "*": "mul"}[op]
                    lines.append(f"  %{ins.dst} = {m} i32 {a}, {b}")
                elif op in {"==", "!=", "<", "<=", ">", ">="}:
                    cmp = {"==": "eq", "!=": "ne", "<": "slt", "<=": "sle", ">": "sgt", ">=": "sge"}[op]
                    lines.append(f"  %cmp_{ins.dst} = icmp {cmp} i32 {a}, {b}")
                    lines.append(f"  %{ins.dst} = zext i1 %cmp_{ins.dst} to i32")
                else:
                    lines.append(f"  %{ins.dst} = add i32 {a}, {b}")
            elif ins.op == "arg" and ins.src1:
                arg_stack.append(reg_map.get(ins.src1, f"%{ins.src1}"))
            elif ins.op == "call" and ins.src1 and ins.dst:
                args = ", ".join(f"i32 {a}" for a in arg_stack)
                reg_map[ins.dst] = f"%{ins.dst}"
                lines.append(f"  %{ins.dst} = call i32 @{ins.src1}({args})")
                arg_stack.clear()
            elif ins.op.startswith("mov.") and ins.dst and ins.src1:
                reg_map[ins.dst] = reg_map.get(ins.src1, f"%{ins.src1}")
            elif ins.op == "ret":
                if ins.src1:
                    last_ret = reg_map.get(ins.src1, f"%{ins.src1}")
                lines.append(f"  ret i32 {last_ret}")
        if not any(i.op == "ret" for i in fn.instrs):
            lines.append(f"  ret i32 {last_ret}")
        lines.append("}")
    return "\n".join(lines) + "\n"


def try_emit_object(_llvm_ir: str) -> bytes:
    try:
        import llvmlite.binding as llvm  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("llvmlite not installed") from exc
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    target = llvm.Target.from_default_triple()
    tm = target.create_target_machine()
    mod = llvm.parse_assembly(_llvm_ir)
    mod.verify()
    return tm.emit_object(mod)
