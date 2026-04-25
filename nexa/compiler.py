from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from nexa.backend.asm_x64 import emit_function
from nexa.backend.llvm_backend import emit_llvm_ir
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
from nexa.vm import HIRVM


@dataclass(slots=True)
class StageStatus:
    name: str
    ok: bool
    detail: str


@dataclass(slots=True)
class BuildResult:
    diagnostics: list[Diagnostic]
    tokens: list[str]
    tables: dict[str, list[str]]
    ast_text: str
    symbols: list[str]
    hir_raw: list[str]
    hir_opt: list[str]
    cfg: dict[str, list[str]]
    asm: dict[str, str]
    timeline: list[StageStatus] = field(default_factory=list)
    run_value: int | None = None
    run_stdout: list[str] = field(default_factory=list)
    llvm_ir: str = ""


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
    for fn in hir_mod.functions:
        lines.append(f"{fn.name}:")
        for idx, i in enumerate(fn.instrs, 1):
            lines.append(f"  {idx:03d}: ({i.op}, {i.src1}, {i.src2}, {i.dst}) @{i.span[0]}:{i.span[1]}")
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




def llvm_subset_warning(hir_lines: list[str], mode: str, diag: DiagnosticBag) -> None:
    if mode != "core" and any(x in ln for x in ("const.str", "call.select_recv", "call.send", "call.recv") for ln in hir_lines):
        diag.warn(Span(0, 0, 1, 1), "LLVM backend only supports core integer subset")

def compile_source(source: str, mode: str = "full", export_dir: str | None = None, run: bool = False) -> BuildResult:
    diag = DiagnosticBag()
    timeline: list[StageStatus] = []

    lexer = Lexer(source, diag)
    tokens = lexer.scan()
    timeline.append(StageStatus("Lexer", not diag.has_errors(), f"tokens={len(tokens)}"))

    parser = Parser(tokens, diag)
    module = parser.parse()
    timeline.append(StageStatus("Parser", not diag.has_errors(), f"items={len(module.items)}"))

    if mode == "full":
        module = MacroExpander(diag).expand_module(module)
    timeline.append(StageStatus("MacroExpand", not diag.has_errors(), "enabled" if mode == "full" else "core-mode disabled"))

    sema_pre: SemanticResult = Checker(diag, mode=mode).analyze(module)
    timeline.append(StageStatus("Sema", not diag.has_errors(), f"symbols={len(sema_pre.symbols.history)}"))

    if mode == "full":
        module = monomorphize(module)
    timeline.append(StageStatus("Monomorphize", not diag.has_errors(), "enabled" if mode == "full" else "core-mode disabled"))

    # Re-run semantic analysis after monomorphization so cloned functions get proper concrete typing.
    sema: SemanticResult = Checker(diag, mode=mode).analyze(module)
    timeline.append(StageStatus("Sema(redo)", not diag.has_errors(), f"symbols={len(sema.symbols.history)}"))

    lowerer = Lowerer()
    hir_raw_mod = lowerer.lower_module(module)
    hir_raw_lines = _hir_lines(hir_raw_mod)
    timeline.append(StageStatus("HIR", True, f"instrs={sum(len(f.instrs) for f in hir_raw_mod.functions)}"))

    hir_opt_mod = run_optimizations(hir_raw_mod)
    hir_opt_lines = _hir_lines(hir_opt_mod)
    timeline.append(StageStatus("Optimize", True, "const-fold + dce"))
    llvm_subset_warning(hir_opt_lines, mode, diag)

    llvm_ir = emit_llvm_ir(hir_opt_mod)
    mir_mod = hir_to_mir(hir_opt_mod)
    timeline.append(StageStatus("MIR", True, f"functions={len(mir_mod.functions)}"))

    asm: dict[str, str] = {}
    cfg_dump: dict[str, list[str]] = {}
    for fn in mir_mod.functions:
        intervals = compute_intervals(fn)
        alloc = linear_scan(intervals, ["r10", "r11", "r12", "r13", "r14", "r15"])
        asm[fn.name] = emit_function(fn, alloc)
        cfg_dump[fn.name] = _cfg_dump(fn)
    timeline.append(StageStatus("RegAlloc", True, "linear-scan"))
    timeline.append(StageStatus("Backend", True, f"asm-fns={len(asm)}"))

    _suggestions(diag)

    tables = _format_tables(lexer.tables, sema, hir_opt_lines)
    symbols = [f"{n:<12} {c:<8} {t:<12} scope={sid} slot={slot}" for n, c, t, sid, slot in sema.symbols.dump_rows()]

    run_value = None
    run_stdout: list[str] = []
    if run and not diag.has_errors():
        try:
            vm_res = HIRVM(hir_opt_mod).run("main")
            run_value = vm_res.return_value
            run_stdout = vm_res.stdout
        except Exception as exc:  # noqa: BLE001
            run_stdout = [f"runtime error: {exc}"]
            diag.add(Level.ERROR, Span(0, 0, 1, 1), f"运行时错误: {exc}")

    if export_dir:
        _export_graphs(module, mir_mod, export_dir)

    return BuildResult(
        diagnostics=diag.items,
        tokens=[f"{t.kind.name}:{t.lexeme}" for t in tokens],
        tables=tables,
        ast_text="\n".join(_ast_dump(module)),
        symbols=symbols,
        hir_raw=hir_raw_lines,
        hir_opt=hir_opt_lines,
        cfg=cfg_dump,
        asm=asm,
        timeline=timeline,
        run_value=run_value,
        run_stdout=run_stdout,
        llvm_ir=llvm_ir,
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
