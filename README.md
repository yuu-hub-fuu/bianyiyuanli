# Nexa Compiler Project

## 快速开始

```bash
python -m pip install pytest
python nexa_cli.py example.nx --mode core --dump tables
python nexa_cli.py example.nx --mode full --dump all --export-dir out
pytest -q
```

## 验收输出（CLI）

`--dump tables` 或 `--dump all` 明确输出：

- 关键字表
- 界符表
- 标识符表
- 常量表
- 符号表
- 四元式表（HIR）

## 模式

- `--mode core`：课程基础模式（变量、表达式、if/while、符号表、四元式）。
- `--mode full`：高分模式（宏展开、泛型推断、select/通道、可视化导出）。

## 图形界面

```bash
python -m nexa.ide.app
```

界面包含：源码区、Token/AST/Symbol/HIR/CFG/ASM/Timeline 多 Tab、诊断区。

## 可视化导出

编译时会输出 DOT 文件：

- `out/ast.dot`
- `out/cfg_<fn>.dot`

安装 `graphviz` Python 包后会自动生成对应 SVG 文件。
