from __future__ import annotations

import argparse
from pathlib import Path

from nexa.compiler import compile_source


def main() -> int:
    ap = argparse.ArgumentParser(description="Nexa compiler")
    ap.add_argument("source", type=Path)
    ap.add_argument("--dump", choices=["tokens", "hir", "asm", "all"], default="all")
    args = ap.parse_args()

    src = args.source.read_text(encoding="utf-8")
    res = compile_source(src)

    for d in res.diagnostics:
        print(f"[{d.level}] {d.message} @ line {d.span.line}:{d.span.col}")
    if args.dump in {"tokens", "all"}:
        print("== TOKENS ==")
        print("\n".join(res.tokens))
    if args.dump in {"hir", "all"}:
        print("== HIR ==")
        print("\n".join(res.hir))
    if args.dump in {"asm", "all"}:
        print("== ASM ==")
        for fn, text in res.asm.items():
            print(f"-- {fn} --")
            print(text)
    return 1 if any(d.level == "error" for d in res.diagnostics) else 0


if __name__ == "__main__":
    raise SystemExit(main())
