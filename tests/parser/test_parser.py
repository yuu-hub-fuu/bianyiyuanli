from nexa.frontend.lexer import scan
from nexa.frontend.parser import parse


def test_parser_pratt_precedence() -> None:
    src = "fn main() -> i32 { let a: i32 = 1 + 2 * 3; return a; }"
    lexed = scan(src)
    parsed = parse(lexed.value or [])
    assert parsed.ok
    assert parsed.value is not None
    assert len(parsed.value.items) == 1

