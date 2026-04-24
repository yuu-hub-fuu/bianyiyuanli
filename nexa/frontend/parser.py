from __future__ import annotations

from . import ast
from .diagnostics import DiagnosticBag
from .tokens import Span, Token, TokenKind


PRECEDENCE = {
    TokenKind.OROR: 1,
    TokenKind.ANDAND: 2,
    TokenKind.EQEQ: 3,
    TokenKind.NE: 3,
    TokenKind.LT: 4,
    TokenKind.LE: 4,
    TokenKind.GT: 4,
    TokenKind.GE: 4,
    TokenKind.PLUS: 5,
    TokenKind.MINUS: 5,
    TokenKind.STAR: 6,
    TokenKind.SLASH: 6,
    TokenKind.PERCENT: 6,
}


class Parser:
    def __init__(self, tokens: list[Token], diagnostics: DiagnosticBag | None = None) -> None:
        self.tokens = tokens
        self.i = 0
        self.diag = diagnostics or DiagnosticBag()

    def parse(self) -> ast.Module:
        items = []
        while not self._at(TokenKind.EOF):
            if self._match(TokenKind.FN):
                items.append(self._parse_fn())
            elif self._match(TokenKind.MACRO):
                items.append(self._parse_macro())
            else:
                self._error_here("期望顶层定义 fn/macro")
                self._sync_top()
        return ast.Module(self._span_of(0), items)

    def _parse_fn(self) -> ast.Function:
        name = self._expect(TokenKind.IDENT, "期望函数名")
        generics: list[str] = []
        if self._match(TokenKind.LBRACKET):
            while not self._at(TokenKind.RBRACKET) and not self._at(TokenKind.EOF):
                gp = self._expect(TokenKind.IDENT, "期望泛型参数")
                generics.append(gp.lexeme)
                if not self._match(TokenKind.COMMA):
                    break
            self._expect(TokenKind.RBRACKET, "缺少 ]")
        self._expect(TokenKind.LPAREN, "缺少 (")
        params: list[ast.Param] = []
        if not self._at(TokenKind.RPAREN):
            while True:
                p_name = self._expect(TokenKind.IDENT, "期望参数名")
                self._expect(TokenKind.COLON, "参数缺少类型注解")
                p_ty = self._parse_type_ref()
                params.append(ast.Param(p_name.span, p_name.lexeme, p_ty))
                if not self._match(TokenKind.COMMA):
                    break
        self._expect(TokenKind.RPAREN, "缺少 )")
        ret = ast.TypeRef(name.span, "void")
        if self._match(TokenKind.ARROW):
            ret = self._parse_type_ref()
        body = self._parse_block()
        return ast.Function(name.span, name.lexeme, params, ret, body, generics)

    def _parse_macro(self) -> ast.Macro:
        name = self._expect(TokenKind.IDENT, "期望宏名")
        self._expect(TokenKind.LPAREN, "缺少 (")
        params: list[str] = []
        if not self._at(TokenKind.RPAREN):
            while True:
                p = self._expect(TokenKind.IDENT, "期望宏参数")
                params.append(p.lexeme)
                if not self._match(TokenKind.COMMA):
                    break
        self._expect(TokenKind.RPAREN, "缺少 )")
        self._expect(TokenKind.LBRACE, "宏缺少 {")
        depth = 1
        toks: list[str] = []
        while depth > 0 and not self._at(TokenKind.EOF):
            t = self._advance()
            if t.kind == TokenKind.LBRACE:
                depth += 1
            elif t.kind == TokenKind.RBRACE:
                depth -= 1
                if depth == 0:
                    break
            toks.append(t.lexeme)
        return ast.Macro(name.span, name.lexeme, params, toks)

    def _parse_block(self) -> ast.Block:
        lb = self._expect(TokenKind.LBRACE, "缺少 {")
        stmts: list[ast.Stmt] = []
        while not self._at(TokenKind.RBRACE) and not self._at(TokenKind.EOF):
            stmts.append(self._parse_stmt())
        self._expect(TokenKind.RBRACE, "缺少 }")
        return ast.Block(lb.span, stmts)

    def _parse_stmt(self) -> ast.Stmt:
        if self._match(TokenKind.LET):
            n = self._expect(TokenKind.IDENT, "期望变量名")
            tr = None
            if self._match(TokenKind.COLON):
                tr = self._parse_type_ref()
            val = None
            if self._match(TokenKind.EQ):
                val = self._parse_expr()
            self._expect(TokenKind.SEMI, "缺少分号")
            return ast.LetStmt(n.span, n.lexeme, tr, val)
        if self._match(TokenKind.RETURN):
            start = self._peek(-1).span
            v = None if self._at(TokenKind.SEMI) else self._parse_expr()
            self._expect(TokenKind.SEMI, "缺少分号")
            return ast.ReturnStmt(start, v)
        if self._match(TokenKind.IF):
            start = self._peek(-1).span
            cond = self._parse_expr()
            tb = self._parse_block()
            eb = self._parse_block() if self._match(TokenKind.ELSE) else None
            return ast.IfStmt(start, cond, tb, eb)
        if self._match(TokenKind.WHILE):
            start = self._peek(-1).span
            cond = self._parse_expr()
            body = self._parse_block()
            return ast.WhileStmt(start, cond, body)
        if self._match(TokenKind.SPAWN):
            start = self._peek(-1).span
            e = self._parse_expr()
            self._expect(TokenKind.SEMI, "缺少分号")
            return ast.SpawnStmt(start, e)
        if self._match(TokenKind.SELECT):
            s = self._peek(-1).span
            self._expect(TokenKind.LBRACE, "select 缺少 {")
            cases = []
            while not self._at(TokenKind.RBRACE) and not self._at(TokenKind.EOF):
                if self._match(TokenKind.RECV):
                    self._expect(TokenKind.LPAREN, "recv 缺少 (")
                    ch = self._parse_expr()
                    self._expect(TokenKind.RPAREN, "recv 缺少 )")
                    self._expect(TokenKind.ARROW, "case 缺少 =>(使用 -> 代替)")
                    body = self._parse_block()
                    cases.append(ast.SelectCase(s, "recv", ch, None, body))
                elif self._match(TokenKind.SEND):
                    self._expect(TokenKind.LPAREN, "send 缺少 (")
                    ch = self._parse_expr(); self._expect(TokenKind.COMMA, "send 缺少 ,")
                    v = self._parse_expr(); self._expect(TokenKind.RPAREN, "send 缺少 )")
                    self._expect(TokenKind.ARROW, "case 缺少 =>(使用 -> 代替)")
                    body = self._parse_block()
                    cases.append(ast.SelectCase(s, "send", ch, v, body))
                elif self._match(TokenKind.ELSE):
                    self._expect(TokenKind.ARROW, "default 缺少 =>(使用 -> 代替)")
                    body = self._parse_block()
                    cases.append(ast.SelectCase(s, "default", None, None, body))
                else:
                    self._error_here("select 子句非法")
                    self._sync_stmt()
            self._expect(TokenKind.RBRACE, "select 缺少 }")
            return ast.SelectStmt(s, cases)
        if self._at(TokenKind.LBRACE):
            return self._parse_block()

        e = self._parse_expr()
        if isinstance(e, ast.NameExpr) and self._match(TokenKind.EQ):
            rhs = self._parse_expr()
            self._expect(TokenKind.SEMI, "缺少分号")
            return ast.AssignStmt(e.span, e, rhs)
        self._expect(TokenKind.SEMI, "缺少分号")
        return ast.ExprStmt(e.span, e)

    def _parse_type_ref(self) -> ast.TypeRef:
        n = self._expect(TokenKind.IDENT, "期望类型名")
        params: list[ast.TypeRef] = []
        if self._match(TokenKind.LBRACKET):
            while not self._at(TokenKind.RBRACKET) and not self._at(TokenKind.EOF):
                params.append(self._parse_type_ref())
                if not self._match(TokenKind.COMMA):
                    break
            self._expect(TokenKind.RBRACKET, "类型参数缺少 ]")
        return ast.TypeRef(n.span, n.lexeme, params)

    def _parse_expr(self, min_bp: int = 0) -> ast.Expr:
        tok = self._advance()
        if tok.kind == TokenKind.INT:
            lhs: ast.Expr = ast.IntLit(tok.span, None, int(tok.lexeme))
        elif tok.kind == TokenKind.TRUE:
            lhs = ast.BoolLit(tok.span, None, True)
        elif tok.kind == TokenKind.FALSE:
            lhs = ast.BoolLit(tok.span, None, False)
        elif tok.kind == TokenKind.STRING:
            lhs = ast.StrLit(tok.span, None, tok.lexeme)
        elif tok.kind == TokenKind.IDENT:
            lhs = ast.NameExpr(tok.span, None, tok.lexeme)
        elif tok.kind in (TokenKind.NOT, TokenKind.MINUS):
            rhs = self._parse_expr(7)
            lhs = ast.UnaryExpr(tok.span, None, tok.lexeme, rhs)
        elif tok.kind == TokenKind.LPAREN:
            lhs = self._parse_expr()
            self._expect(TokenKind.RPAREN, "缺少 )")
        else:
            self.diag.error(tok.span, f"非法表达式起始: {tok.kind.name}")
            lhs = ast.IntLit(tok.span, None, 0)

        while True:
            if self._at(TokenKind.LPAREN):
                self._advance()
                args: list[ast.Expr] = []
                if not self._at(TokenKind.RPAREN):
                    while True:
                        args.append(self._parse_expr())
                        if not self._match(TokenKind.COMMA):
                            break
                rp = self._expect(TokenKind.RPAREN, "缺少 )")
                lhs = ast.CallExpr(rp.span, None, lhs, args)
                continue
            op = self._peek().kind
            if op not in PRECEDENCE:
                break
            bp = PRECEDENCE[op]
            if bp < min_bp:
                break
            op_tok = self._advance()
            rhs = self._parse_expr(bp + 1)
            lhs = ast.BinaryExpr(op_tok.span, None, op_tok.lexeme, lhs, rhs)
        return lhs

    def _peek(self, off: int = 0) -> Token:
        idx = self.i + off
        if idx < 0:
            idx = 0
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def _advance(self) -> Token:
        t = self._peek()
        self.i = min(self.i + 1, len(self.tokens) - 1)
        return t

    def _at(self, kind: TokenKind) -> bool:
        return self._peek().kind == kind

    def _match(self, kind: TokenKind) -> bool:
        if self._at(kind):
            self._advance()
            return True
        return False

    def _expect(self, kind: TokenKind, msg: str) -> Token:
        if self._at(kind):
            return self._advance()
        self._error_here(msg)
        return Token(kind, "", self._peek().span)

    def _error_here(self, msg: str) -> None:
        self.diag.error(self._peek().span, msg)

    def _sync_stmt(self) -> None:
        sync = {TokenKind.SEMI, TokenKind.RBRACE, TokenKind.EOF}
        while self._peek().kind not in sync:
            self._advance()
        if self._at(TokenKind.SEMI):
            self._advance()

    def _sync_top(self) -> None:
        while self._peek().kind not in {TokenKind.FN, TokenKind.MACRO, TokenKind.EOF}:
            self._advance()

    def _span_of(self, idx: int) -> Span:
        if not self.tokens:
            return Span(0, 0, 1, 1)
        return self.tokens[min(idx, len(self.tokens) - 1)].span
