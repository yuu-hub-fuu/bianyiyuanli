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
        ttk.Button(left, text="Apply Fix", command=self.apply_first_fix).pack(anchor="w", pady=2)
        self.last_result = None
        top.add(left, weight=3)

        right = ttk.Notebook(top)
        self.views: dict[str, tk.Text] = {}
        for name in ["Token", "AST", "Symbol Tree", "HIR Table", "Diagnostics Groups", "CFG", "ASM", "Timeline", "Run Output", "Trace Panel"]:
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
        res = compile_source(src, mode="full", export_dir="out", run=True, trace=True)
        self.last_result = res
        self._set("Token", "\n".join(res.artifacts.tokens))
        self._set("AST", res.artifacts.ast_text)
        # Symbol tree view (global -> scope)
        symbol_tree = ["global"]
        for row in res.artifacts.symbols:
            symbol_tree.append("  ├─ " + row)
        self._set("Symbol Tree", "\n".join(symbol_tree))

        self._set("HIR Table", "\n".join(res.artifacts.tables.get("hir_opt", [])))
        grouped: dict[str, list[str]] = {}
        for d in res.diagnostics:
            grouped.setdefault(d.level, []).append(d.message)
        diag_groups = []
        for lv, msgs in grouped.items():
            diag_groups.append(f"[{lv}]")
            diag_groups.extend(f"  - {m}" for m in msgs)
        self._set("Diagnostics Groups", "\n".join(diag_groups))
        cfg = []
        for fn, rows in res.artifacts.cfg.items():
            cfg.append(f"-- {fn} --\n" + "\n".join(rows))
        self._set("CFG", "\n\n".join(cfg))
        self._set("ASM", "\n\n".join(f"-- {k} --\n{v}" for k, v in res.artifacts.asm.items()))
        dashboard = ["编译流水线仪表盘"]
        dashboard.extend(f"{s.status:<8} {s.name:<12} {s.detail}" for s in res.timeline)
        self._set("Timeline", "\n".join(dashboard))
        self._set("Run Output", "\n".join(res.run_stdout + ([f"exit={res.run_value}"] if res.run_value is not None else [])))
        self._set("Trace Panel", "\n".join(f"{i+1:04d} {f.fn}@{f.ip} {f.instr}" for i, f in enumerate(res.vm_trace)))

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


    def apply_first_fix(self) -> None:
        if self.last_result is None:
            return
        for d in self.last_result.diagnostics:
            if not d.fixits:
                continue
            if "分号" in d.message:
                idx = f"{d.span.line}.{max(d.span.col-1, 0)}"
                self.editor.insert(idx, ";")
                self.compile_now()
                return



def main() -> None:
    app = NexaStudio()
    app.mainloop()


if __name__ == "__main__":
    main()
