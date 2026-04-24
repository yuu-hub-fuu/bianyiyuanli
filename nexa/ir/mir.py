from __future__ import annotations

from dataclasses import dataclass, field

from nexa.ir.hir import HIRFunction, HIRInstr, HIRModule


@dataclass(slots=True)
class BasicBlock:
    label: str
    instrs: list[HIRInstr] = field(default_factory=list)
    preds: set[str] = field(default_factory=set)
    succs: set[str] = field(default_factory=set)


@dataclass(slots=True)
class MIRFunction:
    name: str
    blocks: list[BasicBlock] = field(default_factory=list)


@dataclass(slots=True)
class MIRModule:
    functions: list[MIRFunction] = field(default_factory=list)


class CFGBuilder:
    def build(self, mod: HIRModule) -> MIRModule:
        out = MIRModule()
        for fn in mod.functions:
            out.functions.append(self.build_fn(fn))
        return out

    def build_fn(self, fn: HIRFunction) -> MIRFunction:
        block = BasicBlock(label="entry", instrs=list(fn.instrs))
        return MIRFunction(name=fn.name, blocks=[block])


def build_cfg(mod: HIRModule) -> MIRModule:
    return CFGBuilder().build(mod)

