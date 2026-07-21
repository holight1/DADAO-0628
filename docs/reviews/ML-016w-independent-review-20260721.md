# ML-016w 独立 reviewer：MALIGN runtime consistency audit（2026-07-21）

## 结论

**Accepted-with-findings**。

审计的核心分类成立：ML-016v 的 partial-musl user ELF 在 linked runtime 的
`_Exit` → generic `__syscall1` 路径上破坏了 8-byte stack alignment；QEMU 和
Gem5 都以 MALIGN code `0x81`、十进制 `129` 结束。证据没有把根因指向
launcher、ELF entry、PT_LOAD 或 linker script。以下 findings 要求修正证据表述，
不改变本轮“不修复、不宣称 runtime/puts acceptance”的边界。

## 输入与独立性

用户给出的任务路径
`code-agent/tasks/ML-016w-malign-runtime-consistency-audit-20260721.md`
不存在；实际存在并据此审阅的是不带日期后缀的
`code-agent/tasks/ML-016w-malign-runtime-consistency-audit.md`。已有
`docs/reviews/ML-016w-malign-runtime-consistency-audit-20260721.md` 作为被审阅
材料，不作为独立 acceptance 依据。

我只读了上述任务/已有 review 和
`/tmp/ml-016w-malign-runtime-consistency-audit-20260721/`，没有访问或引用
`~/toolchain`、`~/knowledge-graph`。

## 核验结果

### 产物、ELF、linker 与 map

- `identity/audit-evidence.sha256` 校验通过；ELF、BIN、map、linker 副本和
  trampoline 分别与 ML-016v 记录的原始文件 `cmp=0`。
- `elf/llvm-readobj-all.stdout` 和 `elf/host-readelf-all.stdout` 均给出一致的
  ELF64 big-endian、`ET_EXEC`、machine `0xDA0`、entry `0x80000000`、无 relocation。
  两个 `PT_LOAD` 为 RX text/rodata 和 RW data/bss/heap；RW 段的 memsz 覆盖
  `.heap`。这足以排除“明显错误的 ELF header/entry/load layout”作为当前证据支持的
  分类，但不是对所有 loader 行为的形式证明。
- `linker/ml-016v-dadao.ld` 明确为 `ENTRY(_start)`、两个 `PT_LOAD`，并将
  `.heap (NOLOAD)` 放入 data segment；其 hash 与 ML-016v linker 输入一致。
- map/objdump 将 `_start`、`_start_c`、`main`、`exit`、`_Exit` 和目标
  `__syscall1` 对回：`main` 在 `0x80000148` 调用 `puts` 后返回 `42`；
  `exit.o` 的 `exit` 位于 `0x80000fe4`，`_Exit.o` 的 `_Exit`/generic
  `__syscall1` 位于 `0x8000100c`/`0x8000103c`。

### launcher、runtime 和 accepted fixture 对照

- 原始 QEMU argv 是 trampoline + flat BIN：`-bios ...trampoline.bin`
  与 `-kernel ...puts_probe.bin`；原始 Gem5 argv 是 `dadao_se.py`
  加同一 ELF。debug 重跑也使用 evidence root 中相同的 ELF/BIN/trampoline。
- 原始和 debug 两端均 `timeout=no`、`rc=129`。QEMU stdout 只有 monitor banner/
  prompt、stderr 为空；Gem5 stdout 明确为 `SIM_END: MALIGN code=129`，stderr 只有
  warning/info。没有把 `129` 当成 `main` 返回值或 PASS。
- accepted fixture 的 RUN 行确实分别使用 QEMU 的 trampoline + flat BIN 和 Gem5
  direct ELF，并先断言正常 rc（`42` 或 `0`），再独立 grep marker；fixture raw
  output 的 sha256 校验通过。launcher fault table 将 MALIGN 映射为 `0x81`。
  因而 ML-016v 与 accepted fixture 的差异在 user ELF/startup/exit object 组合，
  不是已显示的 argv/transport 错接。

### fault chain 与对齐

DADAO objdump 的关键指令为：

```text
0x80000fe4  exit:       addi rb1, rb1, -16
0x8000100c  _Exit:      addi rb1, rb1, -4
0x80001020              call 0x8000103c
0x8000103c  __syscall1: addi rb1, rb1, -40
0x80001040              sto rd16, rb1, 32
0x80001060              trap 2, 0
```

QEMU 的 `checks/qemu-debug/exec.trace` 进入 `0x80001040` 的 TB 后结束，结合
`rc=129` 和 QEMU source-line evidence 中 `MALIGN -> 0x81`，直接支持 fault 在
该 store。按 QEMU fixture 记录的初始 `rb1=0x87ff0000`，此前保持 8 对齐的
`-160/-24/-16` 经 `_Exit` 的 `-4` 变为 `4 mod 8`，`__syscall1` 的 `-40`
不改变余数，`rb1+32` 仍为 `4 mod 8`；8-byte store 因而不对齐。`trap 2,0`
在此运行中未执行。

Gem5 的 raw `checks/gem5-debug/exec.trace` 则最后一条实际记录是
`0x8000103c @_Exit+48 : addi.rb`；它没有记录 `0x80001040` 这一行。Gem5
stdout 的 `SIM_END: MALIGN code=129`、Gem5 fault mapping 以及静态 objdump 的
下一条 `sto` 共同支持同一窄 fault 分类，但不能把 Gem5 raw trace 描述为已经
直接观测到 `0x80001040`。Gem5 trace 的 `_start` 首次 store 地址为
`0x7fffffffdf60`，对应其实际初始栈约为 `0x7fffffffe000`，同样是 8 对齐；
因此对齐推导适用于两端，但原 review 只显式写出 QEMU 初始栈是不完整的。

## Findings

1. **Gem5 fault-PC 证据表述过强。**
   `checks/fault-pc-evidence.txt` 和已有 review 写成 Gem5 trace ends at
   `0x80001040`，与 raw trace 不符；raw trace ends at `0x8000103c`。应改成：
   QEMU trace 进入 `0x80001040`，Gem5 trace 停在前一条 prologue 指令，但 Gem5
   的 MALIGN exit 加静态下一条指令支持相同 fault。该 finding 不推翻根因，
   但影响“两个 raw trace 均直接定位 fault PC”的说法。

2. **readelf/objdump 产物需区分成功与失败。**
   `llvm-readobj-all`/host `readelf -a` 成功，DADAO-specific objdump 的反汇编、
   symbol、section 输出成功；但各 `elf/readelf-{h,S,l,r,s}.rc` 是 `127`，stderr
   表明 `.work/build/llvm/bin/llvm-readelf` 不存在，相关 stdout 为空。generic
   objdump 对 unknown target 或 flat BIN 失败也是预期限制。已有 review 不应笼统写成
   “所有 readelf/objdump 命令成功”，应明确使用的是成功的综合 readelf/llvm-readobj
   和 DADAO objdump 证据。

3. **任务输入路径存在 provenance finding。**
   日期后缀任务文件不存在，审阅实际使用了不带日期后缀的任务文件；最终记录已明确
   这一替代关系。若要求严格按用户给定路径复核，应补齐该输入或在任务索引中固定
   canonical path。

## 结论边界

当前证据只支持“linked `_Exit`/`__syscall1` 对齐 fault 是第一确认 fault”。它不
支持 syscall responder、fd/console 在越过 fault 后的行为结论，也不支持把缺失 puts
marker 写成独立的 stdio buffering/flush 根因；这些应在修复并越过该 fault 后再测。
该 ELF 也不构成 puts/runtime acceptance。

本 reviewer 未修改 LLVM、musl、build/archive、QEMU/Gem5、测试、spec、vectors、
issues 或 wiki。

