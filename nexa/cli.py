from __future__ import annotations

import argparse
from pathlib import Path

from nexa.compiler import Compiler


def main() -> int:
    parser = argparse.ArgumentParser(description="Nexa teaching compiler")
    parser.add_argument("file", type=Path)
    args = parser.parse_args()

    source = args.file.read_text(encoding="utf-8")
    result = Compiler().compile(source)
    for d in result.diagnostics:
        print(f"{d.level}: {d.message} @ {d.span.start.line}:{d.span.start.column}")
    if not result.ok or result.value is None:
        return 1
    print("== TOKENS ==")
    print("\n".join(result.value.tokens))
    print("== HIR ==")
    print("\n".join(result.value.hir))
    print("== ASM ==")
    print(result.value.asm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

