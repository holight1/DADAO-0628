# DL-065a: 根因定位 + 修复 — `-O1+` call 隐式寄存器范围溢出

**执行环境**: 本地 subagent（LLVM CodeGen，call lowering 修复）

**状态**: 通过（架构师复核，含 issues.yaml 收尾）

**前置**：issue `dadao-oz-undef-physreg`（`docs/issues.yaml`），架构师已复现并附 MIR 证据。

## 现象（架构师已复现，直接复用）

```bash
cd ~/DADAO-0628
.work/build/llvm/bin/clang --target=dadao -nostdlib -nostdinc -ffreestanding -O1 -c \
  -I.work/picolibc/libc/include -I.work/picolibc/libc/stdio -I.work/picolibc/libc/locale \
  -I.work/picolibc -I.work/picolibc/build-dadao -I.work/build/llvm/lib/clang/22/include \
  -D_LIBC -DNEWLIB_NANO_MALLOC .work/picolibc/libc/argz/argz_insert.c -o /tmp/argz_o1.o
```
`-print-after-all` MIR dump 显示（`argz_insert` 函数）：
```
Function Live Ins: $rd16 in %10, $rd17 in %11, $rd18 in %12, $rd19 in %13
...
CALL_IIII @argz_add, <regmask ...>, implicit-def $rd31, implicit $rd16,
  implicit killed $rd17, implicit killed $rd18, implicit killed $rd19,
  implicit killed $rd20, implicit killed $rd21, implicit killed $rd22,
  implicit killed $rd23, implicit killed $rd24, implicit killed $rd25,
  implicit killed $rd26, implicit killed $rd27, implicit killed $rd28,
  implicit killed $rd29, implicit killed $rd30
```
该函数只有 4 个真实参数（`rd16`/`rd17`/`rd18`/`rd19`），但 `CALL_IIII` 的隐式使用列表把 `rd20`-`rd30` 也标进去——这些寄存器在函数内从未被定义/赋值过。**`-O1` 下 `ninja libc.a` 会在这类调用点上报 "Bad machine code: Using an undefined physical register"（历史记录约 63 处）**；`-O0` 未曾报告过此错误（尚不确定是 MachineVerifier 在 `-O0` 未运行，还是别的原因，需本任务确认）。

## 做什么

1. 定位是哪段代码往 `CALL_IIII`/`CALL_RRII` 之类指令上添加了这批"多余"的隐式寄存器（`DADAOISelLowering.cpp:84` 的 `LowerCall` 是首要嫌疑，尤其是构造 outgoing-argument glue/隐式 use 列表的部分——参照标准 LLVM target 的 `LowerCall` 通常只应该为**实际传参数量对应的寄存器**添加 `RegsToPass`/隐式 use，不应该覆盖整个参数寄存器范围）。
2. 确认为什么 `-O0` 不报错（是否 `-O0` 跳过了 `MachineVerifier`，还是 `-O0` 走了不同的 lowering 路径没触发这个多余列表的构造）。
3. **修复**：让隐式寄存器列表按实际参数数量精确构造，不多不少覆盖真正传递的参数寄存器（含返回值 `rd31`/`implicit-def` 那部分若也有类似问题一并核实）。
4. **验证**：
   - `argz_insert.c`（及 issue 提到的约 63 处报错点）在 `-O1` 下不再报 "undefined physical register"。
   - 真实调用场景运行时正确（构造一个多参数函数调用的真实 C 程序，`-O1` 编译，双后端跑出正确结果——不能只验证"编译不报错"，要验证调用约定本身没被这次改动破坏，比如参数没传错、返回值没读错）。
   - 现有 `-O0` 场景不受影响（E2E 测试全部是 `-O0` 建的，理论上此次改动只影响 `-O1+` 的隐式列表构造，不应该动到 `-O0` 路径，但需要验证）。

## 约束

- 不要用"只在 `-O0` 建 libc.a"这种既有的绕过继续下去——这正是本任务要解决的墙。
- 不回归：E2E 全绿（含 `syscall_hello.test` 已知无关失败）、四方 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200。
- 若发现问题比预想的更深（比如不只是隐式寄存器列表构造，还涉及别的 `-O1+` pass 的问题），如实报告根因范围，不要为了"让 argz_insert.c 编过"打局部补丁掩盖更大的结构性问题。

## 验收（架构师亲跑）

```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang
.work/build/llvm/bin/clang --target=dadao -nostdlib -nostdinc -ffreestanding -O1 -c \
  -I.work/picolibc/libc/include -I.work/picolibc/libc/stdio -I.work/picolibc/libc/locale \
  -I.work/picolibc -I.work/picolibc/build-dadao -I.work/build/llvm/lib/clang/22/include \
  -D_LIBC -DNEWLIB_NANO_MALLOC .work/picolibc/libc/argz/argz_insert.c -o /tmp/argz_o1_fixed.o
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
```

**判别强调**：`argz_insert.c` 在 `-O1` 下真正编过（非只是不崩溃，要确认没有偷偷降级成 `-O0` 等价物）；真实多参数函数调用在 `-O1` 双后端跑出正确结果；E2E/四方不回归。

## 参考指针

- `docs/issues.yaml` 的 `dadao-oz-undef-physreg` 条目（完整 MIR 证据）
- `.work/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（`LowerCall`，约第 84 行起）
- DL-066a 完成区（本 session 另一个 call-lowering 类的修复案例，可参考排查方法论——都是"隐式寄存器/base 寄存器设置错误"这一类问题）
- ML-003a 完成区（此 issue 最初的发现记录）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。**必须用真实多参数调用的运行时探针验证 `-O1` 调用约定语义正确，不能只验证"编译不报错"**。

---

## 架构师复核（2026-07-14，ground-truth）：通过

### 技术修复
- diff 审阅：`DADAOInstrInfo.td` 去掉 `CALL_IIII`/`CALL_RRII`/`CALL_PSEUDO_INDIRECT` 的静态 `Uses=[RD16..RD30]`；`LowerCall` 按 `RegsToPass` 显式压 `DAG.getRegister()` 操作数；`DAGToDAG::Select()` 原样带过（排在 Chain/Glue 前，符合 `InstrEmitter::AddOperand` 顺序约定）——标准 LLVM 模式（对标 RISCV），合理。
- 独立重建验证：`argz_insert.c -O1` 真编过（`.s` 113 行 vs `-O0` 的 181 行，非静默降级）；`-O0` 不受影响；全 E2E 30/31、四方 AGREE(3-way)=200/Sail AGREE(4-way)=200 不回归。

### 收尾修正（subagent 遗漏，架构师直接补齐）
subagent 完成区声称更新了 `issues.yaml`（关闭 `dadao-oz-undef-physreg`、登记新 tail-call issue），但实际未改动该文件——**已由架构师直接补上**：
1. 关闭 `dadao-oz-undef-physreg`（`resolved_by: DL-065a`）。
2. 登记新 issue `codegen-tailcall-lowercall-assert`（subagent 报告的诚实发现：963 文件 `-O1` 扫描后仍有 113 个撞上独立的 "LowerCall emitted a return value for a tail call" 断言——`LowerCall` 从未实现 tail-call opt-out；与本任务无关，正确未修复）。

**过程中意外发现并修复一处更早的真实文档缺陷**：本次编辑 `issues.yaml` 时用未加引号的长 `resolved_by` 值（含内嵌 `"..."`）触发 YAML 解析异常，追查后发现**本 session 更早注册 `dadao-oz-undef-physreg` 时（commit 8d25bf5）就已经把 `wiki-9f378f4-sbi-see-deferred-delta` 的 `- id:` 行误删**——YAML 把该条目的 `title`/`status`/`scope`/`blocks`/`resolved_by` 当成前一个条目的重复 key 静默吸收（`yaml.safe_load` 默认"后者覆盖前者"不报错），`check_issues.py` 只做浅层字段检查不查重复 key，故此前多次运行均"PASS"却未发现。已修复（补回缺失的 `- id:` 行）+ **加固 `scripts/check_issues.py`**：自定义 `DuplicateKeyLoader` 覆写 `construct_mapping`，同一映射内出现重复 key 直接抛错（已用故意构造的相同损坏模式验证：确实会 FAIL 并给出清晰诊断）。

**判定**：通过，提交（含本次 issues.yaml 结构性修复 + `check_issues.py` 加固）。
