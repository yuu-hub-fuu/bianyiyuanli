from nexa.compiler import compile_source


PROGRAM = '''
fn add(a: i32, b: i32) -> i32 {
    let c: i32 = a + b;
    return c;
}

fn main() -> i32 {
    let x: i32 = add(20, 22);
    return x;
}
'''


def test_compile_pipeline_no_errors():
    res = compile_source(PROGRAM)
    assert all(d.level != 'error' for d in res.diagnostics)
    assert any('call' in x for x in res.hir)
    assert 'main' in res.asm


def test_type_error_captured():
    src = 'fn main() -> i32 { let a: bool = 1; return 0; }'
    res = compile_source(src)
    assert any('类型不匹配' in d.message for d in res.diagnostics)
