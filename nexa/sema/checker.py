from __future__ import annotations

from dataclasses import dataclass

from nexa.frontend import ast
from nexa.utils.model import CompileResult, Diagnostic, DiagnosticLevel, Symbol, SymbolTable


@dataclass(slots=True)
class SemanticResult:
    module: ast.Module
    symbols: SymbolTable


class SemanticAnalyzer:
    def __init__(self) -> None:
        self.symbols = SymbolTable()
        self.diagnostics: list[Diagnostic] = []
        self.current_return = "void"

    def analyze(self, module: ast.Module) -> CompileResult[SemanticResult]:
        for item in module.items:
            self.visit_stmt(item)
        return CompileResult(SemanticResult(module=module, symbols=self.symbols), self.diagnostics)

    def visit_stmt(self, node: ast.Stmt) -> None:
        if isinstance(node, ast.FunctionDef):
            self.visit_fn(node)
        elif isinstance(node, ast.Block):
            self.visit_block(node)
        elif isinstance(node, ast.LetStmt):
            self.visit_let(node)
        elif isinstance(node, ast.AssignStmt):
            self.visit_assign(node)
        elif isinstance(node, ast.IfStmt):
            self.require_type(self.visit_expr(node.cond), "bool", node.cond)
            self.visit_block(node.then_branch)
            if node.else_branch:
                self.visit_block(node.else_branch)
        elif isinstance(node, ast.WhileStmt):
            self.require_type(self.visit_expr(node.cond), "bool", node.cond)
            self.visit_block(node.body)
        elif isinstance(node, ast.ReturnStmt):
            rty = self.visit_expr(node.value) if node.value else "void"
            if self.current_return != rty:
                self.error(node, f"return type mismatch: expect {self.current_return}, got {rty}")
        elif isinstance(node, ast.ExprStmt):
            self.visit_expr(node.expr)

    def visit_fn(self, node: ast.FunctionDef) -> None:
        inserted = self.symbols.insert(Symbol(node.name, "fn", node.return_type, self.symbols.current_scope_id, mutable=False))
        if not inserted:
            self.error(node, f"duplicate function '{node.name}'")
            return
        self.symbols.push()
        prev = self.current_return
        self.current_return = node.return_type
        for pname, ptype in node.params:
            if not self.symbols.insert(Symbol(pname, "param", ptype, self.symbols.current_scope_id)):
                self.error(node, f"duplicate parameter '{pname}'")
        self.visit_block(node.body, push=False)
        self.current_return = prev
        self.symbols.pop()

    def visit_block(self, block: ast.Block, push: bool = True) -> None:
        if push:
            self.symbols.push()
        for stmt in block.statements:
            self.visit_stmt(stmt)
        if push:
            self.symbols.pop()

    def visit_let(self, node: ast.LetStmt) -> None:
        inferred = self.visit_expr(node.init) if node.init else "unknown"
        declared = node.type_name or inferred
        if node.type_name and node.init:
            self.require_type(inferred, node.type_name, node)
        if not self.symbols.insert(Symbol(node.name, "var", declared, self.symbols.current_scope_id)):
            self.error(node, f"duplicate declaration '{node.name}'")

    def visit_assign(self, node: ast.AssignStmt) -> None:
        sym = self.symbols.lookup(node.target)
        if sym is None:
            self.error(node, f"undefined variable '{node.target}'")
            return
        vty = self.visit_expr(node.value)
        self.require_type(vty, sym.type_name, node)

    def visit_expr(self, node: ast.Expr | None) -> str:
        if node is None:
            return "void"
        if isinstance(node, ast.IntLiteral):
            node.inferred_type = "i32"
            return "i32"
        if isinstance(node, ast.BoolLiteral):
            node.inferred_type = "bool"
            return "bool"
        if isinstance(node, ast.StringLiteral):
            node.inferred_type = "str"
            return "str"
        if isinstance(node, ast.NameExpr):
            sym = self.symbols.lookup(node.name)
            if sym is None:
                self.error(node, f"undefined symbol '{node.name}'")
                return "error"
            node.inferred_type = sym.type_name
            return sym.type_name
        if isinstance(node, ast.UnaryExpr):
            rty = self.visit_expr(node.rhs)
            if node.op == "!":
                self.require_type(rty, "bool", node)
                return "bool"
            if node.op == "-":
                self.require_type(rty, "i32", node)
                return "i32"
        if isinstance(node, ast.BinaryExpr):
            lty = self.visit_expr(node.lhs)
            rty = self.visit_expr(node.rhs)
            if node.op in {"+", "-", "*", "/", "%"}:
                self.require_type(lty, "i32", node)
                self.require_type(rty, "i32", node)
                return "i32"
            if node.op in {"&&", "||"}:
                self.require_type(lty, "bool", node)
                self.require_type(rty, "bool", node)
                return "bool"
            if node.op in {"==", "!=", "<", "<=", ">", ">="}:
                self.require_type(lty, rty, node)
                return "bool"
        if isinstance(node, ast.CallExpr):
            sym = self.symbols.lookup(node.callee)
            if sym is None or sym.category != "fn":
                self.error(node, f"undefined function '{node.callee}'")
                return "error"
            for arg in node.args:
                self.visit_expr(arg)
            return sym.type_name
        return "error"

    def require_type(self, actual: str, expected: str, node: ast.Node) -> None:
        if actual != expected and actual != "error":
            self.error(node, f"type mismatch: expect {expected}, got {actual}")

    def error(self, node: ast.Node, msg: str) -> None:
        self.diagnostics.append(Diagnostic(DiagnosticLevel.ERROR, node.span, msg))


def analyze(module: ast.Module) -> CompileResult[SemanticResult]:
    return SemanticAnalyzer().analyze(module)

