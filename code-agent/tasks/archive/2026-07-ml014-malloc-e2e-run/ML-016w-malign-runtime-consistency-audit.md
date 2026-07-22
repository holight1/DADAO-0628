# ML-016w：MALIGN 129 runtime consistency audit

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：23/30）

## 背景

ML-016v 的 partial archive + puts ELF 已通过 compile/link/undefined/objcopy，但现有
QEMU/Gem5 bare-metal 入口均无 timeout、以 rc=129 结束；Gem5 明确为 `MALIGN code=129`，
无 puts marker。需要按既有一致性检查方案审计，不把失败入口误当作有效用户态测试，也
不擅自修改 spec、vectors、tests 或 wiki。

## 目标与 ownership

worker 只读审计：

1. 核对 ML-016v 的 ELF/BIN、linker script、entry、load segment、stack/alignment、
   syscall/console 配置和 QEMU/Gem5 argv；保存 readelf/objdump/map/sha256 与 raw
   runtime rc/stderr/stdout。
2. 对照仓库已有、已被规范/契约接受的 QEMU/Gem5 bare-metal fixtures/launcher，确认
   `MALIGN 129` 的分类和退出码语义；检查是否把 partial archive user ELF 错接到
   仅适用于裸机 fixture 的入口。不要引入新测试或修改现有测试。
3. 将失败边界拆成 ELF/ABI/linker、launcher/firmware、runtime syscall/console、
   malloc/stdio 或测试入口问题；只给证据支持的下一步任务，不直接修复。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016w-malign-runtime-consistency-audit-20260721.md`；
  额外只读输出放 `/tmp/ml-016w-malign-runtime-consistency-audit-20260721/`。
- 不修改 LLVM、musl、主 archive、QEMU/Gem5、contracts、vectors、issues、wiki、ML-014a
  或任何测试/规范文件；不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不使用 `|| true`；不把 rc=129 或 no marker 改写成 PASS，不新增测试。

## 完成区

### worker 交付（2026-07-21）

状态：**Completed / Final classification：Confirmed runtime syscall/ABI stack-alignment MALIGN；不实施修复**。

全部新增证据只写入 [`/tmp/ml-016w-malign-runtime-consistency-audit-20260721/`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/)。没有修改 LLVM、musl、主 archive、build/QEMU/Gem5、contracts、vectors、issues、wiki、ML-014a 或任何测试/spec；没有回滚其他改动。

#### 结论

- ML-016v 的同一 ELF/BIN/map 已复制并逐项核对：ELF SHA-256 为 `f7844c487c3b601a3a03357be0ecd879e1ace8016d473194c14f6d0b20575ccd`，BIN 为 `ead17191ca0a88ff4e944811a0c94193bee561c46a285ee33f650e7e49cd82f0`，map 为 `0e1b9fa6a93ffbf3d00a455d21c8515305d74e6a53c16008a196291fafe6ca24`；与 ML-016v 原始文件 `cmp=0`。
- `llvm-readobj`/host `readelf`：ELF64 big-endian、`ET_EXEC`、machine `0xDA0`、entry `0x80000000`、无 relocation；两段 `PT_LOAD` 为 RX text/rodata 和 RW data/bss/heap。`.heap` 的 `[0x80005000,0x87e00000)` 段覆盖有证据；stack 是 launcher/fixture 另行提供的运行时区域，不能仅因不属于 image PT_LOAD 就判定 loader 错误。
- linker script 为 `ENTRY(_start)`，`PT_LOAD`/section 布局与仓库标准 `tests/scripts/dadao.ld` 一致；ML-016v 副本与仓库文件 hash 相同。QEMU argv 使用该 BIN + trampoline，Gem5 argv 直接使用同一 ELF + `dadao_se.py`；没有发现入口、`-bios/-kernel`、direct-ELF 或 argv 错接。
- accepted fixture 与 ML-016v user ELF 的差异已明确：accepted `syscall_hello` 是 raw `_start` 直接执行 `trap` write/exit，accepted musl return/auxv fixture 使用已验证的 startup/exit object 路径；它们的 launcher transport 是 QEMU `trampoline + flat BIN`、Gem5 `direct ELF`，并严格断言正常 rc `42`/`0` 后再检查 marker。ML-016v 使用相同 transport 形态但不是同一个 fixture：它把 partial `libc` 的 `puts.o`、`exit.o`、`_Exit.o` 链进 user ELF；其 `_Exit` 走 generic `__syscall1`，在真正 `trap` 前于 `0x80001040` 触发 MALIGN。因此差异在被加载 user ELF 的 startup/exit 内容与退出语义，不在 launcher argv。
- 栈对齐静态链成立到 `exit`：trampoline 约定初始 `rb1=0x87ff0000`，`_start` 减 `160`、`_start_c` 减 `24`、`exit` 减 `16` 都保持 8 对齐。但 ML-016v ELF 的 `_Exit` (`0x8000100c`) 先减 `4`，再调用 `__syscall1` (`0x8000103c`)；`__syscall1` 再减 `40` 后于 `0x80001040` 执行 64-bit `sto rd16, rb1, 32`，该 EA 保持 `4 mod 8`，构成确定的 MALIGN。
- QEMU debug trace 进入 `0x80001040` 后停止；Gem5 raw Exec trace 最后记录为前一条 `0x8000103c`，但静态 objdump 的下一条 `0x80001040` store、Gem5 `MALIGN code=129` 和两端 rc 共同支持同一窄 fault 分类。两端原始 runtime 均 `rc=129`、无 timeout。`trap 2,0` 位于 `0x80001060`，尚未到达，因此本轮不能把 `129` 归因到 syscall fd/console responder。
- QEMU/Gem5 fault 定义及既有 harness 均把 MALIGN 编码为 `0x81`，即十进制 `129`。已接受 fixtures 对正常用户程序严格断言 `42` 或 `0` 并独立检查 marker；因此 ML-016v 的 `129` 是 MALIGN fault，不是 `main` 返回值语义，也不是 PASS。

#### Findings 与未确定项

1. **Confirmed：当前 partial archive 选入的 `_Exit`/generic `__syscall1` 路径存在栈对齐 fault。** 这是双 backend 一致的第一确认 fault，范围属于 linked runtime syscall/ABI frame，不是 ELF entry/load/launcher argv mismatch。
2. **Evidence-backed candidate：** 已接受 `musl_e2e_exit` ELF 的 `_Exit` 是直接 `trap 2,0` 路径并以 `trap-exit code=42` 结束；ML-016v map 则明确拉入 `exit.o`/`_Exit.o` 的 generic wrapper。两者差异支持后续优先审计 `_Exit` frame/prologue 与 syscall wrapper ABI，但本轮不决定具体源码归属。
3. **Undetermined：** syscall/console 在修复对齐前的实际返回/输出行为；`puts` marker 缺失是否还有独立 stdio buffering/flush 原因；以及应由 musl `_Exit`、CodeGen frame lowering 还是 ABI contract 修复。ML-016v 仍不是 runtime 或高层 puts acceptance。

#### 最终分类

**Confirmed：ML-016v user ELF 的 linked runtime syscall/ABI stack-alignment fault（MALIGN `0x81` = decimal `129`）。**

- **不是** ELF header/entry/load segment/linker script 错误；这些检查均有正向 evidence。
- **不是** accepted bare-metal fixture 的 launcher 误接；QEMU/Gem5 argv 与既有 transport 一致，但 accepted fixture 的 user code/startup/exit object 组合不同。
- **不是** 正常 `main` 返回码：ML-016v `main` 返回 `42`，而 `129` 是两后端共同报告的 MALIGN fault。
- **仍未确定** syscall responder/fd/console 在越过 fault 后的行为，以及 puts flush 是否存在第二个独立问题。

原始 readelf/objdump/map/sha256、ELF/BIN、linker/trampoline、launcher argv、QEMU/Gem5 rc/stdout/stderr 与 debug trace 均保留在 evidence root；汇总 review 见 [`docs/reviews/ML-016w-malign-runtime-consistency-audit-20260721.md`](../../docs/reviews/ML-016w-malign-runtime-consistency-audit-20260721.md)。

独立 reviewer Epicurus the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016w-independent-review-20260721.md`。review 要求将 Gem5 fault
PC 表述收窄为 raw trace 到 `0x8000103c`、静态下一条为 `0x80001040`，并明确部分
readelf 命令 rc=127；核心 MALIGN 分类不变。
