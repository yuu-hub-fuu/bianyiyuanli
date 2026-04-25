from __future__ import annotations

import argparse
import html
from pathlib import Path

from nexa.compiler import compile_source


def _print_table(title: str, rows: list[str]) -> None:
    print(f"== {title} ==")
    if rows:
        print("\n".join(rows))
    else:
        print("(empty)")


def _write_html_report(path: Path, res) -> None:
    def section(title: str, rows: list[str]) -> str:
        body = "<br/>".join(html.escape(r) for r in rows) if rows else "<i>(empty)</i>"
        return f"<h2>{html.escape(title)}</h2><div class='box'>{body}</div>"

    timeline = "".join(
        f"<li>{'✅' if st.ok else '❌'} {html.escape(st.name)} - {html.escape(st.detail)}</li>"
        for st in res.timeline
    )
    diags = "".join(
        f"<li><b>{html.escape(d.level)}</b> {html.escape(d.message)} @ {d.span.line}:{d.span.col}</li>"
        for d in res.diagnostics
    )
    html_doc = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/><title>Nexa Report</title>
<style>
body{{font-family:ui-monospace,Consolas,monospace;padding:20px;line-height:1.4}}
.box{{background:#f7f7f7;border:1px solid #ddd;padding:10px;white-space:pre-wrap}}
h1,h2{{margin:12px 0 6px}} ul{{margin:6px 0 12px}}
</style></head><body>
<h1>Nexa 编译报告</h1>
<h2>Timeline</h2><ul>{timeline}</ul>
<h2>Diagnostics</h2><ul>{diags or '<li>none</li>'}</ul>
{section("Tokens", res.tokens)}
{section("AST", res.ast_text.splitlines())}
{section("HIR(raw)", res.hir_raw)}
{section("HIR(opt)", res.hir_opt)}
{section("Symbols", res.symbols)}
</body></html>"""
    path.write_text(html_doc, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Nexa compiler")
    ap.add_argument("source", type=Path)
    ap.add_argument("--dump", choices=["tokens", "tables", "ast", "hir", "cfg", "asm", "all"], default="all")
    ap.add_argument("--mode", choices=["core", "full"], default="full")
    ap.add_argument("--export-dir", default=None)
    ap.add_argument("--emit-llvm", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--trace", action="store_true", help="print VM execution trace (requires --run)")
    ap.add_argument("--report", type=Path, default=None, help="write HTML compile report")
    args = ap.parse_args()

    src = args.source.read_text(encoding="utf-8")
    res = compile_source(src, mode=args.mode, export_dir=args.export_dir, run=args.run, trace=args.trace and args.run)

    print("== TIMELINE ==")
    for st in res.timeline:
        icon = "✅" if st.ok else "❌"
        print(f"{icon} {st.name:<12} {st.detail}")

    for d in res.diagnostics:
        print(f"[{d.level}] {d.message} @ line {d.span.line}:{d.span.col}")
        for n in d.notes:
            print(f"  note: {n}")
        for f in d.fixits:
            print(f"  fix: {f}")


    if args.run and res.run_value is not None:
        print("== RUN ==")
        for line in res.run_stdout:
            print(line)
        print(f"exit={res.run_value}")
        if args.trace:
            print("== TRACE ==")
            for i, fr in enumerate(res.vm_trace, 1):
                print(f"#{i:04d} {fr.fn}@{fr.ip} op={fr.instr} env={fr.env}")


    if args.emit_llvm:
        if args.mode != "core":
            print("[warning] LLVM backend only supports core integer subset")
        print("== LLVM IR ==")
        print(res.llvm_ir)

    if args.dump in {"tokens", "all"}:
        _print_table("TOKENS", res.tokens)

    if args.dump in {"tables", "all"}:
        _print_table("关键字表", res.tables["keywords"])
        _print_table("界符表", res.tables["delimiters"])
        _print_table("标识符表", res.tables["identifiers"])
        _print_table("常量表", res.tables["constants"])
        _print_table("符号表", res.symbols)
        _print_table("四元式表", res.hir_opt)

    if args.dump in {"ast", "all"}:
        _print_table("AST", res.ast_text.splitlines())

    if args.dump in {"hir", "all"}:
        _print_table("HIR(原始)", res.hir_raw)
        _print_table("HIR(优化后)", res.hir_opt)

    if args.dump in {"cfg", "all"}:
        print("== CFG ==")
        for fn, rows in res.cfg.items():
            print(f"-- {fn} --")
            print("\n".join(rows))

    if args.dump in {"asm", "all"}:
        print("== ASM ==")
        for fn, text in res.asm.items():
            print(f"-- {fn} --")
            print(text)

    if args.report is not None:
        _write_html_report(args.report, res)
        print(f"[report] wrote {args.report}")

    return 1 if any(d.level == "error" for d in res.diagnostics) else 0


if __name__ == "__main__":
    raise SystemExit(main())
