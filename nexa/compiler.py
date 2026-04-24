from __future__ import annotations

from dataclasses import dataclass

from nexa.backend.asm_x64 import emit_asm
from nexa.backend.regalloc import allocate
from nexa.frontend.lexer import scan
from nexa.frontend.parser import parse
from nexa.ir.lower import lower
from nexa.ir.mir import build_cfg
from nexa.opt.passes import run_passes
from nexa.sema.checker import analyze
from nexa.utils.model import CompileResult, Diagnostic


@dataclass(slots=True)
class BuildArtifacts:
    tokens: list[str]
    hir: list[str]
    asm: str


class Compiler:
    def compile(self, source: str) -> CompileResult[BuildArtifacts]:
        diagnostics: list[Diagnostic] = []

        lexed = scan(source)
        diagnostics.extend(lexed.diagnostics)
        if not lexed.ok or lexed.value is None:
            return CompileResult(None, diagnostics)

        parsed = parse(lexed.value)
        diagnostics.extend(parsed.diagnostics)
        if not parsed.ok or parsed.value is None:
            return CompileResult(None, diagnostics)

        sema = analyze(parsed.value)
        diagnostics.extend(sema.diagnostics)
        if not sema.ok or sema.value is None:
            return CompileResult(None, diagnostics)

        hir = lower(sema.value.module)
        run_passes(hir)
        mir = build_cfg(hir)
        alloc_map = allocate(mir)

        asm_parts: list[str] = []
        for fn in mir.functions:
            asm_parts.append(emit_asm(fn, alloc_map[fn.name]))

        return CompileResult(
            BuildArtifacts(
                tokens=[f"{t.kind}:{t.lexeme}" for t in lexed.value],
                hir=[f"{ins.op} {ins.dst} {ins.src1} {ins.src2} : {ins.ty}" for f in hir.functions for ins in f.instrs],
                asm="\n\n".join(asm_parts),
            ),
            diagnostics,
        )

