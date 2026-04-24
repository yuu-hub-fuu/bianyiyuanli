from __future__ import annotations

from dataclasses import dataclass

from nexa.backend.asm_x64 import emit_function
from nexa.backend.regalloc import compute_intervals, linear_scan
from nexa.frontend.diagnostics import Diagnostic, DiagnosticBag
from nexa.frontend.lexer import Lexer
from nexa.frontend.macro import expand_module
from nexa.frontend.parser import Parser
from nexa.ir.lower import Lowerer, hir_to_mir
from nexa.opt.passes import run_optimizations
from nexa.sema.checker import Checker
from nexa.sema.monomorphize import monomorphize


@dataclass(slots=True)
class BuildResult:
    diagnostics: list[Diagnostic]
    tokens: list[str]
    hir: list[str]
    asm: dict[str, str]


def compile_source(source: str) -> BuildResult:
    diag = DiagnosticBag()
    lexer = Lexer(source, diag)
    tokens = lexer.scan()
    parser = Parser(tokens, diag)
    module = parser.parse()
    module = expand_module(module)
    module = monomorphize(module)
    Checker(diag).analyze(module)

    hir_mod = Lowerer().lower_module(module)
    run_optimizations(hir_mod)
    mir_mod = hir_to_mir(hir_mod)

    asm: dict[str, str] = {}
    for fn in mir_mod.functions:
        alloc = linear_scan(compute_intervals(fn), ["r10", "r11", "r12", "r13", "r14", "r15"])
        asm[fn.name] = emit_function(fn, alloc)

    hir_lines = [f"{f.name}:" for f in hir_mod.functions]
    for fn in hir_mod.functions:
        for i in fn.instrs:
            hir_lines.append(f"  ({i.op}, {i.src1}, {i.src2}, {i.dst})")
    tok_lines = [f"{t.kind.name}:{t.lexeme}" for t in tokens]
    return BuildResult(diag.items, tok_lines, hir_lines, asm)
