from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from nexa.compiler import compile_source


class NexaStudio(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Nexa Studio")
        self.geometry("1200x800")

        top = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        top.pack(fill=tk.BOTH, expand=True)

        self.editor = tk.Text(top, wrap="none")
        self.editor.insert("1.0", "fn main() -> i32 { let a: i32 = 1 + 2; return a; }")
        top.add(self.editor, weight=3)

        right = ttk.Notebook(top)
        self.tokens = tk.Text(right, wrap="none")
        self.hir = tk.Text(right, wrap="none")
        self.asm = tk.Text(right, wrap="none")
        right.add(self.tokens, text="Tokens")
        right.add(self.hir, text="HIR")
        right.add(self.asm, text="ASM")
        top.add(right, weight=2)

        control = ttk.Frame(self)
        control.pack(fill=tk.X)
        ttk.Button(control, text="Compile", command=self.compile_now).pack(side=tk.LEFT, padx=8, pady=8)

    def compile_now(self) -> None:
        src = self.editor.get("1.0", tk.END)
        res = compile_source(src)
        self.tokens.delete("1.0", tk.END)
        self.tokens.insert("1.0", "\n".join(res.tokens + ["", "== diagnostics =="] + [d.message for d in res.diagnostics]))
        self.hir.delete("1.0", tk.END)
        self.hir.insert("1.0", "\n".join(res.hir))
        self.asm.delete("1.0", tk.END)
        blocks = []
        for fn, text in res.asm.items():
            blocks.append(f"-- {fn} --\n{text}")
        self.asm.insert("1.0", "\n".join(blocks))


def main() -> None:
    app = NexaStudio()
    app.mainloop()


if __name__ == "__main__":
    main()
