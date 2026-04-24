from nexa.frontend.lexer import scan


def test_lexer_tokens() -> None:
    src = "let a: i32 = 1 + 2;"
    out = scan(src)
    assert out.ok
    assert out.value is not None
    kinds = [t.kind for t in out.value]
    assert "LET" in kinds
    assert "IDENT" in kinds
    assert kinds[-1] == "EOF"

