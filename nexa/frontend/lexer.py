from __future__ import annotations

from dataclasses import dataclass

from nexa.utils.model import CompileResult, Diagnostic, DiagnosticLevel, Position, Span, Token

KEYWORDS = {
    "fn",
    "let",
    "if",
    "else",
    "while",
    "return",
    "true",
    "false",
}

SINGLE_CHAR = {
    "(": "LPAREN",
    ")": "RPAREN",
    "{": "LBRACE",
    "}": "RBRACE",
    ",": "COMMA",
    ";": "SEMI",
    ":": "COLON",
    "+": "PLUS",
    "-": "MINUS",
    "*": "STAR",
    "/": "SLASH",
    "%": "PERCENT",
    "=": "ASSIGN",
    "!": "BANG",
    "<": "LT",
    ">": "GT",
}

DOUBLE_CHAR = {
    "==": "EQ",
    "!=": "NE",
    "<=": "LE",
    ">=": "GE",
    "&&": "LAND",
    "||": "LOR",
    "->": "ARROW",
}


@dataclass(slots=True)
class Lexer:
    source: str

    def scan(self) -> CompileResult[list[Token]]:
        tokens: list[Token] = []
        diagnostics: list[Diagnostic] = []
        i = 0
        line = 1
        col = 1

        def pos(offset: int, ln: int, cl: int) -> Position:
            return Position(offset, ln, cl)

        while i < len(self.source):
            ch = self.source[i]
            if ch in " \t\r":
                i += 1
                col += 1
                continue
            if ch == "\n":
                i += 1
                line += 1
                col = 1
                continue

            start = pos(i, line, col)

            if i + 1 < len(self.source):
                pair = self.source[i : i + 2]
                if pair in DOUBLE_CHAR:
                    i += 2
                    col += 2
                    tokens.append(Token(DOUBLE_CHAR[pair], pair, Span(start, pos(i, line, col))))
                    continue

            if ch.isalpha() or ch == "_":
                j = i
                while j < len(self.source) and (self.source[j].isalnum() or self.source[j] == "_"):
                    j += 1
                lexeme = self.source[i:j]
                kind = lexeme.upper() if lexeme in KEYWORDS else "IDENT"
                i = j
                col += len(lexeme)
                tokens.append(Token(kind, lexeme, Span(start, pos(i, line, col))))
                continue

            if ch.isdigit():
                j = i
                while j < len(self.source) and self.source[j].isdigit():
                    j += 1
                lexeme = self.source[i:j]
                i = j
                col += len(lexeme)
                tokens.append(Token("INT", lexeme, Span(start, pos(i, line, col))))
                continue

            if ch == '"':
                j = i + 1
                local_line = line
                local_col = col + 1
                while j < len(self.source) and self.source[j] != '"':
                    if self.source[j] == "\n":
                        local_line += 1
                        local_col = 1
                    else:
                        local_col += 1
                    j += 1
                if j >= len(self.source):
                    diagnostics.append(Diagnostic(DiagnosticLevel.ERROR, Span(start, start), "unterminated string"))
                    break
                lexeme = self.source[i + 1 : j]
                i = j + 1
                col += len(lexeme) + 2
                tokens.append(Token("STRING", lexeme, Span(start, pos(i, line, col))))
                continue

            if ch in SINGLE_CHAR:
                i += 1
                col += 1
                tokens.append(Token(SINGLE_CHAR[ch], ch, Span(start, pos(i, line, col))))
                continue

            diagnostics.append(Diagnostic(DiagnosticLevel.ERROR, Span(start, start), f"illegal character: {ch!r}"))
            i += 1
            col += 1

        eof_pos = Position(i, line, col)
        tokens.append(Token("EOF", "", Span(eof_pos, eof_pos)))
        return CompileResult(tokens, diagnostics)


def scan(source: str) -> CompileResult[list[Token]]:
    return Lexer(source).scan()

