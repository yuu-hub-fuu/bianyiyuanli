from __future__ import annotations

from dataclasses import dataclass

from nexa.ir.hir import HIRFunction, HIRModule
from nexa.runtime import rt_core


@dataclass(slots=True)
class VMResult:
    return_value: int
    stdout: list[str]


@dataclass(slots=True)
class VMFrame:
    fn: str
    ip: int
    instr: str
    env: dict[str, object]
    stdout: list[str]


class HIRVM:
    def __init__(self, module: HIRModule) -> None:
        self.module = {f.name: f for f in module.functions}
        self.output: list[str] = []

    def run(self, entry: str = "main") -> VMResult:
        ret = self._call(entry, [])
        return VMResult(int(ret or 0), self.output)

    def run_with_trace(self, entry: str = "main", max_steps: int = 10000) -> tuple[VMResult, list[VMFrame]]:
        trace: list[VMFrame] = []
        ret = self._call(entry, [], trace, max_steps)
        return VMResult(int(ret or 0), self.output), trace

    def _call(self, name: str, args: list[object], trace: list[VMFrame] | None = None, max_steps: int = 10000) -> object:
        if name == "print":
            self.output.append(str(args[0]))
            return 0
        if name == "panic":
            raise RuntimeError(str(args[0]))
        if name == "chan":
            return rt_core.rt_chan_new(int(args[0]))
        if name == "send":
            rt_core.rt_chan_send(args[0], args[1]); return 0
        if name == "recv":
            return rt_core.rt_chan_recv(args[0])
        if name == "select_recv":
            return rt_core.rt_select_recv([args[0]], default=args[1])

        if name not in self.module:
            raise RuntimeError(f"VM: undefined function {name}")
        fn = self.module[name]
        env: dict[str, object] = {}
        labels: dict[str, int] = {}
        pending_args: list[object] = []

        param_names = [i.dst for i in fn.instrs if i.op == "param" and i.dst]
        for idx, p in enumerate(param_names):
            env[p] = args[idx] if idx < len(args) else 0

        for idx, ins in enumerate(fn.instrs):
            if ins.op == "label" and ins.dst:
                labels[ins.dst] = idx

        ip = 0
        steps = 0
        while ip < len(fn.instrs):
            ins = fn.instrs[ip]
            op = ins.op
            if trace is not None:
                trace.append(VMFrame(name, ip, ins.op, dict(env), list(self.output)))
            steps += 1
            if steps > max_steps:
                raise RuntimeError("VM: step limit exceeded")

            def val(x: str | None) -> object:
                if x is None:
                    return 0
                if x in env:
                    return env[x]
                try:
                    return int(x)
                except Exception:
                    return x

            if op == "param":
                ip += 1; continue
            if op.startswith("const.") and ins.dst:
                env[ins.dst] = val(ins.src1)
            elif op.startswith("mov.") and ins.dst:
                env[ins.dst] = val(ins.src1)
            elif op.startswith("unary.") and ins.dst:
                r = int(val(ins.src1))
                env[ins.dst] = -r if op.endswith("-") else (0 if r else 1)
            elif op.startswith("bin.") and ins.dst:
                a, b = val(ins.src1), val(ins.src2)
                sym = op[4:]
                if sym == "+": env[ins.dst] = int(a) + int(b)
                elif sym == "-": env[ins.dst] = int(a) - int(b)
                elif sym == "*": env[ins.dst] = int(a) * int(b)
                elif sym == "/": env[ins.dst] = int(a) // int(b)
                elif sym == "%": env[ins.dst] = int(a) % int(b)
                elif sym == "==": env[ins.dst] = int(a == b)
                elif sym == "!=": env[ins.dst] = int(a != b)
                elif sym == "<": env[ins.dst] = int(int(a) < int(b))
                elif sym == "<=": env[ins.dst] = int(int(a) <= int(b))
                elif sym == ">": env[ins.dst] = int(int(a) > int(b))
                elif sym == ">=": env[ins.dst] = int(int(a) >= int(b))
                elif sym == "&&": env[ins.dst] = int(bool(a) and bool(b))
                elif sym == "||": env[ins.dst] = int(bool(a) or bool(b))
            elif op == "arg" and ins.src1:
                pending_args.append(val(ins.src1))
            elif op == "call" and ins.src1:
                ret = self._call(ins.src1, pending_args, trace, max_steps)
                pending_args = []
                if ins.dst:
                    env[ins.dst] = ret
            elif op == "call.recv" and ins.dst:
                env[ins.dst] = self._call("recv", [val(ins.src1)], trace, max_steps)
            elif op == "call.send":
                self._call("send", [val(ins.src1), val(ins.src2)], trace, max_steps)
            elif op == "call.select_recv" and ins.dst:
                env[ins.dst] = self._call("select_recv", [val(ins.src1), val(ins.src2)], trace, max_steps)
            elif op == "br.true" and ins.dst:
                if int(val(ins.src1)) != 0:
                    ip = labels[ins.dst]
                    continue
            elif op == "br.ready" and ins.dst:
                ch = val(ins.src1)
                if hasattr(ch, "q") and not ch.q.empty():
                    ip = labels[ins.dst]
                    continue
            elif op == "jmp" and ins.dst:
                ip = labels[ins.dst]
                continue
            elif op == "ret":
                return val(ins.src1)
            ip += 1
        return 0


class VMDebugger:
    """Simple debugger facade over VM trace."""

    def __init__(self, module: HIRModule) -> None:
        self._vm = HIRVM(module)
        self._trace: list[VMFrame] = []
        self._idx = 0
        self._result: VMResult | None = None

    def start(self, entry: str = "main", max_steps: int = 10000) -> None:
        self._result, self._trace = self._vm.run_with_trace(entry, max_steps=max_steps)
        self._idx = 0

    def step(self) -> VMFrame | None:
        if self._idx >= len(self._trace):
            return None
        frame = self._trace[self._idx]
        self._idx += 1
        return frame

    def run(self) -> list[VMFrame]:
        if self._idx >= len(self._trace):
            return []
        rem = self._trace[self._idx :]
        self._idx = len(self._trace)
        return rem

    @property
    def result(self) -> VMResult | None:
        return self._result
