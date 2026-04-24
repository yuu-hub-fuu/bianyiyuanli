from __future__ import annotations

from dataclasses import dataclass

from nexa.ir.mir import MIRFunction, MIRModule


@dataclass(slots=True)
class Interval:
    vreg: str
    start: int
    end: int


@dataclass(slots=True)
class AllocResult:
    mapping: dict[str, str | None]


class LinearScan:
    def __init__(self, regs: list[str] | None = None) -> None:
        self.regs = regs or ["r10", "r11", "r12", "r13"]

    def alloc_fn(self, fn: MIRFunction) -> AllocResult:
        intervals = self._compute_intervals(fn)
        active: list[Interval] = []
        alloc: dict[str, str | None] = {}
        free = self.regs[:]

        def expire(start: int) -> None:
            nonlocal active, free
            rest: list[Interval] = []
            for it in active:
                if it.end < start:
                    reg = alloc[it.vreg]
                    if reg is not None:
                        free.append(reg)
                else:
                    rest.append(it)
            active = sorted(rest, key=lambda x: x.end)

        for cur in sorted(intervals, key=lambda i: i.start):
            expire(cur.start)
            if free:
                alloc[cur.vreg] = free.pop()
                active.append(cur)
                active.sort(key=lambda x: x.end)
                continue
            spill = active[-1]
            if spill.end > cur.end:
                alloc[cur.vreg] = alloc[spill.vreg]
                alloc[spill.vreg] = None
                active[-1] = cur
                active.sort(key=lambda x: x.end)
            else:
                alloc[cur.vreg] = None
        return AllocResult(alloc)

    def _compute_intervals(self, fn: MIRFunction) -> list[Interval]:
        points: dict[str, list[int]] = {}
        idx = 0
        for block in fn.blocks:
            for ins in block.instrs:
                for ref in (ins.dst, ins.src1, ins.src2):
                    if ref and (ref.startswith("t") or ref.isidentifier()):
                        points.setdefault(ref, []).append(idx)
                idx += 1
        out: list[Interval] = []
        for name, uses in points.items():
            out.append(Interval(name, min(uses), max(uses)))
        return out


def allocate(module: MIRModule) -> dict[str, AllocResult]:
    ls = LinearScan()
    return {fn.name: ls.alloc_fn(fn) for fn in module.functions}

