# ML-014ab：startup stage2 地址物化的最小阈值与重定位诊断

**执行环境**：本地 subagent worker；承接 ML-014aa 的 startup→main 未命中

**状态**：Complete（已记录/关闭）

## 目标

在不运行 allocator、不中改 LLVM/lld 实现的前提下，找出
`libc_start_main_stage2` 间接调用错误地址的最小代码布局/页边界触发条件，区分
“输入对象中的 relocation/地址物化错误”和“链接后 RELA_PAGE/RELA_LO 计算错误”。

## Ownership

- worker 只写 `.work/ML-014ab-*` 派生 probe/runner/trace 与本 task MD。
- 可使用锁定 clang/lld/crt1/libc.a/script 产生最小 ELF；不得修改实现源码、root
  tests、patches、issues、contracts、manifests 或 ML-014a。
- 不运行 malloc/free 语义验证，不宣称 mallocng 已解决；不查阅或引用
  `~/toolchain`、`~/knowledge-graph`。
- 多人共享仓库，不回滚他人改动；完成后提交本 task MD 及本任务专属 artifacts。

## 执行阶梯

1. 以 ML-014aa/Accepted ML-014y 的 startup layout 为基线，构造尽可能小的
   stage2 地址物化样本；用 object/ELF readobj、反汇编、map/symbol 记录
   `RELA_PAGE`/`RELA_LO`、P、S、A 与最终指令。
2. 通过受控 padding/section 排布或等价最小源程序，让 stage2/调用点跨越相邻
   4 KiB 页及 signed-low 边界；至少保留一个成功布局和一个失败布局。
3. 在 QEMU 与 gem5 各跑一次失败/成功样本，确认动态目标是否分别为预期函数和
   `0x7ffff...` 栈地址；若运行不是必要条件，明确标为静态结论。
4. 给出首个可证明差异、当前最可能的责任层级和下一修复任务边界；不得在本任务
   直接改 linker/compiler。

## 验收

- 至少一对可复现的 success/failure layout，或有充分证据说明无法构成且给出原因。
- 同时保存 relocation decode 与双后端结果；不以 host rc 代替 guest 行为。
- 结论必须区分事实、推断和未决项，并由独立 reviewer 复核。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

## Completion / Closure

### Facts

- All three probes compiled, linked, and converted successfully (`compile=0`,
  `link=0`, `objcopy=0`). The locked-input and runtime-tool comparisons are
  unchanged (`locked_cmp=0`, `runtime_tools_cmp=0`).
- Success layout: `libc_start_main_stage2 = 0x800005ec`, signed low
  `+1516` (`0x5ec`). QEMU reaches `main` at `0x80000110` and exits `42`;
  gem5 reaches the same `main` PC and reports `trap-exit code=42`.
- Failure layout: `libc_start_main_stage2 = 0x80000804`, signed low
  `-2044` (`0x804 - 0x1000`). QEMU repeatedly fetches the wrong target
  `0x7ffff804` and returns `130`; gem5 halts at `0x7ffff804` with code `0`.
- Boundary layout: `libc_start_main_stage2 = 0x80000800`, signed low
  `-2048` (`0x800 - 0x1000`). The artifacts support this as the first
  signed-low boundary: QEMU repeatedly fetches `0x7ffff800` and returns
  `130`; gem5 halts at `0x7ffff800` with code `0`.
- The relocation decode shows relocations in the input `crt1.o` for `main`,
  `_init`, `_fini`, and `__libc_start_main`. The generated success/failure/
  boundary probe objects report empty relocation lists, and the final ELF
  relocation lists are empty in all three cases.

### Exact arithmetic

The materialization behaves as a page base of `0x80000000` followed by a
sign-extended 12-bit low immediate:

```text
success: 0x80000000 + signed(0x5ec) = 0x80000000 + 1516  = 0x800005ec
boundary: 0x80000000 + signed(0x800) = 0x80000000 - 2048 = 0x7ffff800
failure: 0x80000000 + signed(0x804) = 0x80000000 - 2044 = 0x7ffff804
```

Thus the signed-low threshold is raw low `0x800`: values through `0x7ff`
remain positive, while `0x800` and above become negative. For the two
cross-page targets, a compatible rounded target page would make the arithmetic
explicit: `0x80001000 - 0x800 = 0x80000800` and
`0x80001000 - 0x7fc = 0x80000804`.

### Inference

The first proven layout difference is the stage2 low half crossing `0x800`;
the input probe objects do not carry the failing address materialization as
relocations, while the linked instructions do. The most likely responsibility
is linker `RELA_PAGE` handling: it likely needs a rounded target page that is
compatible with the signed `RELA_LO` value. This task records the diagnosis
only; it makes no compiler/linker implementation fix.

### Unresolved

- The exact linker implementation site and whether other `RELA_PAGE` users
  have the same cross-page condition remain for a follow-up fix task.
- This closure does not validate allocator or mallocng semantics.

## 审阅记录

### Independent review（2026-07-19；仅使用既有 artifacts）

**Verdict：Accepted（Finding=0；仅限本任务的 startup stage2 地址物化阈值诊断，不等价于 linker 修复或 allocator/mallocng 完成）。**

- `layout-comparison.txt`、三个 map 和三个最终反汇编彼此一致：`main` 固定为
  `0x80000110`，stage2 分别为 `0x800005ec`、`0x80000800`、`0x80000804`；
  `success.c` 无 padding，`boundary.c`/`failure.c` 的 532/536-byte padding 正好
  形成 `0x800`/`0x804` 两个相邻布局。
- 物化指令记录为同一 `rela rb8, 0` 后接 signed-low `+1516`、`-2048`、
  `-2044`。因此 `0x80000000 + signed(low)` 分别得到
  `0x800005ec`、`0x7ffff800`、`0x7ffff804`；`0x800` 是 12-bit signed-low
  从正数转负数的首个边界。
- `result.txt`、各 `runtime-focus.txt` 及 QEMU/gem5 sidecar 同时提供 guest
  证据：success 两端命中 `main` 并 exit 42；boundary/failure 两端均未命中
  `main`，QEMU 重复取指 `0x7ffff800`/`0x7ffff804` 后为 130，gem5 在相同错误
  地址 halt 为 0，且三组均 `no-timeout`。没有以 host rc 替代 guest 行为。
- `relocation-decode.txt` 正确区分层级：输入 `crt1.o` 有 `main`、`_init`、
  `_fini`、`__libc_start_main` relocations；三个 probe object 与三个最终 ELF
  的 relocation 列表为空。结合最终 `rela`/`addi` 反汇编，这支持“输入对象未携带
  该失败地址物化 relocation、链接后指令呈现问题”的窄结论；RELA_PAGE 责任仍被
  正确标为推断而非已证实现位置。
- `locked-hash-cmp.rc=0`、`runtime-tools-hash-cmp.rc=0`，且 LLVM/QEMU/gem5
  当前 HEAD 与 `baseline-state.txt` 一致；本复核未运行实验、未重编译、未修改
  implementation 或 `.work` 产物。

据此，本任务的 success/failure/boundary 布局、精确 signed-low 算术、输入与最终
relocation 区分、双后端结果及“未改实现”约束均已闭合，判定 **Accepted**。
