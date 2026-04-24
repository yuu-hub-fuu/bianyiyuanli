from __future__ import annotations

from .diagnostics import DiagnosticBag
from .tokens import KEYWORDS, Span, Token, TokenKind


class Lexer:
    def __init__(self, source: str, diagnostics: DiagnosticBag | None = None) -> None:
        self.source = source
        self.i = 0
        self.line = 1
        self.col = 1
        self.diag = diagnostics or DiagnosticBag()

    def _peek(self, off: int = 0) -> str:
        p = self.i + off
        return self.source[p] if p < len(self.source) else "\0"

    def _advance(self) -> str:
        ch = self._peek()
        self.i += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _span(self, s: int, e: int, line: int, col: int) -> Span:
        return Span(s, e, line, col)

    def scan(self) -> list[Token]:
        out: list[Token] = []
        while self._peek() != "\0":
            ch = self._peek()
            if ch in " \t\r\n":
                self._advance()
                continue
            if ch == "/" and self._peek(1) == "/":
                while self._peek() not in ("\n", "\0"):
                    self._advance()
                continue
            start, line, col = self.i, self.line, self.col
            if ch.isalpha() or ch == "_":
                lex = self._scan_ident()
                kind = KEYWORDS.get(lex, TokenKind.IDENT)
                out.append(Token(kind, lex, self._span(start, self.i, line, col)))
                continue
            if ch.isdigit():
                lex = self._scan_number()
                out.append(Token(TokenKind.INT, lex, self._span(start, self.i, line, col)))
                continue
            if ch == '"':
                tok = self._scan_string(start, line, col)
                out.append(tok)
                continue
            tok = self._scan_punct(start, line, col)
            if tok:
                out.append(tok)
            else:
                bad = self._advance()
                self.diag.error(self._span(start, self.i, line, col), f"非法字符: {bad!r}")
        out.append(Token(TokenKind.EOF, "", self._span(self.i, self.i, self.line, self.col)))
        return out

    def _scan_ident(self) -> str:
        s = self.i
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        return self.source[s:self.i]

    def _scan_number(self) -> str:
        s = self.i
        while self._peek().isdigit():
            self._advance()
        return self.source[s:self.i]

    def _scan_string(self, start: int, line: int, col: int) -> Token:
        self._advance()
        chars: list[str] = []
        while self._peek() not in ('"', "\0"):
            if self._peek() == "\\":
                self._advance()
                esc = self._advance()
                chars.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(esc, esc))
            else:
                chars.append(self._advance())
        if self._peek() != '"':
            self.diag.error(self._span(start, self.i, line, col), "字符串未闭合")
            return Token(TokenKind.STRING, "".join(chars), self._span(start, self.i, line, col))
        self._advance()
        return Token(TokenKind.STRING, "".join(chars), self._span(start, self.i, line, col))

    def _scan_punct(self, start: int, line: int, col: int) -> Token | None:
        two = self._peek() + self._peek(1)
        pair = {
            "==": TokenKind.EQEQ,
            "!=": TokenKind.NE,
            "<=": TokenKind.LE,
            ">=": TokenKind.GE,
            "&&": TokenKind.ANDAND,
            "||": TokenKind.OROR,
            "->": TokenKind.ARROW,
        }
        if two in pair:
            self._advance(); self._advance()
            return Token(pair[two], two, self._span(start, self.i, line, col))
        single = {
            "+": TokenKind.PLUS,
            "-": TokenKind.MINUS,
            "*": TokenKind.STAR,
            "/": TokenKind.SLASH,
            "%": TokenKind.PERCENT,
            "=": TokenKind.EQ,
            "<": TokenKind.LT,
            ">": TokenKind.GT,
            "!": TokenKind.NOT,
            "(": TokenKind.LPAREN,
            ")": TokenKind.RPAREN,
            "{": TokenKind.LBRACE,
            "}": TokenKind.RBRACE,
            "[": TokenKind.LBRACKET,
            "]": TokenKind.RBRACKET,
            ":": TokenKind.COLON,
            ";": TokenKind.SEMI,
            ",": TokenKind.COMMA,
            ".": TokenKind.DOT,
        }
        ch = self._peek()
        if ch in single:
            self._advance()
            return Token(single[ch], ch, self._span(start, self.i, line, col))
        return None
