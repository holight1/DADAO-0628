# ML-014h：修复 musl `__mmap` 返回链的 pointer ABI bridge

**执行环境**：本地 subagent worker；先证据定位，后最小实现

**状态**：Blocked（2026-07-18；未发现后端 pointer-return bridge 缺陷）

## 背景

ML-014g 已将 ML-014f 缩小到 malloc 返回/首次 dereference 之前：

- gem5：`malloc(131052)` 单独阶段 exit=42，但首次写读访问
  `0xffffffffffff` page-table fault；free 阶段为 MALIGN 129；
- QEMU：malloc-only 阶段返回 11（NULL），后续阶段也未成功；
- ELF 反汇编确认 musl `__mmap` 使用 syscall 222，syscall 返回值先走 `rd31`，
  再由 C wrapper 转成 pointer return；
- ML-014e 的 raw probe 只验证了手写 `rd31 → rd2rb`，不能证明 C wrapper 与两个
  backend 的 pointer return 链一致。

本任务先保证“malloc 返回真实可用地址”基本链路；不在本轮处理 `-O0` workaround
的长期质量，也不先修 `puts` 归档覆盖。

## Ownership

- 允许修改：临时 `.work/ML-014h-mmap-return-bridge/` 探针和报告；必要时修改
  QEMU/gem5 当前工作树中的最小实现，并新增对应
  `components/qemu/patches/0019-*` / `components/gem5/patches/0013-*` 及 series；
  本任务 MD 的完成区和审阅记录。
- 不允许修改：LLVM、musl 源码、`components/musl/patches/series`、contracts、
  manifests、主 musl E2E、`docs/issues.yaml`、ML-014a 原文。
- 不得仅把测试改成 raw probe 来规避 C ABI；必须使用当前 musl `__mmap`/malloc
  产生的真实 pointer return。不得用 `|| true` 或忽略 backend 退出码。
- 只有在反汇编/寄存器观测明确证明后端缺陷时才改后端；若发现是 musl wrapper 或
  archive 构建问题，记录最小 musl-side 修复建议，不越权修改。

## 执行阶梯

1. 复核 `.work/ML-014g-runtime-isolation/stage1.elf` 的 `__mmap`、malloc 调用
   和 pointer return；用最小 C/汇编 bridge probe 对比 QEMU/gem5 的 RD31/RB31
   状态，不依赖 puts。
2. 构造单次 `malloc(131052)` 后只返回/检查指针的判别性程序，再构造首尾写读；
   明确记录每次 syscall 222 的输入和返回值落在哪个 bank。
3. 若确认后端 bridge 缺陷，做最小 QEMU/gem5 修复，分别普通 commit、导出 patch、
   更新 series；新增回归 probe 必须能在两个 backend exit=42。
4. 回归 ML-014g stage1/2/3/4；至少达到两后端 stage1=42、stage2=42，且不引入
   `mmap_backing_probe`、既有 59/59 或 differential 回归。

## 验收

- 报告给出根因证据：具体指令/寄存器 bank/返回值，不得只写“ABI 不一致”；
- 若有实现修改：QEMU/gem5 各自 patch 与 series 可复现，工作树干净；
- pointer-return stage1 和真实首尾写读 stage2 双 backend exit=42；
- ML-014e probe、full E2E 59/59、differential 200/200 不回归；
- 完成区必须有 subagent 自审，随后独立 reviewer 复核。

## 完成区

**状态**：Blocked；诊断已完成，未产生可授权的最小后端修复

**根因证据**：

- 临时 C ABI 探针实际调用当前 musl `mmap`，没有 raw syscall：
  `mmap(NULL, 4096, ...)` 和 `mmap(NULL, 135168, ...)` 均为 QEMU=42、
  gem5=42，判别值均为预期 arena `0x100000000`。
- `.work/ML-014h-mmap-return-bridge/report.md` 的 ELF 反汇编显示 musl
  `__mmap` 的 syscall 返回值先由 `__syscall6` 放在 `rd31`，随后执行
  `rd2rb rb31, rd16, 1`，再 `ret rd0, 0`。这直接证明了真实 C pointer
  return bridge，不是手写 raw probe 绕过 ABI。
- QEMU/gem5 当前 syscall responder 都把 syscall 结果写到 `rd31`，且上述
  direct mmap 在两个后端均成功；因此没有后端缺陷证据，不生成 0019/0013。
- `malloc(131052)` 结果为 QEMU=11、gem5=13；加入首尾写读后为
  QEMU=11、gem5=134，gem5 原始 fault 为访问 `0xffffffffffff`。
- 当前 `.work/build/musl/lib/libc.a` 的成员顺序中，`lite_malloc.o` 是第
  660 个成员，mallocng `malloc.o` 是第 664 个成员；实际 `malloc` 符号
  解析到 lite allocator，而当前 musl 配置声明 `MALLOC_DIR = mallocng`。
  这是 archive/build selection 边界，超出本任务允许的 musl/series ownership。

**修改文件**：

- 仅新增 `.work/ML-014h-mmap-return-bridge/` 临时 C 探针、ELF/bin、运行
  脚本和报告。
- 未修改 QEMU/gem5 工作树，未创建 `components/qemu` 0019 或
  `components/gem5` 0013，未修改任何 patch series。

**验收结果**：

- 真实 `mmap` pointer-return stage：QEMU=42、gem5=42（两个请求尺寸）。
- 真实 `malloc` pointer-return stage：QEMU=11、gem5=13，未通过。
- 真实 `malloc` 首尾写读 stage：QEMU=11、gem5=134，未通过。
- 没有实现修改，因此不宣称 ML-014e、full E2E 59/59 或 differential
  200/200 是本任务修复后的回归结果；既有 ML-014e 的 Accepted 记录保持有效。

**遗留问题**：

- 需要另开、明确授权的 musl build/archive 任务，修正或确认 mallocng
  entry-point 的归档选择；不得在本任务中修改 musl source、主 series 或
  ML-014a。
- archive 边界修复后，重新执行本任务的 C ABI probe；只有真实 mallocng
  pointer return 与首尾访问双 backend 通过后，才继续 ML-014f。

## 审阅记录（subagent）

> 不得把“诊断 probe 通过”写成 ML-014f 已完成；必须记录实现前后真实退出码。

### Subagent 自审（2026-07-18）

- 复核了 `run_probes.sh` 生成的四组 C 输入、compile/link/objcopy 返回码和
  两后端原始退出码；没有使用 `|| true`，`timeout` 语义保持可见。
- 复核了 `mmap_pointer`/`mmap_large` 的真实 musl `__mmap` 调用和
  `rd31 -> rd2rb rb31` 反汇编证据；两个后端均 exit=42。
- 复核了 archive member order 和实际链接符号：失败 malloc 阶段不能归因
  为 QEMU/gem5 pointer bridge，故没有生成 0019/0013，也没有宣称 ML-014f
  完成。
- **自审判决：ML-014h 诊断完成但 Blocked；最小下一步为单独处理归档/构建选择。**

### 独立复核（2026-07-18）

- 以新生成的 `report.md` 为准复核：direct `mmap` 4096/135168 在
  QEMU/gem5 均为 exit=42；`malloc` 为 QEMU=11、gem5=13；malloc 首次
  读写为 QEMU=11、gem5=134，未被误记为通过。
- 独立核对 QEMU `env->rd[31] = ret`、gem5 `setReg(RD_BASE+31, ret)`，以及
  musl `__mmap` 的 `rd2rb rb31` 反汇编；结论是后端 pointer-return bridge
  没有直接缺陷证据。
- 独立核对 QEMU/gem5 工作树干净、两个 patch series 仍停在 0018/0012，
  root 仅保留用户原有 ML-014a 与本任务记录；没有越权修改 LLVM、musl、
  主 series、contracts、manifests、主 E2E、issues 或 ML-014a。
- **独立复核判决：Blocked，Finding=0；ML-014f 和 ML-014a 仍未完成。**

### 独立复核（Codex 二次复核，2026-07-18）

- 独立重跑现有 ELF/bin 探针，未改动源代码或 probe：真实 C `mmap(NULL,
  4096, ...)` 与 `mmap(NULL, 135168, ...)` 均为 QEMU=42、gem5=42；真实
  `malloc(131052)` 为 QEMU=11、gem5=13；真实 malloc 后首尾写读为
  QEMU=11、gem5=134。报告中的四组退出码准确，gem5=134 与
  `0xffffffffffff` page-table fault 一致。
- `mmap` 探针通过 C 声明解析到 musl `__mmap`；musl 源码的返回路径为
  `__syscall` → `__syscall_ret` → pointer return，ELF 反汇编含
  `rd2rb rb31, rd16, 1` 后 `ret rd0, 0`。QEMU 当前 responder 写
  `env->rd[31]`，gem5 当前 trap handler 写 `RD_BASE+31`。因此两个真实
  尺寸的 direct mmap=42 足以排除本任务所针对的 syscall/pointer-return
  backend bridge 缺陷（不宣称覆盖所有未测试的 pointer ABI 场景）；malloc
  失败不能反推后端 bridge 缺陷。
- 独立检查 archive：`libc.a` 第 660 个成员为 `lite_malloc.o`，第 664 个为
  mallocng `malloc.o`；前者导出 `malloc`/`default_malloc`/`__simple_malloc`
  （`malloc` 为 weak），后者导出 `__libc_malloc_impl`。链接 ELF 的 `malloc`
  与 `__simple_malloc`/`default_malloc` 符号链确认实际选中了 lite allocator；
  同时 `.work/build/musl/config.mak` 声明 `MALLOC_DIR = mallocng`。报告关于
  “配置声明 mallocng、实际 archive/link 选择落到 lite”的结论有证据支持，
  根因应转入另行授权的 musl build/archive 任务。
- QEMU、gem5、musl 工作树及项目受限范围均无 diff；QEMU/gem5 series 仍为
  0018/0012，未创建 0019/0013，未修改 `components/musl/patches/series`、
  backend/root series、LLVM、contracts、manifests、主 E2E、issues 或
  ML-014a。ML-014f 与 ML-014a 的未完成状态也未被错误改写。
- **独立复核判决：Blocked / Finding=0；不接受为 ML-014h 实现完成，亦不
  宣称 ML-014f 或 ML-014a 完成。**
