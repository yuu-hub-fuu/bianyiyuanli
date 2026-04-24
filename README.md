# Nexa Compiler Project

## 快速开始

```bash
python -m pip install pytest
python nexa_cli.py example.nx --dump all
pytest -q
```

## 功能覆盖

- 手写词法分析器（关键字、界符、字符串、注释、诊断）
- 递归下降 + Pratt 语法分析
- 符号表与类型检查
- 带类型四元式 HIR
- CFG 化 MIR
- 常量折叠 + DCE
- 线性扫描寄存器分配
- 教学型 x86-64 文本发射
- LLVM IR 生成（可选 llvmlite 对象发射）
- 简易通道与任务运行时
- CLI 与教学 IDE

详细任务映射见 `docs/12周任务实现说明.md`。
