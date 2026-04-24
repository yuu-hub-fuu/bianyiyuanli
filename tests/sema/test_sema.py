from nexa.frontend.lexer import scan
from nexa.frontend.parser import parse
from nexa.sema.checker import analyze


def test_sema_undefined_symbol() -> None:
    src = "fn main() -> i32 { return x; }"
    lexed = scan(src)
    parsed = parse(lexed.value or [])
    sema = analyze(parsed.value)
    assert not sema.ok
    assert any("undefined symbol" in d.message for d in sema.diagnostics)

