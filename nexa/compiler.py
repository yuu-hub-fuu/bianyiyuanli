from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from nexa.backend.asm_x64 import emit_function
from nexa.backend.llvm_backend import emit_llvm_ir, validate_llvm_subset
from nexa.backend.regalloc import compute_intervals, linear_scan
from nexa.frontend import ast
from nexa.frontend.diagnostics import Diagnostic, DiagnosticBag, Level
from nexa.frontend.lexer import LexTables, Lexer
from nexa.frontend.tokens import Span
from nexa.frontend.macro import MacroExpander
from nexa.frontend.parser import Parser
from nexa.ir.lower import Lowerer, hir_to_mir
from nexa.ir.mir import MIRFunction
from nexa.opt.passes import run_optimizations
from nexa.sema.checker import Checker, SemanticResult
from nexa.sema.monomorphize import monomorphize
from nexa.vm import HIRVM, VMFrame


@dataclass(slots=True)
class StageResult:
    name: str
    status: str
    detail: str


@dataclass(slots=True)
class BuildArtifacts:
    tokens: list[str] = field(default_factory=list)
    tables: dict[str, list[str]] = field(default_factory=dict)
    ast_text: str = ""
    symbols: list[str] = field(default_factory=list)
    hir_raw: HIRModule | None = None
    hir_opt: HIRModule | None = None
    cfg: dict[str, list[str]] = field(default_factory=dict)
    asm: dict[str, str] = field(default_factory=dict)
    llvm_ir: str = ""


@dataclass(slots=True)
class BuildResult:
    diagnostics: list[Diagnostic]
    artifacts: BuildArtifacts
    timeline: list[StageResult] = field(default_factory=list)
    run_value: int | None = None
    run_stdout: list[str] = field(default_factory=list)
    vm_trace: list[VMFrame] = field(default_factory=list)


def _ast_dump(node: object, indent: int = 0) -> list[str]:
    pad = "  " * indent
    if isinstance(node, ast.Module):
        out = [f"{pad}Module"]
        for i in node.items:
            out.extend(_ast_dump(i, indent + 1))
        return out
    if isinstance(node, ast.Function):
        out = [f"{pad}Function {node.name}"]
        for p in node.params:
            out.append(f"{pad}  Param {p.name}: {p.type_ref.name}")
        out.extend(_ast_dump(node.body, indent + 1))
        return out
    if isinstance(node, ast.StructDef):
        out = [f"{pad}Struct {node.name}"]
        for f in node.fields:
            out.append(f"{pad}  Field {f.name}: {f.type_ref.name}")
        return out
    if isinstance(node, ast.Block):
        out = [f"{pad}Block"]
        for s in node.stmts:
            out.extend(_ast_dump(s, indent + 1))
        return out
    if isinstance(node, ast.LetStmt):
        return [f"{pad}Let {node.name}"]
    if isinstance(node, ast.AssignStmt):
        return [f"{pad}Assign {node.target.name}"]
    if isinstance(node, ast.ReturnStmt):
        return [f"{pad}Return"]
    if isinstance(node, ast.IfStmt):
        out = [f"{pad}If"]
        out.extend(_ast_dump(node.then_block, indent + 1))
        if node.else_block:
            out.extend(_ast_dump(node.else_block, indent + 1))
        return out
    if isinstance(node, ast.WhileStmt):
        out = [f"{pad}While"]
        out.extend(_ast_dump(node.body, indent + 1))
        return out
    if isinstance(node, ast.ExprStmt):
        return [f"{pad}ExprStmt"]
    return [f"{pad}{type(node).__name__}"]


def _hir_lines(hir_mod) -> list[str]:
    lines: list[str] = []
    if hir_mod is None:
        return lines
    for fn in hir_mod.functions:
        lines.append(f"{fn.name}:")
        for idx, i in enumerate(fn.instrs, 1):
            args = ", ".join(i.args)
            lines.append(f"  {idx:03d}: ({i.kind.name}, op={i.op}, args=[{args}], dst={i.dst}, target={i.target}, ty={i.ty}) @{i.span[0]}:{i.span[1]}")
    return lines


def _cfg_dump(fn: MIRFunction) -> list[str]:
    rows = []
    for b in fn.order:
        if b not in fn.blocks:
            continue
        blk = fn.blocks[b]
        if not blk.instrs and not blk.preds and not blk.succs and b != "entry":
            continue
        rows.append(f"[{b}] preds={sorted(blk.preds)} succs={sorted(blk.succs)}")
        for i in blk.instrs:
            rows.append(f"  {i.op} {i.args} -> {i.dst}")
    return rows


def _suggestions(diag: DiagnosticBag) -> None:
    for d in diag.items:
        if "缺少分号" in d.message and not d.fixits:
            d.fixits.append("在此处插入 ';'")
        if "未声明" in d.message and not d.fixits:
            d.fixits.append("先使用 let 声明该变量")
def compile_source(
    source: str,
    mode: str = "full",
    export_dir: str | None = None,
    run: bool = False,
    trace: bool = False,
) -> BuildResult:
    diag = DiagnosticBag()
    timeline: list[StageResult] = []
    artifacts = BuildArtifacts()

    def stage(name: str, status: str, detail: str) -> None:
        timeline.append(StageResult(name, status, detail))

    lexer = Lexer(source, diag)
    tokens = lexer.scan()
    artifacts.tokens = [f"{t.kind.name}:{t.lexeme}" for t in tokens]
    stage("Lexer", "failed" if diag.has_errors() else "ok", f"tokens={len(tokens)}")
    if diag.has_errors():
        stage("Parser", "skipped", "blocked by lexer errors")
        stage("MacroExpand", "skipped", "blocked")
        stage("Sema", "skipped", "blocked")
        stage("Monomorphize", "skipped", "blocked")
        stage("Sema(redo)", "skipped", "blocked")
        stage("HIR", "skipped", "blocked")
        stage("Optimize", "skipped", "blocked")
        stage("MIR", "skipped", "blocked")
        stage("RegAlloc", "skipped", "blocked")
        stage("Backend", "skipped", "blocked")
        _suggestions(diag)
        return BuildResult(diagnostics=diag.items, artifacts=artifacts, timeline=timeline)

    parser = Parser(tokens, diag)
    module = parser.parse()
    artifacts.ast_text = "\n".join(_ast_dump(module))
    stage("Parser", "failed" if diag.has_errors() else "ok", f"items={len(module.items)}")
    if diag.has_errors():
        stage("MacroExpand", "skipped", "blocked by parser errors")
        stage("Sema", "skipped", "blocked")
        stage("Monomorphize", "skipped", "blocked")
        stage("Sema(redo)", "skipped", "blocked")
        stage("HIR", "skipped", "blocked")
        stage("Optimize", "skipped", "blocked")
        stage("MIR", "skipped", "blocked")
        stage("RegAlloc", "skipped", "blocked")
        stage("Backend", "skipped", "blocked")
        _suggestions(diag)
        return BuildResult(diagnostics=diag.items, artifacts=artifacts, timeline=timeline)

    if mode == "full":
        module = MacroExpander(diag).expand_module(module)
    stage("MacroExpand", "failed" if diag.has_errors() else "ok", "enabled" if mode == "full" else "core-mode disabled")
    artifacts.ast_text = "\n".join(_ast_dump(module))

    sema_pre: SemanticResult = Checker(diag, mode=mode).analyze(module)
    stage("Sema", "failed" if diag.has_errors() else "ok", f"symbols={len(sema_pre.symbols.history)}")
    if diag.has_errors():
        stage("Monomorphize", "skipped", "blocked by sema errors")
        stage("Sema(redo)", "skipped", "blocked")
        stage("HIR", "skipped", "blocked")
        stage("Optimize", "skipped", "blocked")
        stage("MIR", "skipped", "blocked")
        stage("RegAlloc", "skipped", "blocked")
        stage("Backend", "skipped", "blocked")
        artifacts.tables = _format_tables(lexer.tables, sema_pre, [])
        artifacts.symbols = [f"{n:<12} {c:<8} {t:<12} scope={sid} slot={slot}" for n, c, t, sid, slot in sema_pre.symbols.dump_rows()]
        _suggestions(diag)
        return BuildResult(diagnostics=diag.items, artifacts=artifacts, timeline=timeline)

    if mode == "full":
        module = monomorphize(module, sema_pre.generic_calls)
    stage("Monomorphize", "failed" if diag.has_errors() else "ok", "enabled" if mode == "full" else "core-mode disabled")

    # Re-run semantic analysis after monomorphization so cloned functions get proper concrete typing.
    sema: SemanticResult = Checker(diag, mode=mode).analyze(module)
    stage("Sema(redo)", "failed" if diag.has_errors() else "ok", f"symbols={len(sema.symbols.history)}")
    if diag.has_errors():
        stage("HIR", "skipped", "blocked by sema errors")
        stage("Optimize", "skipped", "blocked")
        stage("MIR", "skipped", "blocked")
        stage("RegAlloc", "skipped", "blocked")
        stage("Backend", "skipped", "blocked")
        artifacts.tables = _format_tables(lexer.tables, sema, [])
        artifacts.symbols = [f"{n:<12} {c:<8} {t:<12} scope={sid} slot={slot}" for n, c, t, sid, slot in sema.symbols.dump_rows()]
        _suggestions(diag)
        return BuildResult(diagnostics=diag.items, artifacts=artifacts, timeline=timeline)

    lowerer = Lowerer()
    hir_raw_mod = lowerer.lower_module(module)
    hir_raw_lines = _hir_lines(hir_raw_mod)
    artifacts.hir_raw = hir_raw_mod
    stage("HIR", "ok", f"instrs={sum(len(f.instrs) for f in hir_raw_mod.functions)}")

    hir_opt_mod = run_optimizations(hir_raw_mod)
    hir_opt_lines = _hir_lines(hir_opt_mod)
    artifacts.hir_opt = hir_opt_mod
    stage("Optimize", "ok", "const-fold + dce")

    ok_llvm, llvm_msg = validate_llvm_subset(hir_opt_mod)
    llvm_ir = emit_llvm_ir(hir_opt_mod) if ok_llvm else ""
    if not ok_llvm:
        diag.warn(Span(0, 0, 1, 1), llvm_msg)
    mir_mod = hir_to_mir(hir_opt_mod)
    stage("MIR", "ok", f"functions={len(mir_mod.functions)}")

    asm: dict[str, str] = {}
    cfg_dump: dict[str, list[str]] = {}
    for fn in mir_mod.functions:
        intervals = compute_intervals(fn)
        alloc = linear_scan(intervals, ["r10", "r11", "r12", "r13", "r14", "r15"])
        asm[fn.name] = emit_function(fn, alloc)
        cfg_dump[fn.name] = _cfg_dump(fn)
    stage("RegAlloc", "ok", "linear-scan")
    stage("Backend", "warning" if not ok_llvm else "ok", f"asm-fns={len(asm)}")

    _suggestions(diag)

    artifacts.tables = _format_tables(lexer.tables, sema, hir_opt_lines)
    artifacts.tables["hir_raw"] = hir_raw_lines
    artifacts.tables["hir_opt"] = hir_opt_lines
    artifacts.symbols = [f"{n:<12} {c:<8} {t:<12} scope={sid} slot={slot}" for n, c, t, sid, slot in sema.symbols.dump_rows()]
    artifacts.cfg = cfg_dump
    artifacts.asm = asm
    artifacts.llvm_ir = llvm_ir

    run_value = None
    run_stdout: list[str] = []
    vm_trace: list[VMFrame] = []
    if run and not diag.has_errors():
        try:
            vm = HIRVM(hir_opt_mod)
            if trace:
                vm_res, vm_trace = vm.run_with_trace("main")
            else:
                vm_res = vm.run("main")
            run_value = vm_res.return_value
            run_stdout = vm_res.stdout
        except Exception as exc:  # noqa: BLE001
            run_stdout = [f"runtime error: {exc}"]
            diag.add(Level.ERROR, Span(0, 0, 1, 1), f"运行时错误: {exc}")

    if export_dir:
        _export_graphs(module, mir_mod, export_dir)

    return BuildResult(
        diagnostics=diag.items,
        artifacts=artifacts,
        timeline=timeline,
        run_value=run_value,
        run_stdout=run_stdout,
        vm_trace=vm_trace,
    )


def _format_tables(lt: LexTables, sema: SemanticResult, hir_lines: list[str]) -> dict[str, list[str]]:
    quads = [ln.strip() for ln in hir_lines if "(" in ln and ")" in ln]
    return {
        "keywords": sorted(lt.keyword_table),
        "delimiters": sorted(lt.delimiter_table),
        "identifiers": sorted(lt.identifier_table),
        "constants": sorted(lt.constant_table),
        "symbols": [f"{n}|{c}|{t}|scope={sid}|slot={slot}" for n, c, t, sid, slot in sema.symbols.dump_rows()],
        "quadruples": quads,
    }


def _export_graphs(module: ast.Module, mir_mod, export_dir: str) -> None:
    out = Path(export_dir)
    out.mkdir(parents=True, exist_ok=True)
    # AST DOT
    ast_dot = ["digraph AST {"]
    nid = 0

    def emit(node, parent=None):
        nonlocal nid
        cur = f"n{nid}"; nid += 1
        label = type(node).__name__
        if isinstance(node, ast.Function):
            label += f"\\n{node.name}"
        ast_dot.append(f'{cur} [label="{label}"];')
        if parent:
            ast_dot.append(f"{parent} -> {cur};")
        if isinstance(node, ast.Module):
            for i in node.items:
                emit(i, cur)
        elif isinstance(node, ast.Function):
            emit(node.body, cur)
        elif isinstance(node, ast.Block):
            for s in node.stmts:
                emit(s, cur)
        elif isinstance(node, ast.IfStmt):
            emit(node.then_block, cur)
            if node.else_block:
                emit(node.else_block, cur)
        elif isinstance(node, ast.WhileStmt):
            emit(node.body, cur)

    emit(module)
    ast_dot.append("}")
    (out / "ast.dot").write_text("\n".join(ast_dot), encoding="utf-8")

    for fn in mir_mod.functions:
        lines = ["digraph CFG {"]
        for name, blk in fn.blocks.items():
            if not blk.instrs and not blk.preds and not blk.succs and name != "entry":
                continue
            lines.append(f'{name} [shape=box,label="{name}"];')
            for s in blk.succs:
                if s in fn.blocks:
                    lines.append(f"{name} -> {s};")
        lines.append("}")
        (out / f"cfg_{fn.name}.dot").write_text("\n".join(lines), encoding="utf-8")

    try:
        import graphviz  # type: ignore

        graphviz.Source((out / "ast.dot").read_text(encoding="utf-8")).render((out / "ast"), format="svg", cleanup=True)
        for fn in mir_mod.functions:
            dot = out / f"cfg_{fn.name}.dot"
            graphviz.Source(dot.read_text(encoding="utf-8")).render((out / f"cfg_{fn.name}"), format="svg", cleanup=True)
    except Exception:
        pass
