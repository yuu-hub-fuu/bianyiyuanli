from __future__ import annotations

import html
from pathlib import Path


def write_html_report(path: Path, res) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    def section(title: str, rows: list[str]) -> str:
        body = "<br/>".join(html.escape(r) for r in rows) if rows else "<i>(empty)</i>"
        return f"<h2>{html.escape(title)}</h2><div class='box'>{body}</div>"

    timeline = "".join(
        f"<li>{html.escape(st.status)} {html.escape(st.name)} - {html.escape(st.detail)}</li>"
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
{section("Tokens", res.artifacts.tokens)}
{section("AST", res.artifacts.ast_text.splitlines())}
{section("HIR(raw)", res.artifacts.tables.get("hir_raw", []))}
{section("HIR(opt)", res.artifacts.tables.get("hir_opt", []))}
{section("Symbols", res.artifacts.symbols)}
</body></html>"""
    path.write_text(html_doc, encoding="utf-8")
