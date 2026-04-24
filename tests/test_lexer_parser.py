from nexa.frontend.diagnostics import DiagnosticBag
from nexa.frontend.lexer import Lexer
from nexa.frontend.parser import Parser


def test_lexer_tokens():
    src = 'fn main() -> i32 { let a: i32 = 1 + 2; return a; }'
    diag = DiagnosticBag()
    tokens = Lexer(src, diag).scan()
    assert not diag.has_errors()
    assert any(t.lexeme == 'main' for t in tokens)


def test_parser_function():
    src = 'fn main() -> i32 { let a: i32 = 1 + 2; return a; }'
    diag = DiagnosticBag()
    module = Parser(Lexer(src, diag).scan(), diag).parse()
    assert len(module.items) == 1
    fn = module.items[0]
    assert fn.name == 'main'
