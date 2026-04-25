from __future__ import annotations

from nexa.ir.hir import HIRKind, HIRModule


_UNSUPPORTED = {
    HIRKind.LABEL,
    HIRKind.JUMP,
    HIRKind.BRANCH_TRUE,
    HIRKind.BRANCH_READY,
    HIRKind.SELECT,
}


def validate_llvm_subset(module: HIRModule) -> tuple[bool, str]:
    for fn in module.functions:
        for ins in fn.instrs:
            if ins.kind in _UNSUPPORTED:
                return False, f"LLVM backend rejects control-flow instruction: {ins.kind.name}"
            if ins.kind == HIRKind.CONST and ins.ty in {"str", "Chan"}:
                return False, f"LLVM backend rejects const type: {ins.ty}"
            if ins.kind == HIRKind.CALL and (ins.op in {"recv", "send", "select_recv", "chan"}):
                return False, f"LLVM backend rejects runtime intrinsic call: {ins.op}"
    return True, ""


def emit_llvm_ir(module: HIRModule) -> str:
    lines = ["; Nexa LLVM IR"]
    for fn in module.functions:
        params = [i.dst for i in fn.instrs if i.kind == HIRKind.PARAM and i.dst]
        param_decl = ", ".join(f"i32 %{p}" for p in params)
        lines.append(f"define i32 @{fn.name}({param_decl}) {{")
        lines.append("entry:")
        reg_map = {p: f"%{p}" for p in params}
        arg_stack: list[str] = []
        last_ret = "0"
        for ins in fn.instrs:
            if ins.kind == HIRKind.PARAM:
                continue
            if ins.kind == HIRKind.CONST and ins.ty == "i32" and ins.dst and ins.args:
                reg_map[ins.dst] = f"%{ins.dst}"
                lines.append(f"  %{ins.dst} = add i32 0, {ins.args[0]}")
            elif ins.kind == HIRKind.BIN and ins.dst and len(ins.args) == 2:
                reg_map[ins.dst] = f"%{ins.dst}"
                a = reg_map.get(ins.args[0], f"%{ins.args[0]}")
                b = reg_map.get(ins.args[1], f"%{ins.args[1]}")
                op = ins.op or "+"
                if op in {"+", "-", "*"}:
                    m = {"+": "add", "-": "sub", "*": "mul"}[op]
                    lines.append(f"  %{ins.dst} = {m} i32 {a}, {b}")
                elif op in {"==", "!=", "<", "<=", ">", ">="}:
                    cmp = {"==": "eq", "!=": "ne", "<": "slt", "<=": "sle", ">": "sgt", ">=": "sge"}[op]
                    lines.append(f"  %cmp_{ins.dst} = icmp {cmp} i32 {a}, {b}")
                    lines.append(f"  %{ins.dst} = zext i1 %cmp_{ins.dst} to i32")
            elif ins.kind == HIRKind.ARG and ins.args:
                arg_stack.append(reg_map.get(ins.args[0], f"%{ins.args[0]}"))
            elif ins.kind == HIRKind.CALL and ins.op and ins.dst:
                args = ", ".join(f"i32 {a}" for a in arg_stack)
                reg_map[ins.dst] = f"%{ins.dst}"
                lines.append(f"  %{ins.dst} = call i32 @{ins.op}({args})")
                arg_stack.clear()
            elif ins.kind == HIRKind.MOVE and ins.dst and ins.args:
                reg_map[ins.dst] = reg_map.get(ins.args[0], f"%{ins.args[0]}")
            elif ins.kind == HIRKind.RET:
                if ins.args:
                    last_ret = reg_map.get(ins.args[0], f"%{ins.args[0]}")
                lines.append(f"  ret i32 {last_ret}")
        if not any(i.kind == HIRKind.RET for i in fn.instrs):
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
