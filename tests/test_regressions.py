from nexa.compiler import compile_source


def test_select_default_nonblocking_with_vm_run():
    src = '''
fn main() -> i32 {
  let ch: Chan[i32] = chan(1);
  let x: i32 = select { recv(ch) => { 1; } default => { 7; } };
  return x;
}
'''
    res = compile_source(src, mode='full', run=True)
    assert all(d.level != 'error' for d in res.diagnostics)
    assert res.run_value == 7


def test_macro_gensym_avoids_capture():
    src = '''
macro make_tmp(v) { let x: i32 = v; }
fn main() -> i32 {
  let x: i32 = 1;
  make_tmp(2);
  return x;
}
'''
    res = compile_source(src, mode='full', run=True)
    assert all(d.level != 'error' for d in res.diagnostics)
    assert res.run_value == 1


def test_generic_conflict_reports_error():
    src = '''
fn same[T](a: T, b: T) -> T { return a; }
fn main() -> i32 { let x: i32 = same(1, true); return x; }
'''
    res = compile_source(src, mode='full')
    assert any('泛型实参冲突' in d.message or '参数类型不匹配' in d.message for d in res.diagnostics)


def test_cfg_has_true_and_false_paths():
    src = 'fn main() -> i32 { let a: i32 = 1; if a > 0 { a = a + 1; } else { a = a + 2; } return a; }'
    res = compile_source(src, mode='core')
    rows = '\n'.join(res.cfg['main'])
    assert 'succs=' in rows
    assert 'br.true' in rows


def test_parser_recovery_continues_after_missing_semi():
    src = 'fn main() -> i32 { let a: i32 = 1 let b: i32 = 2; return b; }'
    res = compile_source(src, mode='core')
    assert any('缺少分号' in d.message for d in res.diagnostics)
    # still lowers second declaration/return
    assert any('mov.i32' in line for line in res.hir_opt)
