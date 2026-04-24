from __future__ import annotations

from dataclasses import dataclass

from nexa.frontend import ast
from nexa.utils.model import CompileResult, Diagnostic, DiagnosticLevel, Span, Token

PRECEDENCE = {
    "LOR": 1,
    "LAND": 2,
    "EQ": 3,
    "NE": 3,
    "LT": 4,
    "LE": 4,
    "GT": 4,
    "GE": 4,
    "PLUS": 5,
    "MINUS": 5,
    "STAR": 6,
    "SLASH": 6,
    "PERCENT": 6,
}


@dataclass(slots=True)
class Parser:
    tokens: list[Token]
    i: int = 0
    diagnostics: list[Diagnostic] | None = None

    def __post_init__(self) -> None:
        self.i = 0
        self.diagnostics = []

    def parse(self) -> CompileResult[ast.Module]:
        items: list[ast.Stmt] = []
        while not self.at("EOF"):
            items.append(self.parse_item())
        span = items[0].span if items else self.peek().span
        return CompileResult(ast.Module(span=span, items=items), self.diagnostics)

    def parse_item(self) -> ast.Stmt:
        if self.match("FN"):
            return self.parse_fn()
        return self.parse_stmt()

    def parse_fn(self) -> ast.FunctionDef:
        fn_tok = self.prev()
        name = self.expect("IDENT", "expect function name")
        self.expect("LPAREN", "expect '(' after function name")
        params: list[tuple[str, str]] = []
        if not self.at("RPAREN"):
            while True:
                p_name = self.expect("IDENT", "expect parameter name").lexeme
                self.expect("COLON", "expect ':'")
                p_ty = self.expect("IDENT", "expect parameter type").lexeme
                params.append((p_name, p_ty))
                if not self.match("COMMA"):
                    break
        self.expect("RPAREN", "expect ')' after parameters")
        ret = "void"
        if self.match("ARROW"):
            ret = self.expect("IDENT", "expect return type").lexeme
        body = self.parse_block()
        return ast.FunctionDef(name=name.lexeme, params=params, return_type=ret, body=body, span=Span(fn_tok.span.start, body.span.end))

    def parse_block(self) -> ast.Block:
        lbrace = self.expect("LBRACE", "expect '{'")
        stmts: list[ast.Stmt] = []
        while not self.at("RBRACE") and not self.at("EOF"):
            stmts.append(self.parse_stmt())
        rbrace = self.expect("RBRACE", "expect '}'")
        return ast.Block(span=Span(lbrace.span.start, rbrace.span.end), statements=stmts)

    def parse_stmt(self) -> ast.Stmt:
        if self.match("LET"):
            return self.parse_let()
        if self.match("IF"):
            return self.parse_if()
        if self.match("WHILE"):
            return self.parse_while()
        if self.match("RETURN"):
            return self.parse_return()
        if self.at("LBRACE"):
            return self.parse_block()

        expr = self.parse_expr(0)
        if isinstance(expr, ast.NameExpr) and self.match("ASSIGN"):
            value = self.parse_expr(0)
            semi = self.expect("SEMI", "expect ';' after assignment")
            return ast.AssignStmt(target=expr.name, value=value, span=Span(expr.span.start, semi.span.end))
        semi = self.expect("SEMI", "expect ';' after expression")
        return ast.ExprStmt(expr=expr, span=Span(expr.span.start, semi.span.end))

    def parse_let(self) -> ast.LetStmt:
        let_tok = self.prev()
        name = self.expect("IDENT", "expect variable name").lexeme
        ty: str | None = None
        init = None
        if self.match("COLON"):
            ty = self.expect("IDENT", "expect type after ':'").lexeme
        if self.match("ASSIGN"):
            init = self.parse_expr(0)
        semi = self.expect("SEMI", "expect ';' after let")
        return ast.LetStmt(name=name, type_name=ty, init=init, span=Span(let_tok.span.start, semi.span.end))

    def parse_if(self) -> ast.IfStmt:
        if_tok = self.prev()
        cond = self.parse_expr(0)
        then_branch = self.parse_block()
        else_branch = None
        if self.match("ELSE"):
            else_branch = self.parse_block()
            end = else_branch.span.end
        else:
            end = then_branch.span.end
        return ast.IfStmt(cond=cond, then_branch=then_branch, else_branch=else_branch, span=Span(if_tok.span.start, end))

    def parse_while(self) -> ast.WhileStmt:
        wt = self.prev()
        cond = self.parse_expr(0)
        body = self.parse_block()
        return ast.WhileStmt(cond=cond, body=body, span=Span(wt.span.start, body.span.end))

    def parse_return(self) -> ast.ReturnStmt:
        rt = self.prev()
        if self.at("SEMI"):
            semi = self.advance()
            return ast.ReturnStmt(value=None, span=Span(rt.span.start, semi.span.end))
        val = self.parse_expr(0)
        semi = self.expect("SEMI", "expect ';' after return")
        return ast.ReturnStmt(value=val, span=Span(rt.span.start, semi.span.end))

    def parse_expr(self, min_bp: int) -> ast.Expr:
        tok = self.advance()
        if tok.kind == "INT":
            lhs: ast.Expr = ast.IntLiteral(value=int(tok.lexeme), span=tok.span)
        elif tok.kind in {"TRUE", "FALSE"}:
            lhs = ast.BoolLiteral(value=tok.kind == "TRUE", span=tok.span)
        elif tok.kind == "STRING":
            lhs = ast.StringLiteral(value=tok.lexeme, span=tok.span)
        elif tok.kind == "IDENT":
            lhs = ast.NameExpr(name=tok.lexeme, span=tok.span)
            if self.match("LPAREN"):
                args: list[ast.Expr] = []
                if not self.at("RPAREN"):
                    while True:
                        args.append(self.parse_expr(0))
                        if not self.match("COMMA"):
                            break
                rparen = self.expect("RPAREN", "expect ')' after call args")
                lhs = ast.CallExpr(callee=tok.lexeme, args=args, span=Span(tok.span.start, rparen.span.end))
        elif tok.kind in {"BANG", "MINUS"}:
            rhs = self.parse_expr(7)
            lhs = ast.UnaryExpr(op=tok.lexeme, rhs=rhs, span=Span(tok.span.start, rhs.span.end))
        elif tok.kind == "LPAREN":
            lhs = self.parse_expr(0)
            self.expect("RPAREN", "expect ')' to close expression")
        else:
            self.error(tok, f"unexpected token in expression: {tok.kind}")
            lhs = ast.IntLiteral(value=0, span=tok.span)

        while True:
            op = self.peek()
            bp = PRECEDENCE.get(op.kind)
            if bp is None or bp < min_bp:
                break
            self.advance()
            rhs = self.parse_expr(bp + 1)
            lhs = ast.BinaryExpr(op=op.lexeme, lhs=lhs, rhs=rhs, span=Span(lhs.span.start, rhs.span.end))
        return lhs

    def peek(self) -> Token:
        return self.tokens[self.i]

    def prev(self) -> Token:
        return self.tokens[self.i - 1]

    def advance(self) -> Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def at(self, kind: str) -> bool:
        return self.peek().kind == kind

    def match(self, kind: str) -> bool:
        if self.at(kind):
            self.advance()
            return True
        return False

    def expect(self, kind: str, msg: str) -> Token:
        tok = self.peek()
        if tok.kind == kind:
            return self.advance()
        self.error(tok, msg)
        return tok

    def error(self, tok: Token, msg: str) -> None:
        self.diagnostics.append(Diagnostic(DiagnosticLevel.ERROR, tok.span, msg))


def parse(tokens: list[Token]) -> CompileResult[ast.Module]:
    return Parser(tokens).parse()

