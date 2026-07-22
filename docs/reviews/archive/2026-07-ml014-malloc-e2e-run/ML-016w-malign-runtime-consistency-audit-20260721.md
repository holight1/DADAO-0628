# ML-016w：MALIGN 129 runtime consistency audit（2026-07-21）

## 结论

**Audit completed / Findings（只读诊断，不修复；本轮未冒充独立 reviewer acceptance）**。

ML-016v 的 ELF/BIN、linker、entry/load segments、stack、syscall path、launcher argv
和已接受 bare-metal fixture 语义已完成交叉检查。`rc=129` 在 QEMU/Gem5 两端都是真实
的 MALIGN fault，不是正常用户程序退出码；第一确认 fault 是当前 ML-016v ELF 的
`_Exit` 调用 generic `__syscall1` 时的栈对齐错误。没有证据表明这是 ELF entry、load
segment、trampoline 选择或 launcher argv 错配。

本轮没有修改实现、archive、测试/spec 或任何受限文件。所有额外证据仅在
[`/tmp/ml-016w-malign-runtime-consistency-audit-20260721/`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/)。

## Evidence root 与产物身份

主要证据：

- [`elf/llvm-readobj-all.stdout`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/elf/llvm-readobj-all.stdout)、[`elf/host-readelf-all.stdout`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/elf/host-readelf-all.stdout)：header、sections、program headers、symbols、relocations。
- [`elf/objdump-d-dadao.stdout`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/elf/objdump-d-dadao.stdout)：DADAO 反汇编；[`elf/puts_probe.map`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/elf/puts_probe.map)：link map。
- [`identity/sha256-and-stat.txt`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/identity/sha256-and-stat.txt)：ELF/BIN/map/linker/trampoline 身份；[`checks/provenance-comparisons.txt`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/checks/provenance-comparisons.txt)：与 ML-016v 原始产物的 `cmp`。
- [`runtime/`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/runtime/)：ML-016v 原始 QEMU/Gem5 argv、rc、stdout、stderr。
- [`checks/qemu-debug/`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/checks/qemu-debug/) 与 [`checks/gem5-debug/`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/checks/gem5-debug/)：同一 ELF/BIN 的只读 debug 重跑及 raw trace；两次均保存 `rc=129`。

产物 hash：

| artifact | SHA-256 | observation |
|---|---|---|
| `puts_probe.elf` | `f7844c487c3b601a3a03357be0ecd879e1ace8016d473194c14f6d0b20575ccd` | ML-016v ELF 与审计副本相同 |
| `puts_probe.bin` | `ead17191ca0a88ff4e944811a0c94193bee561c46a285ee33f650e7e49cd82f0` | 同一 ELF 的 flat image |
| `puts_probe.map` | `0e1b9fa6a93ffbf3d00a455d21c8515305d74e6a53c16008a196291fafe6ca24` | link map 保留 |
| linker script | `bc3c1bf453ec0ddd6a4e0856c085930f1d12eeae3238a897f1c320f843d95b39` | ML-016v 副本与 `tests/scripts/dadao.ld` 相同 |

## ELF/linker/entry/load 审计

证据确认：

- ELF64、big-endian、`ET_EXEC`、machine `0xDA0`，entry `0x80000000`。
- 无 relocation；最终 undefined check 在 ML-016v 中 `rc=0`。
- `PT_LOAD[0]` 为 RX，包含 `.text`/`.rodata`；`.text` 从 `0x80000000` 开始。
- `PT_LOAD[1]` 为 RW，始于 `0x80004000`，覆盖 `.data`、`.bss` 和 `.heap`；`.heap`
  为 `[0x80005000,0x87e00000)`。linker script 的 `ENTRY(_start)`、两个 `PT_LOAD`
  以及 `ALIGN(4096)` 分界均与仓库标准脚本一致。
- `_start`、`_start_c`、`main`、`puts`、`__init_tls`、`exit`、`_Exit`、`__syscall1`
  均在 map/symbol/disassembly 中可对应；`main` 的代码返回 `42`。

stack 不是第二个 ELF load segment 的一部分，而是 launcher/运行时提供的区域。既有
`crt0` 约定初始 QEMU stack pointer 为 `0x87ff0000`；该地址位于 image heap 末端
`0x87e00000` 之外，但这与现有 trampoline/QEMU 及 Gem5 SE 分别提供运行时 stack 的
模型一致。本审计没有把这种地址空间分离误判为 loader failure。

## Launcher、syscall 与退出码语义

ML-016v 原始 argv：

- QEMU：`qemu-system-dadao -M dadao-m1 -nographic -bios <trampoline.bin> -kernel <puts_probe.bin>`。
- Gem5：`gem5.opt dadao_se.py <puts_probe.elf>`；launcher 将同一 ELF 同时作为
  `SEWorkload` 输入、`process.cmd[0]` 和 `process.executable`。

这与已接受 fixtures 的入口形态一致：QEMU 使用 trampoline + flat BIN，Gem5 直接
使用 ELF；正常 fixture 还会严格断言 guest rc，再独立检查输出 marker。保存的原始
fixture RUN 行和输出见 [`launcher/accepted-fixture-run-lines.txt`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/launcher/accepted-fixture-run-lines.txt) 与 [`fixtures/raw/`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/fixtures/raw/)。已接受语义包括：

- musl return/auxv、raw syscall hello：两后端正常退出 `42`，Gem5 输出
  `SIM_END: trap-exit code=42`；QEMU 输出 `hi` 的 fixture 也严格要求 `42`。
- `printf_hello`、`malloc_hello`：两后端正常退出 `0`，并独立检查对应 marker。
- harness 的 `MALIGN` fault code 是 `0x81`，即十进制 `129`；只有明确预期
  `MALIGN` 的 fault fixture 才接受这个退出码。

ML-016v 的 raw runtime：

| backend | timeout | rc | stdout/stderr |
|---|---:|---:|---|
| QEMU | no | 129 | 仅 monitor banner/prompt；stderr 为空；无 puts marker |
| Gem5 | no | 129 | `SIM_END: MALIGN code=129`；stderr 仅既有 warning/info；无 puts marker |

因此 `129` 不能解释为 `main` 返回了 129，也不能作为 puts/runtime PASS。

## 确定的 fault 链

ML-016v ELF 反汇编的关键路径为：

```text
0x80000fe4  exit:      addi rb1, rb1, -16
0x8000100c  _Exit:     addi rb1, rb1, -4
0x80001020              call 0x8000103c   # generic __syscall1
0x8000103c  __syscall1: addi rb1, rb1, -40
0x80001040              sto rd16, rb1, 32   # 64-bit store
0x80001060              trap 2, 0           # not reached
```

按既有 trampoline 初始 `rb1=0x87ff0000` 的对齐约定，`-160`、`-24`、`-16` 均保留
`0 mod 8`；`_Exit` 的 `-4` 把栈变为 `4 mod 8`，`__syscall1` 的 `-40` 不改变
这一余数，故 `rb1+32` 仍为 `4 mod 8`。8-byte `sto` 在此处触发 MALIGN。

这是两端 trace 的共同终点：

- QEMU [`exec.trace`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/checks/qemu-debug/exec.trace) 进入 `0x80001040` 后停止，debug rc=129。
- Gem5 [`exec.trace`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/checks/gem5-debug/exec.trace) 最后实际记录为 `0x8000103c __syscall1`，debug rc=129；静态 objdump 的下一条为 `0x80001040` store，不能把 Gem5 raw trace 写成直接观测到该 store。
- QEMU 侧 MALIGN 退出码实现和 Gem5 `MalignFault` 均使用 `0x81`；对应 source-line
  摘要保存在 [`fixtures/qemu-malign-source-lines.txt`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/fixtures/qemu-malign-source-lines.txt) 与 [`fixtures/gem5-malign-source-lines.txt`](/tmp/ml-016w-malign-runtime-consistency-audit-20260721/fixtures/gem5-malign-source-lines.txt)。

所以当前最窄、证据闭合的分类是：**linked runtime syscall/ABI frame 的栈对齐
fault**。入口、ELF load、trampoline 选择和 launcher argv 没有被证据指向为根因。

## Findings / 未确定

1. **Confirmed**：ML-016v partial archive 选入的 `_Exit.o`/generic `__syscall1`
   路径在 `_Exit` 到 syscall wrapper 的边界破坏了 8-byte stack alignment；QEMU/Gem5
   同点返回 MALIGN `129`。
2. **Evidence-backed candidate**：已接受的 `musl_e2e_exit` ELF 使用直接 `trap 2,0`
   的 `_Exit` 路径并成功 `trap-exit code=42`；ML-016v map 使用 generic `exit.o`/
   `_Exit.o`。这说明后续应优先比较这两条 runtime object/ABI 路径，但不在本轮
   擅自指定修复组件。
3. **Undetermined**：syscall fd/console responder 在真正执行 `trap` 后是否正确；
   `puts` marker 缺失是否还有独立 buffering/flush 问题；以及修复归属是 musl
   `_Exit`、CodeGen frame lowering 还是 ABI contract。当前没有足够 evidence 把它们
   写成结论。

后续最小动作是另开受控任务修复/验证 `_Exit` 与 syscall wrapper 的对齐契约，再用
相同 ELF/BIN 双后端复跑；只有越过该 fault 后，才有资格继续判断 syscall/console 和
puts flush。ML-016w 本轮不修改实现、不新增测试、不改变任何既有语义。

独立 reviewer Epicurus the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016w-independent-review-20260721.md`。review 要求保留 Gem5 raw
trace 只到 `0x8000103c`、静态下一条为 `0x80001040` 的精确边界；部分 readelf helper
命令 rc=127 也作为工具边界记录，综合 llvm-readobj/host-readelf 证据仍有效。
