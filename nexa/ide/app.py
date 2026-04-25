from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from nexa.compiler import compile_source


class NexaStudio(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Nexa Studio ✨")
        self.geometry("1400x900")

        root = ttk.PanedWindow(self, orient=tk.VERTICAL)
        root.pack(fill=tk.BOTH, expand=True)

        top = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        root.add(top, weight=5)

        left = ttk.Frame(top)
        ttk.Label(left, text="Source").pack(anchor="w")
        self.editor = tk.Text(left, wrap="none", font=("Consolas", 12))
        self.editor.pack(fill=tk.BOTH, expand=True)
        self.editor.insert("1.0", "fn main() -> i32 { let a: i32 = 1 + 2 * 3; return a; }")
        ttk.Button(left, text="Compile", command=self.compile_now).pack(anchor="w", pady=6)
        top.add(left, weight=3)

        right = ttk.Notebook(top)
        self.views: dict[str, tk.Text] = {}
        for name in ["Token", "AST", "Symbol", "HIR", "HIR-Diff", "CFG", "ASM", "Timeline"]:
            frame = ttk.Frame(right)
            txt = tk.Text(frame, wrap="none", font=("Consolas", 11))
            txt.pack(fill=tk.BOTH, expand=True)
            right.add(frame, text=name)
            self.views[name] = txt
        top.add(right, weight=4)

        bottom = ttk.Frame(root)
        ttk.Label(bottom, text="Diagnostics").pack(anchor="w")
        self.diag = tk.Text(bottom, wrap="word", height=10, font=("Consolas", 11))
        self.diag.pack(fill=tk.BOTH, expand=True)
        root.add(bottom, weight=1)

    def _set(self, name: str, content: str) -> None:
        v = self.views[name]
        v.delete("1.0", tk.END)
        v.insert("1.0", content)

    def compile_now(self) -> None:
        src = self.editor.get("1.0", tk.END)
        res = compile_source(src, mode="full", export_dir="out")
        self._set("Token", "\n".join(res.tokens))
        self._set("AST", res.ast_text)
        # Symbol tree view (global -> scope)
        symbol_tree = ["global"]
        for row in res.symbols:
            symbol_tree.append("  ├─ " + row)
        self._set("Symbol", "\n".join(symbol_tree))

        self._set("HIR", "=== raw ===\n" + "\n".join(res.hir_raw) + "\n\n=== opt ===\n" + "\n".join(res.hir_opt))
        raw_set = set(res.hir_raw)
        opt_set = set(res.hir_opt)
        diff_rows = ["--- Removed by optimization ---"]
        diff_rows.extend(["- " + x for x in res.hir_raw if x not in opt_set])
        diff_rows.append("\n+++ Added/Changed after optimization +++")
        diff_rows.extend(["+ " + x for x in res.hir_opt if x not in raw_set])
        self._set("HIR-Diff", "\n".join(diff_rows))
        cfg = []
        for fn, rows in res.cfg.items():
            cfg.append(f"-- {fn} --\n" + "\n".join(rows))
        self._set("CFG", "\n\n".join(cfg))
        self._set("ASM", "\n\n".join(f"-- {k} --\n{v}" for k, v in res.asm.items()))
        dashboard = ["编译流水线仪表盘"]
        dashboard.extend(("✅" if s.ok else "❌") + f" {s.name:<12} {s.detail}" for s in res.timeline)
        self._set("Timeline", "\n".join(dashboard))

        self.diag.delete("1.0", tk.END)
        if not res.diagnostics:
            self.diag.insert("1.0", "无错误。")
        else:
            lines = []
            for d in res.diagnostics:
                lines.append(f"[{d.level}] {d.message} @ {d.span.line}:{d.span.col}")
                lines.extend(f"  note: {n}" for n in d.notes)
                lines.extend(f"  fix: {f}" for f in d.fixits)
            self.diag.insert("1.0", "\n".join(lines))


def main() -> None:
    app = NexaStudio()
    app.mainloop()


if __name__ == "__main__":
    main()
