# ML-005a: 解锁 picolibc libc.a 全量重建（jmp_buf + atold_engine 两个缺口）

**执行环境**: 本地 subagent（picolibc 配置 + LLVM backend 排查）

**状态**: 待执行

**前置**：issue `picolibc-libc-rebuild-blocked`（`docs/issues.yaml`）；DG-007b/DL-066a 完成区（gem5 双后端两个真实 bug 已修，但 `printf_hello.test`/`malloc_hello.test` 链接的 `.work/picolibc/build-dadao/libc.a` 是旧编译器预建产物，`my_putc` 间接调用点已固化进旧目标码，需要重建 libc.a 才能让这两个 E2E 用例真正吃到 DL-066a 的修复）。

## 背景（issue 里已记录的两个缺口，直接复用）

`ninja libc.a` 全量重建目前卡在两处**与 DL-066a 无关的既有缺口**：

1. `libc/signal/sigjmp_{setsigs,getsigs}.c`：`../libc/include/setjmp.h` 里 `jmp_buf` 类型未定义，报 "unknown type name 'jmp_buf'"。
2. `libc/stdio/atold_engine.c`（long double 解析引擎）：DADAO backend 在 SelectionDAG legalize 阶段报 "fatal error: unsupported library call operation"（`__atold_engine` 内某个 libcall 未在 `DADAOISelLowering` 实现）。

## 做什么

1. **排查 (1)（jmp_buf）**：确认 DADAO 是否已有 `libc/machine/dadao/` 目录下的 machine 特定头文件（ML-003a 提到"真 setjmp.S(墙②)现为 stub"）。若 `jmp_buf` 只是缺一个 machine-specific 头文件定义（常见做法：一个不透明的定长数组/结构体，字段数覆盖 DADAO ABI 的 callee-saved 寄存器数量），补一个即可——**不需要真正实现 setjmp/longjmp 语义**（那是独立的墙②，本任务只解决"类型能编译"，不是"功能能跑"）。参考其它 picolibc 已支持架构（如 `libc/machine/riscv/`）的 `setjmp.h` 写法。
2. **排查 (2)（atold_engine）**：先确认这是不是**该被排除的编译单元**，而不是需要新实现的 CodeGen 能力——M1 spec 明确排除 RF 浮点扩展（DADAO 无原生浮点单元），`atold_engine.c` 是 `long double` 十进制字符串解析引擎，服务于 `scanf`/`strtold` 类函数。检查 picolibc 的 meson 选项（如 `-Dio-long-double=false`、`-Dtinystdio-strtod=false` 之类）能否直接禁用这个编译单元而不影响 printf/malloc 这两个已验证的目标；若确认这是配置问题，改 `cross-dadao-unknown-elf.txt` 或 `Makefile` 的 `build-picolibc` target 加对应 meson flag，而不是去 `DADAOISelLowering` 里新增 libcall 支持（后者是范围明显更大的新 CodeGen 能力，超出本任务）。
3. 两处都解决后，**真正 `ninja libc.a` 全量重建**，产出干净的、包含 DL-066a 修复后目标码的 `libc.a`。
4. **不要引入新的独立问题**——如果 (2) 排查后发现确实需要新的 libcall CodeGen 支持（而非配置问题），如实报告、不实现，转记为新 issue 交架构师决定是否值得做，不要为了"让 libc.a 编出来"勉强拼凑。

## 约束

- 不改 DADAO CodeGen 去支持浮点 libcall（除非确认 (2) 不是配置问题——若是，先报告，不直接动手，这是"新代码实现"按边界规则该另开任务）。
- `jmp_buf` 头文件只需让类型系统通过编译，不要求真正实现 setjmp/longjmp 跳转语义（那是独立墙②）。
- 不回归：E2E 29/30（含 `syscall_hello.test` 已知无关失败）、四方 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200。

## 验收（架构师亲跑）

```bash
cd ~/DADAO-0628
rm -rf .work/picolibc/build-dadao
make build-picolibc   # 应该干净重建出 libc.a，不再卡在 jmp_buf/atold_engine
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
```

**判别强调**：`libc.a` 用**新编译器**（含 DL-066a 修复）真实重建，不是复用旧产物；反汇编确认新 `libc.a` 里 `vfprintf.o`（或含 `my_putc` 调用点的目标文件）里的间接调用不再用 `rb0` 做 base。

## 参考指针

- `docs/issues.yaml` 的 `picolibc-libc-rebuild-blocked` 条目（两个具体错误信息）
- DL-066a 完成区（本任务要验证的修复内容）
- `.work/picolibc/libc/machine/`（各架构 machine-specific 头文件参考写法，尤其 `setjmp.h` 的常见实现方式）
- `.work/picolibc/libc/stdio/atold_engine.c`（长 double 解析引擎源码）、picolibc 官方 meson_options.txt（确认是否有可禁用它的选项）
- `Makefile` 的 `build-picolibc` target（ML-003l，libc.a 构建入口，若需加 meson flag 改这里）
- `contracts/isa/spec.md`（M1 排除 RF 浮点扩展的范围声明，判断 atold_engine 是否本就不该编译进 M1 目标）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。**必须真跑 `make build-picolibc` 从干净状态重建，不能只改配置没验证真的编出来**。
