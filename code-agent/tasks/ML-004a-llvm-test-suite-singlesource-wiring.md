# ML-004a: llvm-test-suite SingleSource 纯计算子集布线（ADR-0012 T3 第一片）

**执行环境**: 本地 subagent（组件锁定 + 构建/运行基础设施）

**状态**: 通过（架构师复核，含根因更正）

**前置**：ADR-0012 D4 已定策略（"先跑 SingleSource 纯计算子集，无 libc I/O，只算+返回值，能上 QEMU/gem5 退出码 harness"）；clang 集成（DL-064a/b）+ picolibc 双后端里程碑（本轮 DG-007/DL-066/ML-005/DL-067 全链）均已完成，工具链具备跑真实 C 的能力。

## 背景

`llvm-test-suite`（`github.com/llvm/llvm-test-suite`）目前**完全未接入本仓库**（`manifests/components.lock.toml` 无此组件，未 fetch）。ADR-0012 D4 明确"不用 llvm-test-suite 当近期门槛"，本任务只是开一个小口子：**先证明"能跑通几个最简单的纯计算测试"这条链路本身通**，不是要一次性接完整个 llvm-test-suite。

llvm-test-suite 自带的 CMake/lit 基础设施假设"宿主可执行、有标准 libc、有完整 exit code/stdout 采集"，直接照搬不现实（DADAO 是 freestanding 裸机目标，走 `crt0.s`+`dadao.ld`+QEMU/gem5 退出码约定，不是 host 执行）。**不要尝试直接跑 llvm-test-suite 自己的 CMake 构建系统**——参照本仓库已有的 lit E2E 测试范式（`tests/lit/E2E/*.test`，`%clang --target=dadao ... | %qemu ... | test $? -eq N`）自己写薄封装。

## 做什么

1. **组件锁定**：在 `manifests/components.lock.toml` 加 `[[component]] name="llvm-test-suite"`，选定一个具体 commit（不用 branch/tag），`enabled = true`，`patch_series` 留空或按需（大概率不需要打 patch，只是取源码不编译它自带的 harness）。跑 `make fetch` 确认能拉下来。
2. **挑选纯计算子集**（无 libc I/O，只算+返回值）：从 `SingleSource/Benchmarks/` 或 `SingleSource/UnitTests/` 里挑 **5-10 个最简单的**（比如简单递归/循环/数组类，不依赖 `printf`/`scanf`/文件 I/O、不依赖浮点如果 DADAO 还没有意义好的 FP 支持）。先小规模验证链路，不追求覆盖率。
3. **薄封装构建+运行**：给每个挑中的测试写一个 lit `.test`（仿照 `tests/lit/E2E/*.test` 范式：`%clang --target=dadao -nostdlib ... crt0.o <test>.c -o t.elf` → `%llvm-objcopy` → `%qemu ...` 断言 exit code；已知期望值需要从测试自身逻辑推导，或如果测试有标准"参考输出"就对照；纯计算测试通常有一个可预期的返回值）。可以放在 `tests/lit/E2E/llvm-test-suite/` 子目录，不要和现有 E2E 测试混在一起。
4. **跑通**，如实报告有几个真的端到端跑通（QEMU 先，gem5 视时间/难度补）。**若某个测试因为缺 libc 符号/CodeGen 缺口跑不通，如实记录卡在哪，不要为了"跑通数字好看"而挑绕开所有难点的样例**——目标是验证链路+暴露真实缺口，不是刷通过率。

## 约束

- **不要**尝试接入 llvm-test-suite 自带的完整 CMake/lit 测试基础设施（那是给宿主执行设计的，接不进 freestanding 裸机模型）。
- **不要**为了让某个测试跑通而修改 CodeGen/libc（发现的缺口如实记录成 issue，本任务只是布线+初跑，不做后续修复）。
- 优先级：先 QEMU 跑通，gem5 视时间补（不强制这批测试全双后端，本轮重点是"链路能不能通"）。
- 不回归：E2E 全绿（含 `syscall_hello.test` 已知无关失败）、四方 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200。

## 验收（架构师亲跑）

```bash
cd ~/DADAO-0628
make fetch    # 确认 llvm-test-suite 组件真的拉下来了
llvm-lit tests/lit/E2E/llvm-test-suite/ 2>&1 | tail   # 新增的一批测试的通过情况
llvm-lit tests/lit/E2E/ 2>&1 | tail                    # 全体不回归
python3 tools/run_differential.py 2>&1 | tail -3
```

**判别强调**：至少要有真实跑通（非绕过）的用例，如实报告数量和卡住的用例分别卡在什么问题上（缺 libc 符号 / CodeGen 崩溃 / 其它）；不要为了数字好看而只选最简单能过的样例、回避真实的暴露价值。

## 参考指针

- `docs/adr/0012-test-tiering-strategy.md` §D4（llvm-test-suite 时机与范围）
- `tests/lit/E2E/*.test`（现有 lit 测试的 `%clang`/`%qemu`/`%gem5` 封装范式，直接参考照抄结构）
- `manifests/components.lock.toml`（组件锁定格式，参照 llvm/qemu/gem5 现有条目）
- `scripts/fetch.py`（组件拉取脚本，确认是否需要特殊处理才能支持新组件）
- `tests/scripts/{crt0.s,dadao.ld}`（现有 freestanding 启动/链接脚本，新测试大概率能直接复用）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决）。**如实报告能跑通几个、卡住几个，不要挑软柿子凑数字**。

---

## 架构师复核（2026-07-15，ground-truth）：通过，含根因更正

### 布线本身
- `manifests/components.lock.toml` 加 `llvm-test-suite` 组件、pin 具体 commit（非 branch）；`.work/source/llvm-test-suite`/`gem5` 均确认 clean checkout 在正确 commit（`git status --short` 零输出）。
- 独立重跑：`llvm-lit tests/lit/E2E/llvm-test-suite/` 3/3 PASS（`bitops`/`minint`/`arrayresolution`）；全 E2E 33/34（同一个已知无关的 `syscall_hello.test` 失败）；四方 AGREE(3-way)=200/Sail AGREE(4-way)=200，不回归；`manifest_check.py` PASS。
- 未采用 llvm-test-suite 自带 CMake/lit 基础设施，遵照薄封装范式；未为让测试过而改 CodeGen/libc；5 个跑不通的用例未固化错误值为"预期"、未提交为 lit fixture——遵守约束。

### 根因更正（架构师独立验证）
subagent 把新发现的 miscompile 描述为"函数调用写全局后，调用点对该全局做位运算读到调用前旧值"，并列出多轮排除"调用相关"假设的过程。**架构师用零调用最小复现证明这个定性不成立**：
```c
static int acc = 5;
int main(void) { return acc & 0xFF; }   // host=5  dadao=0（无任何 call）
```
反汇编显示 `ldbu rd31, rb8, 0`——从大端 4 字节 `acc` 的偏移 **0**（最高字节）读单字节，而非低字节所在的偏移 **3**。这是 narrow-load DAG combine 把 `(load i32) & 0xFF` 优化成"直接读最低字节"时，字节偏移选取按小端惯例默认 offset+0、未针对 DADAO 大端调整——与 DL-067b 修复的 BR_CC 大端 narrow-load bug是**同一大类缺陷的另一个独立触发点**，但与"是否发生过函数调用"无关。已更正 `issues.yaml` 的 id/标题/正文（`codegen-global-mask-after-call-miscompile`→`codegen-global-byte-mask-load-wrong-endian-offset`），保留 subagent 的原始发现路径记录（避免抹去有效的调查线索），补充架构师验证的真实根因 + 与 DL-067b 的关联指针，供后续任务参照排查方法直接复用。

**判定**：通过，提交（含 issues.yaml 根因更正）。
