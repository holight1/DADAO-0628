# ML-024a: mallocng size-class（小分配）路径诊断与修复——`malloc(8)` 崩溃/返回 NULL

**执行环境**: 本地 subagent

**状态**: 待处理

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm`、`.work/source/{qemu,gem5,musl}`、`~/DADAO-gem5` 做
  `git rebase`/`git am` 重放整条历史/`git reset --hard` 到早于当前 HEAD 的操作。
  只允许在当前 HEAD 基础上新增普通 `git commit`。
- 本任务是**诊断优先**任务：先把根因摸清楚、用可复现的最小样例证实，再判断是否
  在本任务范围内修。如果诊断后发现修复需要深入 mallocng 分配器算法或后端
  较大改动，**允许停下来如实报告诊断结果+根因假设**，不要为了"完成任务"勉强上
  一个没把握的修复——参照 `ML-020a`/`ML-021a` 的先例（那两个任务都是先诚实报告
  范围边界，而不是强行绕过验收标准）。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。若走"仅诊断不修复"的路线，同样需要完成区+审阅记录，只是完成区写
  诊断结论而非修复方案。

## 背景

`ML-023a`（`code-agent/tasks/ML-023a-mallocng-e2e-real-completion.md`，2026-07-23）
关闭了 mallocng **直接 mmap 路径**（分配 ≥`MMAP_THRESHOLD`=131052 字节）的 E2E
里程碑，但过程中发现一个**不在该里程碑范围内、独立的新缺口**：mallocng 的
**size-class（小对象/slab 池）分配路径**（低于 `MMAP_THRESHOLD` 的分配，走
`.work/source/musl/src/malloc/mallocng/meta.h` 里 `size_classes[]` 数组和
`donate.c`/`malloc.c` 的正常池化逻辑，不是直接 mmap）在当前 HEAD 上有问题。

架构师用两个几乎相同的最小样例复现，**发现结果对测试程序的具体写法敏感**
（这一点本身就值得诊断，不要假设"malloc(8) 就是单纯地总是失败"）：

**样例 1**（只调用 `malloc`，不声明/调用 `free`，不写入返回的内存）：
```c
typedef unsigned long size_t;
void *malloc(size_t);
int main(void) {
    void *p = malloc(8);
    return p ? 42 : 11;
}
```
结果：**QEMU exit=42，gem5 exit=42**（`malloc(8)` 看起来成功，两后端一致）。

**样例 2**（额外声明 `free`，写入+读回校验返回的内存，成功路径调用 `free`）：
```c
typedef unsigned long size_t;
void *malloc(size_t);
void free(void*);
int main(void) {
    char *p = malloc(8);
    if (!p) return 11;
    volatile char *vp = (volatile char *)p;
    vp[0] = 5;
    vp[7] = 6;
    if (vp[0] != 5 || vp[7] != 6) return 12;
    free(p);
    return 42;
}
```
结果：**QEMU exit=11**（`malloc(8)` 这次返回了 NULL），**gem5 exit=129**
（`SIM_END: MALIGN code=129`，硬件对齐故障，不是干净返回）。

两个样例除了"是否声明/调用 free、是否写入返回内存"之外没有其它区别，但结果
从"两后端一致成功"变成"两后端不一致地失败（QEMU 干净返回 NULL vs gem5 直接
故障）"。这个对测试写法的敏感性本身可能就是诊断的重要线索（例如：链接进 `free`
相关代码后二进制布局/relocation 发生变化、或者 mallocng 内部有依赖调用顺序的
全局状态、或者是一个真实的、与访问模式相关的 allocator bug），**不要跳过这个
现象直接去猜一个原因**。

## 目标

1. 独立复现架构师给出的两个样例（自己重新编译/链接/跑，不采信转述），确认现象
   是否可稳定复现。
2. 诊断 size-class 分配路径失败的根因。可能的方向（供参考，不要预设结论，自己
   验证）：
   - mallocng 的 size-class 元数据结构初始化/`donate.c` 的正常池化逻辑是否有
     依赖某个之前只在直接-mmap 路径上验证过、但 size-class 路径上从未验证过
     的机制（比如某种特定寻址模式、某个尚未被最近几个修复覆盖到的 CodeGen
     场景）。
   - QEMU 的"返回 NULL"（相对干净）与 gem5 的"MALIGN 硬故障"（不干净）是同一个
     根因的两种不同表现，还是两个独立的、恰好都在小分配路径触发的不同 bug——
     需要分别追踪，不要假设是同一个原因。
   - 可以用 gdb/`llc`/gem5 debug 输出等手段实际定位到具体是哪条指令/哪次访问
     出的问题，参照 `ML-020a`/`ML-021a` 那种"先用调试转储找到真根因，不要凭代码
     走读猜测"的方法论。
3. 如果根因是**后端/CodeGen 缺陷**且改动范围可控（参照 ML-020a/021a 的"个位数
   文件、几十行以内"量级）：修复并验证。
4. 如果根因在于 **mallocng 分配器算法本身**（比如某个 DADAO 特定的对齐/地址
   空间假设与 mallocng 上游假设冲突）：如实说明，判断是否需要 musl 侧改动，
   同样只在改动范围可控时修，否则停下报告。
5. 修复后（如果修了）：新增一个正式的、覆盖 size-class 路径的 lit 测试
   （建议同时覆盖"只 malloc"、"malloc+读写+free"两种场景，因为架构师的复现表明
   这两种写法的行为可能不同，需要都验证），双后端 exit=42。

## 验收

- 独立复现架构师给出的两个样例，报告实际结果（可能与架构师的结果一致，也可能
  由于并行/环境差异略有不同——如实报告，不要假设一定复现一致）。
- 诊断结论：具体是哪一层（mallocng 算法/musl 集成/LLVM CodeGen/QEMU 或 gem5
  模拟器）出的问题，给出可复现的最小样例和证据（调试转储/反汇编/gdb 输出等）。
- 若修复：新增 lit 测试覆盖 size-class 路径，双后端 exit=42；全量
  `llvm-lit tests/lit/E2E/` 零回归（当前基线 63/63，落地前重新跑一次记录当前值
  为准）；`python3 tools/run_differential.py` AGREE 数与当前基线一致、
  DIVERGE=0；`python3 scripts/manifest_check.py`/`check_issues.py` 通过；改动
  按项目惯例普通 `git commit` + patch 导出 + 追加 series。
- 若仅诊断未修复：在 `docs/issues.yaml` 登记一条新 issue，包含诊断结论、两个
  复现样例、根因假设、建议的后续方向；不算任务失败。
- 不要把本任务的结果误报为"malloc 完全解决"——即使本任务修好了 size-class
  路径，也只是覆盖了 mallocng 的另一半分配路径，不代表 mallocng 所有场景
  （比如更极端的分配模式、多线程——本项目当前是单线程，不用管这个）都已覆盖。

## 参考指针

- `code-agent/tasks/ML-023a-mallocng-e2e-real-completion.md` 完成区（本任务
  发现的缺口出处，direct-mmap 路径的对照参考）
- `.work/source/musl/src/malloc/mallocng/meta.h`、`malloc.c`、`donate.c`
  （size-class 分配逻辑，`size_classes[]` 数组、`MMAP_THRESHOLD=131052`）
- `code-agent/tasks/ML-020a-f64-softfloat-libcall-vfprintf.md`、
  `code-agent/tasks/ML-021a-direct-call-glue-chain-multicall-block.md`
  （"先用调试转储找到真根因，不要凭代码走读猜测"方法论的参照先例）
- `docs/issues.yaml`（若登记新 issue，检查现有 `musl-backend-*` 系列条目的
  命名/格式约定）
- `tests/lit/E2E/musl_malloc_printf.test`（direct-mmap 路径的现有测试范式，
  含 `volatile` 校验的踩坑记录，见 [[feedback-volatile-needed-for-memory-verification-tests]]
  同类教训——本任务新测试如果涉及写读回校验也要用 `volatile`）
- `.work/build/musl/lib/{crt1.o,libc.a}`（`make build-musl` 重新生成）
- `tests/scripts/dadao.ld`（链接脚本，必须用它才能跑得起来）
