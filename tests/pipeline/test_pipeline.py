from nexa.compiler import Compiler


def test_pipeline_end_to_end() -> None:
    src = "fn main() -> i32 { let a: i32 = 1 + 2; return a; }"
    result = Compiler().compile(src)
    assert result.ok
    assert result.value is not None
    assert any(line.startswith("mov") for line in result.value.hir)
    assert "main:" in result.value.asm

