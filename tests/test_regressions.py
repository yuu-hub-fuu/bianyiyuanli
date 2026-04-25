from nexa.compiler import compile_source
from nexa_cli import _write_html_report


def test_select_default_nonblocking_with_vm_run_and_default_body_effect():
    src = '''
fn main() -> i32 {
  let ch: Chan[i32] = chan(1);
  let x: i32 = select { recv(ch) => { 1; } default => { print(0); 7; } };
  return x;
}
'''
    res = compile_source(src, mode='full', run=True)
    assert all(d.level != 'error' for d in res.diagnostics)
    assert res.run_value == 7
    assert '0' in res.run_stdout


def test_select_recv_body_value_overrides_received_value():
    src = '''
fn main() -> i32 {
  let ch: Chan[i32] = chan(1);
  send(ch, 42);
  let x: i32 = select { recv(ch) => { 99; } default => { 0; } };
  return x;
}
'''
    res = compile_source(src, mode='full', run=True)
    assert all(d.level != 'error' for d in res.diagnostics)
    assert res.run_value == 99


def test_macro_gensym_avoids_capture_nested_let():
    src = '''
macro make_tmp(v) { if true { let x: i32 = v; } }
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


def test_runtime_errors_are_reported_not_crash():
    src = 'fn main() -> i32 { let a: i32 = 1 / 0; return a; }'
    res = compile_source(src, mode='core', run=True)
    assert any('运行时错误' in d.message for d in res.diagnostics)
    assert any('runtime error' in line for line in res.run_stdout)


def test_vm_trace_available_when_enabled():
    src = 'fn main() -> i32 { let a: i32 = 1 + 2; return a; }'
    res = compile_source(src, mode='core', run=True, trace=True)
    assert res.run_value == 3
    assert len(res.vm_trace) > 0
    assert any(fr.instr.startswith('ret') for fr in res.vm_trace)


def test_html_report_writer(tmp_path):
    src = 'fn main() -> i32 { return 0; }'
    res = compile_source(src, mode='core')
    out = tmp_path / 'report.html'
    _write_html_report(out, res)
    txt = out.read_text(encoding='utf-8')
    assert 'Nexa 编译报告' in txt
    assert 'Timeline' in txt
