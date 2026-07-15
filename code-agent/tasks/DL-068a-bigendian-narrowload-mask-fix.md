# DL-068a: 修复大端窄字节 load 偏移错误（`x & 0xFF` 类掩码读到错误字节）

**执行环境**: 本地 subagent（LLVM DAG combine 修复，大端字节序）

**状态**: 待执行

**前置**：issue `codegen-global-byte-mask-load-wrong-endian-offset`（`docs/issues.yaml`），架构师已用零调用最小复现定位并附反汇编证据。ML-004a 发现症状，架构师纠正根因定性（与函数调用无关）。DL-067a/b 是同一大类"大端 narrow-load"问题的先例（那次是分支条件，这次是直接返回值/掩码表达式），排查方法可直接复用。

## 现象（架构师已复现，直接复用）

```c
static int acc = 5;
int main(void) { return acc & 0xFF; }
```
`gcc -O0`（host，小端）：exit=5（正确）。
`clang --target=dadao -O0`（DADAO，大端）：exit=0（错误，应为 5）。

反汇编（`llvm-objdump -dr --triple=dadao`）：
```
rela rb8, 0        ; rb8 = page(acc)
addi rb8, rb8, 0   ; rb8 += offset(acc)
ldbu rd31, rb8, 0  ; 从 rb8+0 读 1 字节 unsigned  ← 问题所在
```
`acc=5` 在 DADAO 大端布局下的 4 字节表示是 `00 00 00 05`（偏移 0→3）。`ldbu ..., 0` 从偏移 **0** 读，取到最高字节 `0x00`；真正的最低有效字节（`x & 0xFF` 想要的）在偏移 **3**。这是 LLVM 通用 `ReduceLoadWidth` 类 DAG combine 把 `(load i32) & 0xFF` 优化成"直接读最低有效字节"时，字节偏移的计算按小端惯例默认用 `offset+0`，没有针对大端目标做调整（大端下最低有效字节应该在 `offset + (原始宽度 - 窄化后宽度)`，即本例 `offset+3`）。

**与 DL-067b 的关系**：DL-067a/b 修复的是"大端场景下 narrow-load 产出的窄类型操作数流入自定义 `BR_CC` 节点、类型合法化钩子缺失导致 fatal error"——那次的根因是"钩子缺失崩溃"，不是"字节选错"。本次现象是"能正常编译执行，但选错了字节、结果错误"（更隐蔽的 silent miscompile，非 crash）。**这次触发路径大概率是另一个 DAG combine**（很可能还是 `ReduceLoadWidth` 或相关的 load-narrowing 优化，但产出的路径这次没有流经自定义节点，直接生成了 `ldbu`），需要确认具体是哪个 combine、以及 DADAO target 的字节序信息（`DataLayout::isBigEndian()`）在这条路径上有没有被正确查询/使用。

## 做什么

1. 用 `-debug-only=dagcombine`（DL-067a 已验证过的方法论）追踪 `return acc & 0xFF;` 这个最小复现的 DAG combine 过程，确认具体是哪个 combine（`ReduceLoadWidth`/`reduceLoadWidth`/其它命名）产出了错误偏移的窄 load，以及它在计算字节偏移时是否查询了 `isBigEndian()`（或 DADAO target 是否正确报告自己是大端——若 target 描述本身有误也要指出）。
2. 定位后修复：让这条 combine 路径为大端目标正确计算窄化 load 的字节偏移（应为 `原地址 + (原宽度字节数 - 窄化宽度字节数)`，不是恒定的 `+0`）。**优先检查这是不是 LLVM 通用（target-independent）DAG combine 代码里本来就该处理大端但目标描述缺了某个信息**，而不是假设需要在 DADAO 后端另写一个绕过；若确实是 DADAO target 描述缺失（比如某个 `TargetLowering` hook 没有正确暴露字节序信息），修那个钩子。
3. **验证**：
   - 零调用最小复现 `return acc & 0xFF;` 在 DADAO 上正确返回 5（不只是"不崩溃"，值要对）。
   - 补充判别性探针：不同的窄化宽度（`& 0xFF`/`& 0xFFFF`）、不同的初始值（含高位非零，如 `0x12345678 & 0xFF` 应为 `0x78`）、全局变量与栈变量都测一遍，双后端跑出正确值。
   - ML-004a 里因这个 bug 跳过的 5 个 llvm-test-suite 用例（`crc8.le`/`crc16.be`/`popcount-clz-ctz`/`divrem loop`/`divtest`，源码在 `.work/source/llvm-test-suite`）重新尝试，如实报告修复后能跑通几个（可能还有其它独立缺口，不强求全部通过，但至少应该有所改善）。
4. **确认不影响 DL-067b 已修的 BR_CC 场景**（`align_strfn.test` 等既有大端相关回归必须继续通过）。

## 约束

- 不要为了让 `return acc & 0xFF;` 这一个具体形态过而打局部补丁——要修通用的字节偏移计算逻辑。
- 若这条 combine 是 LLVM target-independent 代码（多数 target 共享），确认修改不会破坏其它已知工作正常的场景（不必展开测试其它 target，但要理解你改的是不是被广泛复用的代码路径，若是要格外谨慎不要引入行为变化影响小端目标）。
- 不回归：E2E 全绿（含 `syscall_hello.test` 已知无关失败）、四方 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200、`align_strfn.test`（DL-067b 回归）。

## 验收（架构师亲跑）

```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang
# 零调用最小复现验证
cat > /tmp/mask_verify.c << 'CEOF'
static int acc = 5;
int main(void) { return acc & 0xFF; }
CEOF
.work/build/llvm/bin/clang --target=dadao -nostdlib -ffreestanding -O0 -c /tmp/mask_verify.c -o /tmp/mv.o
# 链接+跑，确认 exit=5
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
```

**判别强调**：最小复现返回值真正正确（=5，非仅"不崩溃"）；补充的多组判别性探针（不同掩码宽度/不同初值/含高位非零）双后端值都对；E2E/四方不回归；ML-004a 跳过的用例重新尝试并如实报告结果。

## 参考指针

- `docs/issues.yaml` 的 `codegen-global-byte-mask-load-wrong-endian-offset` 条目（完整反汇编证据 + 根因分析）
- DL-067a 完成区（`-debug-only=dagcombine` 追踪方法论，同类大端 narrow-load 问题的排查范例）
- ML-004a 完成区 + `tests/lit/E2E/llvm-test-suite/`（已布线的测试基础设施，跳过的 5 个用例源码在 `.work/source/llvm-test-suite`）
- `tests/lit/E2E/align_strfn.test`（DL-067b 回归测试，验证本次修复不破坏它）
- LLVM 通用 `SelectionDAG.cpp`/`DAGCombiner.cpp` 的 `ReduceLoadWidth` 相关代码（若确认是 target-independent 路径）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。**必须验证修复后的值真正正确，不能只验证"不崩溃"或"编译通过"**。
