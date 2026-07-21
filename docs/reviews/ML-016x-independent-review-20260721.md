# ML-016x 独立 reviewer 报告

日期：2026-07-21  
角色：独立 reviewer；未实现修复

## 结论

**Accepted-with-findings**。

核心诊断可接受：证据确实把失败从 syscall/trap 本身收窄到 callee frame 的 `-4`
导致的栈余数变化；当前没有阻塞性 finding。以下两个 finding 都是证据措辞/复跑
身份链问题，不改变本次归因结论。

## 审阅边界

已复核：

- [任务说明](../../code-agent/tasks/ML-016x-exit-syscall-frame-repro.md) 与
  [待审报告](ML-016x-exit-syscall-frame-repro-20260721.md)；
- 报告引用的 musl、LLVM frame-lowering 源文件，以及
  [ABI spec](../../contracts/abi/spec.md)；
- `/tmp/ml-016x-exit-syscall-frame-repro-20260721/` 下的 probe、disassembly、MIR、
  hash、命令日志、QEMU/Gem5 结果和 raw trace。

没有修改生产源、musl、测试、launcher、规范或构建产物；本文件是唯一新增文件。

## 阻塞 findings

无。

## 非阻塞 findings

### NB-1：摘要中的 faulting-store wording 略越过 QEMU trace 能直接证明的范围

待审报告摘要把路径写成“`first 64-bit sto -> MALIGN 129`”（[报告:11–20](ML-016x-exit-syscall-frame-repro-20260721.md:11)）。QEMU 的
`-d exec,in_asm` 原始文件确实从 `0x80000038` 的 block 进入 `0x8000003c` 的
store block 并重复（[qemu trace](/tmp/ml-016x-exit-syscall-frame-repro-20260721/runtime/qemu-debug-exit/exec.trace:27)），但该 trace 本身
不提供 faulting instruction 完成语义。Gem5 trace 的最后动态记录是
`0x80000038 @__syscall1 : addi.rb`，下一条 `0x8000003c` store 只由静态
disassembly 对应出来（[gem5 trace](/tmp/ml-016x-exit-syscall-frame-repro-20260721/runtime/gem5-debug-exit/exec.trace:10)）。

报告后文已经正确保留了这个边界（[报告:135–143](ML-016x-exit-syscall-frame-repro-20260721.md:135)），因此不阻塞。建议摘要统一写成“进入/停留在 faulting-store block，MALIGN 发生在 trap 之前”，把实际 faulting instruction 标成静态映射或推断。

### NB-2：复跑所用 launcher 路径有效，但 launcher identity 未纳入 x 证据 hash

所有 QEMU argv 使用 `/tmp/ml-016w-malign-runtime-consistency-audit-20260721/launcher/ml-016v-trampoline.bin`（例如
[qemu argv](/tmp/ml-016x-exit-syscall-frame-repro-20260721/logs/qemu-debug-exit.argv:1)）。该路径当前存在，文件为 32 bytes，hash 为
`44042fabb2741724828443d7ae13bd42e3931e88d8be7f2f7dc48be3d851f5e0`；因此不是
当前复核中的 missing/stale path，也没有证据表明它污染了结果。QEMU launcher key-lines
明确其 `-bios`/`-kernel` 关系，且 trampoline 的 `0x87ff0000` 初始 SP 与 8-byte
对齐一致；Gem5 的 SE stack base 也为 `0x00007ffffffff000`。

不过该 launcher hash 没有写入 ML-016x 证据目录或待审报告，独立复跑者无法仅凭 x
目录闭合 binary identity。建议在后续报告的 baseline manifest 中记录 launcher hash、
生成命令和版本；这是可审计性改进，不阻塞现有结论。

## 关键断言复核

### 1. `-4` 确实来自 frame lowering，而非 runtime 现象倒推

该断言成立，证据链足够窄：

1. ABI 明确要求 SP 在 `call` 前 8-byte aligned、frame size 8-byte aligned
   （[spec:206–210](../../contracts/abi/spec.md:206)、[spec:263–269](../../contracts/abi/spec.md:263)）。
2. musl `_Exit(int ec)` 的源形状是先调用 `SYS_exit_group`，再循环调用 `SYS_exit`
   （[source](/home/holight/DADAO-0628/.work/source/musl/src/exit/_Exit.c:4)）；`__syscall1` 的 inline asm 只显式执行 `trap 2, 0`，没有显式 stack adjustment
   （[source](/home/holight/DADAO-0628/.work/source/musl/arch/dadao/syscall_arch.h:40)）。
3. LLVM target object 虽声明 `Align(8)`（[header](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/Target/DADAO/DADAOFrameLowering.h:9)），但 prologue/epilogue 直接使用 `MFI.getStackSize()`，没有 round-up
   （[implementation](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/Target/DADAO/DADAOFrameLowering.cpp:19)）。
4. exact `_Exit` MIR 直接给出 `stackSize: 4`、`maxAlignment: 4` 和 `ADDI ... -4`；
   `__syscall1` 则是 `stackSize: 40`、`ADDI ... -40`、随后 `STO`。MIR hash
   `232a811685fe501660f3d04f645bb215c614c4966e8e87906929c2611d997af6` 与文件
   [ml016u-exit.prologepilog.mir](/tmp/ml-016x-exit-syscall-frame-repro-20260721/logs/ml016u-exit.prologepilog.mir) 一致。
5. 人工 IR 对照也独立产生 i64 `-8`、i32 `-4`，MIR hash
   `29bdba8304b8c1a436fdfb862caf22c6b97990232a253e5107cf0fe74e1c1236` 可复核。

因此，报告没有把 runtime `129` 反向冒充成 frame lowering 的直接证据；runtime 与
MIR/源代码是相互独立的闭环。

### 2. `42/129` 双后端结果可复核

权威 `.rc` 文件与报告表一致：

| probe | QEMU | Gem5 |
|---|---:|---:|
| direct_syscall1 | 42 | 42 |
| wrapper_return | 42 | 42 |
| wrapper_noreturn | 129 | 129 |
| exit_shape | 129 | 129 |
| trap_direct | 42 | 42 |
| trap_stack_minus4 | 129 | 129 |
| trap_stack_minus8 | 42 | 42 |

例如完整矩阵的 QEMU/Gem5 rc 分别见 [qemu logs](/tmp/ml-016x-exit-syscall-frame-repro-20260721/logs/qemu-exit_shape.rc:1) 和
[gem5 logs](/tmp/ml-016x-exit-syscall-frame-repro-20260721/logs/gem5-exit_shape.rc:1)；
其他行同目录同名 `.rc` 文件均可直接核对。Gem5 stdout 还明确区分
`SIM_END: trap-exit code=42` 与 `SIM_END: MALIGN code=129`。

exact ML-016u `_Exit.o` 的编译结果 hash
`341a7148cda7ed4c033b93bdc477f1051f5cf052bf138a080ba46695d73638b0` 与 archive member
一致；aligned assembly caller 为 129，而自身生成 `main -4` 的 C caller 为 42，正好
证明 caller parity 会掩盖违规 frame，不能把偶然成功当作修复。

### 3. hash、命令 rc 与 baseline 没有发现阻塞错误

- 报告列出的四个关键 ELF hash 与 artifacts 实际 hash 相同。
- 正常 compile/assemble/link/objcopy/disasm 日志的 `.rc` 为 0；exact compile、
  MIR 两条 llc 命令也均为 0。
- 日志中确有早期错误 objcopy（错误的 `link-*` 路径）和错误命名的 Gem5 capture，
  但待审报告已明确排除它们，没有把 rc=1 伪装成成功；修正后的 authority 日志与
  runtime 产物路径一致。
- 当前 `.work/build/musl/lib/libc.a` 与 ML-016u/ML-016v partial archive 的
  `_Exit.o` hash 不同，待审报告明确没有混用该 baseline；这项 stale-vintage 风险已
  被正确揭示，而不是静默采用错误 baseline。

## 最终判定

**Accepted-with-findings**：无阻塞 finding；接受“DADAO frame lowering 的 4-byte
frame 未按 ABI 向上取整是第一根因、musl wrapper 是触发器/规避面、launcher 不是
根因”的诊断。建议后续只修正文案中的 QEMU faulting-store 断言，并把复跑所用
launcher 的 hash/生成身份补进证据 manifest。
