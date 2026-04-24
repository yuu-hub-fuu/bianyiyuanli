from __future__ import annotations


def emit_object(llvm_ir: str) -> bytes:
    try:
        import llvmlite.binding as llvm  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError("llvmlite not installed, install with pip install .[llvm]") from exc

    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    target = llvm.Target.from_default_triple()
    tm = target.create_target_machine()
    mod = llvm.parse_assembly(llvm_ir)
    mod.verify()
    return tm.emit_object(mod)

