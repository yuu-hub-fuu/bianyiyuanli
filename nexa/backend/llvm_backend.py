from __future__ import annotations

from nexa.ir.hir import HIRModule


def emit_llvm_ir(module: HIRModule) -> str:
    lines = ["; Nexa LLVM IR (teaching backend)"]
    for fn in module.functions:
        lines.append(f"define i32 @{fn.name}() {{")
        lines.append("entry:")
        for ins in fn.instrs:
            if ins.op == "const.i32" and ins.dst and ins.src1 is not None:
                lines.append(f"  %{ins.dst} = add i32 0, {ins.src1}")
            elif ins.op.startswith("bin.") and ins.dst and ins.src1 and ins.src2:
                op = ins.op[4:]
                m = {"+": "add", "-": "sub", "*": "mul"}.get(op, "add")
                lines.append(f"  %{ins.dst} = {m} i32 %{ins.src1}, %{ins.src2}")
            elif ins.op == "ret":
                if ins.src1:
                    lines.append(f"  ret i32 %{ins.src1}")
                else:
                    lines.append("  ret i32 0")
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
