from __future__ import annotations

from dataclasses import dataclass, field

from nexa.frontend import ast


@dataclass(slots=True)
class MonoCache:
    instances: dict[tuple[str, tuple[str, ...]], str] = field(default_factory=dict)


def monomorphize(module: ast.Module) -> ast.Module:
    cache = MonoCache()
    for item in module.items:
        if isinstance(item, ast.Function) and item.generic_params:
            # teaching strategy: register potential instantiations and keep canonical fn.
            cache.instances[(item.name, tuple(item.generic_params))] = item.name
    return module
