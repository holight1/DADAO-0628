# Phase 0.5C — Spec Freeze Impact Matrix

**Freeze date**: 2026-06-29
**Spec lock commit**: `13a414da158dc780ae5501c1443acbffd15cbf4a` (manifests/spec.lock.toml)

"依赖此节的合约/文件"列列出 **当前仓库内** 直接引用本节的文件；
"Phase 1+ 实现目标"列列出 **需要实现本节规则的** LLVM/QEMU 组件。

---

## ISA Contract (`contracts/isa/spec.md`)

| 规格来源 | 依赖此节的合约/文件 | Phase 1+ 实现目标 |
|---------|-------------------|-----------------|
| ISA §1 Register Model | `contracts/abi/spec.md §1`（RD/RB/RF/RA bank roles 基础）；`tests/vectors/isa/` | LLVM TargetRegisterInfo（Phase 2）；QEMU CPU state struct（Phase 3）|
| ISA §2 Instruction Encoding | `tools/opcodes.yaml`；`tests/vectors/isa/*.yaml`；`contracts/elf/spec.md §2`（field widths） | LLVM MC code emission / MCCodeEmitter（Phase 2）；`make check` encoding gate（active）|
| ISA §3 Scalar Integer Instructions (RD) | `tests/vectors/isa/` | LLVM MC RD instruction selection；QEMU TCG RD helpers（Phase 2/3）|
| ISA §4 Address/Memory Instructions (RB) | `tests/vectors/isa/` | LLVM MC RB instruction selection；QEMU TCG RB/load-store helpers（Phase 2/3）|
| ISA §5 Control Flow | `contracts/elf/spec.md §2`（PCREL18/24/12 relocation fields）；`tests/vectors/isa/` | LLVM MC branch/call relocation consumers；QEMU TCG branch/call helpers（Phase 2/3）|
| ISA §6 NOP and Reserved | `tools/opcodes.yaml`（swym/unimp records） | LLVM MC NOP emission；assembler diagnostics on reserved encodings（Phase 2）|
| ISA §7 M1 Excluded | `code-agent/designs/0001-foundation-scope.md` | Scope boundary — no Phase 1/2 impl target |
| ISA Appendix A Canonical Encoding Inventory | `tools/opcodes.yaml`；`scripts/validate_encoding.py` | `make check` encoding gate（active）；LLVM MCInstrDesc table（Phase 2）|
| ISA Appendix B Condition Flag Reference | `tests/vectors/isa/` | LLVM SelectionDAG condition lowering（Phase 5）|
| ISA Appendix C Open Issues | `docs/open-spec-issues.md` | Wiki clarification required before affected Phase 2+ work |

---

## ABI Contract (`contracts/abi/spec.md`)

| 规格来源 | 依赖此节的合约/文件 | Phase 1+ 实现目标 |
|---------|-------------------|-----------------|
| ABI §1 Register Roles and Caller/Callee Classification | `contracts/isa/spec.md §1`（bank definitions）；`contracts/abi/spec.md §4–§5` | LLVM CallingConv.td；TargetRegisterInfo reserved regs（Phase 2）|
| ABI §2 Argument Passing | `contracts/abi/spec.md §1`（reg roles）；`contracts/abi/spec.md §4`（stack spill） | LLVM calling convention lowering（CC_DADAO in CCInfo）（Phase 2）|
| ABI §3 Return Values | `contracts/abi/spec.md §1`（reg roles） | LLVM return value lowering（RetCC_DADAO）（Phase 2）|
| ABI §4 Stack Frame Layout | `contracts/abi/spec.md §5`（prologue/epilogue） | LLVM TargetFrameLowering（Phase 2）|
| ABI §5 Call Sequence (Prologue/Epilogue) | `contracts/abi/spec.md §4`（frame）；`contracts/isa/spec.md §4`（RB addi/sto/ldo） | LLVM prologue/epilogue insertion pass（Phase 2）|
| ABI §6 Open Issues | `docs/open-spec-issues.md` | Wiki clarification required (varargs, multiple returns, cross-cfx) |

---

## ELF Contract (`contracts/elf/spec.md`)

| 规格来源 | 依赖此节的合约/文件 | Phase 1+ 实现目标 |
|---------|-------------------|-----------------|
| ELF §1 ELF Header Fixed Fields | `docs/adr/0003-object-abi.md §D1`（source ADR） | LLVM MC ELFObjectWriter（EI_CLASS/EI_DATA/e_machine/e_flags）（Phase 2）|
| ELF §2 M1 Relocation Types | `docs/adr/0003-object-abi.md §D2`（source ADR）；`contracts/isa/spec.md §2/§5`（field widths） | LLVM MC relocation emission；lld DADAO relocation applier（Phase 2/4）|
| ELF §3 Overflow Policy | `docs/adr/0003-object-abi.md §D3`（source ADR） | lld DADAO overflow checker（Phase 4）|
| ELF §4 Relaxation | `docs/adr/0003-object-abi.md §D4`（source ADR） | lld M1 no-op relaxation stub（Phase 4）|
| ELF §5 Section Alignment and Loading | `docs/adr/0003-object-abi.md §D5`（source ADR） | LLVM MC section layout；lld linker script（Phase 2/4）|
| ELF §6 Artifact Pipeline | `docs/adr/0004-test-machine.md §D2`（QEMU entry）；`docs/adr/0004-test-machine.md §D6`（ROM） | Phase 4 test harness：assemble→link→objcopy→QEMU |

---

## ADR-0003 (`docs/adr/0003-object-abi.md`)

| 规格来源 | 依赖此节的合约/文件 | Phase 1+ 实现目标 |
|---------|-------------------|-----------------|
| ADR-0003 §D1 ELF Header Fields | `contracts/elf/spec.md §1` | Normalized; see ELF §1 |
| ADR-0003 §D2 Relocation Types | `contracts/elf/spec.md §2` | Normalized; see ELF §2 |
| ADR-0003 §D3 Overflow Strategy | `contracts/elf/spec.md §3` | Normalized; see ELF §3 |
| ADR-0003 §D4 Relaxation | `contracts/elf/spec.md §4` | Normalized; see ELF §4 |
| ADR-0003 §D5 Section Alignment / Artifact Pipeline | `contracts/elf/spec.md §5–§6` | Normalized; see ELF §5–§6 |

---

## ADR-0004 (`docs/adr/0004-test-machine.md`)

| 规格来源 | 依赖此节的合约/文件 | Phase 1+ 实现目标 |
|---------|-------------------|-----------------|
| ADR-0004 §D1 Memory Map | `contracts/elf/spec.md §5`（VA=PA constraint）；`contracts/elf/spec.md §6`（0x80000000 load base） | QEMU machine model：RAM/ROM/MMIO 布局（Phase 3）|
| ADR-0004 §D2 Reset Vector and Entry Point | `contracts/elf/spec.md §6`（artifact pipeline entry） | QEMU boot init；ROM trampoline binary（`trampoline.bin`）（Phase 3）|
| ADR-0004 §D3 Exit Port Protocol | `tests/vectors/isa/`（exit-port semantic tests） | QEMU MMIO exit handler；test harness exit-code capture（Phase 3/4）|
| ADR-0004 §D4 MALIGN Observable Behavior | `tests/vectors/isa/`（alignment fault vectors） | QEMU memory access alignment fault（Phase 3）|
| ADR-0004 §D5 ILLI/UNDI Observable Behavior | `tests/vectors/isa/`（legality vectors）；`tools/opcodes.yaml`（legality table） | QEMU illegal instruction handler（Phase 3）|
| ADR-0004 §D6 Test Signature Specification | `contracts/elf/spec.md §6`（pipeline）；ROM bios.bin image | ROM `trampoline.bin`；Phase 4 test harness golden comparison |
