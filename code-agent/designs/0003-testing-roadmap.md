# 0003 — DADAO-0628 测试路线图

**版本**：0.1.1
**日期**：2026-06-30  
**状态**：Active

---

## 总体原则

1. **独立预期值**：所有测试期望值（字节序列、寄存器状态、故障类型）必须手推自
   `contracts/` 或 `tests/vectors/isa/*.yaml`，**不得从实现输出自举**。
2. **分层隔离**：LLVM MC 测试、QEMU 语义测试、E2E 集成测试三层独立运行；
   低层通过是高层的必要条件，但不是充分条件。
3. **随修附测**：lit 测试随 fix 任务同批提交，不单独建"补覆盖度"任务；
   只有在 QEMU 语义测试高度收敛后才考虑系统性补 boundary/overlap 向量。
4. **两条路径都测**：LLVM MC 测试必须覆盖 `-filetype=asm`（解析/规范化输出）和
   `-filetype=obj`（编码、fixup 与 ELF object）两条不同路径。

---

## 向量基础设施（框架已就绪，覆盖未收敛）

向量文件在 `tests/vectors/isa/`，采用 5 种 class。当前 inventory 仍缺 opcode
identity `0x47`、`0x4D`，各 class 的覆盖也未达到 Phase 2/3 exit gate：

| Class | 来源 | 期望字段 | 当前状态 |
|-------|------|---------|---------|
| `encoding` | Appendix A mask/value + §2.8 | `encoding.word` | 大部分空缺，DL-010a 填补 |
| `legality` | §2.6 ILLI 触发规则 | `expected_fault: ILLI` | 部分有 |
| `semantic` | §3–§6 指令语义 | `expected_state` | **大部分已有 ✓** |
| `boundary` | 边界值（min/max/zero/overflow）| `expected_state` | 普遍空缺 |
| `overlap` | src=dst 寄存器重叠 | `expected_state` | C-27 deferred；其余普遍空缺 |

向量 schema：`tests/vectors/schema.md`  
覆盖矩阵：`tests/vectors/inventory.md`  
机器可读 opcode oracle：`tools/opcodes.yaml`

---

## 阶段一：LLVM MC 编码测试（Phase 2 exit gate）

**前提**：DL-010a（AsmParser + MC Code Emitter）就绪。

### 测试位置

`tests/lit/MC/Dadao/`（已有目录）

### 测试内容

| 文件 | 测试目标 | vector class |
|------|---------|-------------|
| `encoding-rd-arith.s` | addi/add/sub/muls/mulu/divs/divu 字节序列 | encoding |
| `encoding-rd-logic.s` | and/orr/xor/xnor 及 MISC-Norm 子表 | encoding |
| `encoding-rd-shift.s` | shlu/shrs/shru/exts/extz reg+imm | encoding |
| `encoding-rd-cmp.s` | cmps/cmpu imm+reg, csn/csz/csp/cseq/csne | encoding |
| `encoding-rd-wyde.s` | orw/andnw/setzw/setow，rwii 位域分解 | encoding |
| `encoding-mem.s` | ldbs~ldo, stb~sto（单次）| encoding |
| `encoding-mem-multi.s` | ldmbs~ldmo, stmb~stmo（多次，rrri 格式）| encoding |
| `encoding-rb.s` | addi-rb/rela/sto-rb/rd2rb/rb2rd/rb2rb/add-rb/sub-rb/cmp-rb/orw-rb | encoding |
| `encoding-ctrl.s` | brn~brnp, breq/brne 相对偏移 | encoding |
| `encoding-jump-call.s` | jump/call（iiii+rrii）, ret | encoding |
| `encoding-misc.s` | swym, unimp, rd2rd | encoding |
| `legality-rd.s` | rd0 目标非法、越界 immu6 等可静态判定的操作数错误 | legality |
| `legality-rb.s` | rb0 目标非法 | legality |

### RUN 行模板

```asm
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d %t | FileCheck %s
# 同时测试 -filetype=asm 路径：
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM
```

### 期望字节规则

- 字节值来自 `tests/vectors/isa/*.yaml` 的 `encoding.word` 字段
- 或手推（公式见 `contracts/isa/spec.md §2.2–§2.4`）
- **不得从 `llvm-mc` 输出复制**

### 通过标准

```
llvm-lit tests/lit/MC/Dadao/   →  0 failures
```

---

## 阶段二：QEMU 语义测试（Phase 3 exit gate）

**前提**：DL-016a（load/store）+ DL-017a（控制流）+ 0002 patch 修复 + **state-dump 协议定义**。

> Phase 3 **不依赖 LLVM 汇编器**（DL-010a）。测试 binary 直接从向量的 `encoding.word`
> 字段构建，绕过 llvm-mc；若 LLVM encoder 和 QEMU decoder 对同一字段存在相同偏差，
> raw-encoding 路径能暴露而 llvm-mc 路径不能。LLVM 正确性由 Phase 2 独立验证，
> Phase 4 才将两者合并为 E2E。

### 测试位置

`tests/lit/QEMU/Dadao/`

### 测试架构（raw-encoding harness）

```
tests/vectors/isa/*.yaml (semantic/boundary/legality class)
        │  读取 encoding.word + expected_state + expected_fault
        ▼
tests/scripts/build_qemu_binary.py
  → struct.pack('>I', encoding_word) 直接生成 raw big-endian binary
  → 不经过 llvm-mc（Phase 3 与 DL-010a 完全独立）
        │
        ▼
tests/scripts/run_qemu_test.py
  → qemu-system-dadao -M dadao-m1 -bios trampoline.bin -kernel test.bin
  → 读取 state-dump region（见下节）
  → 按 vector expected_state 逐字段比较
  → assert exit code == expected_fault
```

### State-dump 协议（待 DL-016a 返回后最终化）

guest 在写 exit port 前，先将完整状态写入 RAM 固定偏移区（`0x80000000 + 0x7F00`）：

```
offset 0x000: rd[0..63]   (64 × 8 = 512 bytes, big-endian)
offset 0x200: rb[0..63]   (64 × 8 = 512 bytes, big-endian)
offset 0x400: pc           (8 bytes)
offset 0x408: 指定内存快照 (由 vector 的 memory_snapshot 字段指定起始地址和长度)
```

Python harness 通过 QEMU monitor `dump-memory` 或 `-d` 读取此区域，与 vector
的 `expected_state` 逐字段对比。

**关键约束**：
- fault（ILLI/MALIGN）情况下 state-dump 必须反映 fault 前状态（destination 无写入）
- rb0 停在 faulting 指令地址
- state-dump 写入使用最小可信指令集；具体 bootstrap 顺序在 Phase 3 harness 任务中定义

### 测试协议（exit port，ADR-0004）

```
exit code 0x00 = PASS
exit code 0x01 = ILLI（非法指令，precise — 无寄存器写入）
exit code 0x02 = MALIGN（对齐异常，precise — 无内存写入）
exit code 0x03 = UNDI（保留编码）
exit code 0xFF = harness 错误
```

### 覆盖目标（Phase 3 exit gate）

- semantic 向量：每条 M1 指令至少 1 个 normal case，**harness 直接对比 expected_state**（不依赖 guest self-check）
- **boundary 向量**：signed-min/max/zero/overflow 各类边界，覆盖所有适用指令（C-27 除外）
- legality 向量：所有 ILLI 触发路径（rd0 目标、除零、bank 越界、rb0 目标），验证 state-dump 无写入
- MALIGN 向量：wyde/tetra/octa 各宽度对齐异常，验证 state-dump 内存无写入

### 关键 TCG 陷阱（历史教训）

1. **`gen_exception_illegal` 后必须立即 `return true`**：该函数只向 TCG 流插入
   microop，不中断 C 函数执行；漏 return 导致后续 TCG 代码在非法状态下继续
   生成，可能引发 NULL TCGv assert 或无限循环。
   （来源：`knowledge-graph/compiler-backend/05-qemu-tcg-target-porting.md`）

2. **多寄存器循环用 TEMP_EBB 而非 TEMP_TB**：DL-016a 的 ldm/stm 循环，
   每次迭代的临时变量用 `tcg_temp_ebb_new_i64()`，避免 `TCG_MAX_TEMPS=512`
   超限（64 次循环 × 每次 2 个 temp = 128 temp，大批量指令很容易超）。

3. **rdhc/rbhb 在循环前 snapshot**：multi-load/store 中地址寄存器在循环前一次性
   读出，循环内部不重新 load（ISA spec §3.3 明确 snapshot 语义）。

---

## 阶段三：E2E 集成测试（Phase 4 = M1 Completion Gate）

**前提**：Phase 2 + Phase 3 全部通过。  
**任务编号**：DL-019a … DL-021a（估算）

### 测试位置

`tests/interface/`

### 测试内容

每条 M1 指令的完整流水线：
```
llvm-mc：.s → ET_REL .o → ld.lld：ET_EXEC（VMA 0x80000000）
→ llvm-objcopy：flat binary → qemu-system-dadao → 验证 exit signature
```

### make 集成

```makefile
test-interface: build-mc build-qemu
    python3 tests/scripts/run_interface_tests.py tests/interface/
    @echo "test-interface: PASS"
```

### M1 Completion Gate

```
make prepare        →  fetch + apply-series: clean
make build-mc       →  llvm-lit tests/lit/MC/Dadao/: 0 FAIL
make build-qemu     →  qemu build: PASS
make test-interface →  MC→QEMU roundtrips: 0 FAIL
```

全部通过 = M1 完成。

### boundary + overlap 补充时机

- **boundary 向量**（signed-min/max、zero、overflow）：Phase 3 结束后补充，
  在 DL-019a 前作为专项任务（DL-019a-vectors）
- **overlap 向量**（src=dst）：C-27 resolved 后补充，不阻塞 M1 Completion Gate
  以外的所有里程碑

---

## 任务对应表

| 任务 | 测试产出 | 阶段 |
|------|---------|------|
| DL-010a | `tests/lit/MC/Dadao/encoding-*.s`（11 文件）+ legality-rd.s | Phase 2 |
| DL-016a | encoding-mem*.s 补充 + boundary/legality 向量（load/store） | Phase 2 |
| DL-017a | encoding-ctrl.s, encoding-jump-call.s + boundary/legality（控制流）| Phase 2 |
| DL-018a | encoding-rb.s + legality-rb.s + boundary（RB ops）| Phase 2 |
| DL-vectors-fix | schema 增加 opcode identity；validate_vectors.py 按 `opcode_id × class` 统计；修复 `0x47`/`0x4D` 未覆盖静默通过 | Phase 2 前 |
| DL-019a | Phase 3 harness（`build_qemu_binary.py` + `run_qemu_test.py` + state-dump 协议实现）| Phase 3 |
| DL-020a | `make test-interface`（Phase 4 E2E：ET_REL→ld.lld→objcopy→QEMU）+ CI 集成 | Phase 4 |
| *(C-27 resolved)* | overlap 向量补充 | Phase 4 后 |

---

## 不在测试范围内（M1 scope exclusions）

- RF bank 执行（浮点）
- ldmo-ra / stmo-ra / rd2ra / ra2rd（RA 多寄存器）
- MMU / TLB / SBI
- SMP / atomic
- Dynamic linking / TLS
- 以上行为在测试中遇到时必须产生可断言的显式错误，不得静默忽略。

---

## 参考

- `code-agent/designs/0002-detailed-roadmap.md` §Phase 2/3/4 — exit gates 权威定义
- `tests/vectors/schema.md` — 向量字段规范
- `tests/vectors/inventory.md` — 覆盖矩阵
- `docs/adr/0007-testing-methodology.md` — 独立预期值原则 ADR
- `knowledge-graph/compiler-backend/01-llvm-backend-phases.md` — lit 分层策略
- `knowledge-graph/compiler-backend/05-qemu-tcg-target-porting.md` — TCG 测试陷阱

---

## Review 意见（2026-06-30）

**Review 范围**：`0003-testing-roadmap.md`、`ADR-0007`，并交叉核对
`0002-detailed-roadmap.md`、ADR-0003/0004、当前 vector inventory/validator、
上一版 DADAO 测试任务记录及 compiler-backend 知识图谱。

### 阻断问题

1. **[P0] Phase 3 不是独立的 QEMU 测试层，LLVM 与 QEMU 可能同错同过。**
   当前方案先由 `gen_qemu_test.py` 生成汇编，再由被测 `llvm-mc` 生成 QEMU
   输入，且明确把 DL-010a 设为 Phase 3 前提。这既与本文“分层隔离”冲突，也与
   `0002` 中 Phase 2/3 可并行的计划冲突；如果 LLVM 和 QEMU 对同一字段采用相同
   错位解释，semantic 测试仍会通过。上一版任务 DL-051a 已采用裸编码解除该耦合。
   **要求**：Phase 3 的被测指令必须直接取 vector 的 `encoding.word`，由独立的
   big-endian raw-binary builder 注入；LLVM 生成的 binary 只用于 Phase 4 interface
   test。Phase 3 不得依赖 DL-010a 完成。

2. **[P0] ADR-0007 D4 与既定 TDD/exit gate 正面冲突，且重复上一版“后补覆盖”失误。**
   `0002` Phase 0.5A 要求各适用 class 在实现前有实际 vector，Phase 2/3 又要求
   boundary 及除 C-27 外的 overlap 全部通过；本文和 ADR-0007 却把系统性
   boundary/overlap 推迟到 Phase 3 收敛后，并称 lit 只用于防回归、已知 bug 先写
   测试不增加价值。上一版 DL-058a 在 27 个 PASS 测试后审计出 42 项规格仅 16 项
   强覆盖、12 项未覆盖，DL-058b 又发现新增 PASS 测试存在“触发了错误机制却声称
   覆盖目标机制”的问题，恰好证明事后补测无法替代测试先行。
   **要求**：重写 D4 为“vector/失败测试先于实现或 fix，测试与实现同任务提交”；
   boundary 和所有已确定语义的 overlap 必须回到对应 Phase exit gate，仅 C-27
   可以 deferred。若确需改变 `0002`，必须先显式修订权威 roadmap，不能由新 ADR
   静默覆盖。

3. **[P0] Phase 3 缺少可独立断言完整架构状态的观测协议。**
   当前协议只检查 exit code，并让 guest 用尚在开发的 add/compare/branch/load/store
   自己验证 `expected_state`，容易形成循环 oracle，也无法证明 fault 时 destination、
   memory 未提交及 `rb0` 停在 faulting PC。它还遗漏 `0002` Phase 3 明确要求的
   “state-dump facility callable by test harness”。上一版 DL-035i 的核心教训正是
   “机制能触发/返回”不等于接口状态正确。
   **要求**：先定义机器可读 state dump（至少 RD/RB/RA、PC、指定内存区）及
   before/after 比较协议；Python harness 直接按 vector 的 `expected_state` 比较，
   exit signature 只表示终止原因。若保留 guest self-check，必须冻结最小可信指令集、
   明确 bootstrap 顺序，并用 host state dump 交叉验证该可信集。

4. **[P0] LLVM MC 测试设计没有真正隔离 encoder、decoder、fixup 和 ELF ABI。**
   `llvm-mc -filetype=asm` 主要覆盖 parser/printer，不覆盖 ELF relocation；
   `llvm-mc -filetype=obj | llvm-objdump -d` 又同时使用被测 encoder 和 decoder，二者
   字段同错时 round-trip 仍可通过。当前计划也没有 ADR-0003 所要求的 ELF header、
   `e_flags`、section endian/alignment、resolved fixup、unresolved relocation 类型/
   offset/addend 断言。上一版 DL-002h 曾出现 lit 2/2 PASS，但第二个 resolved `.equ`
   fixup 静默写成 0，原因就是场景被省略。
   **要求**：至少拆成四组门禁：`-show-encoding`/`.text` hex 对独立字节 oracle；
   raw bytes 或 `yaml2obj` 输入 disassembler；`llvm-readobj -h -S -r` 验证 ELF/reloc；
   同一 section 多 offset 的 resolved/unresolved fixup。不能以“每文件两条 RUN”替代
   按机制划分的测试矩阵。

5. **[P0] Vector completeness 门禁按错误主键统计，当前成功结果是伪完整。**
   `tests/vectors/inventory.md` 规定按 opcode identity 跟踪，并明确缺 `0x47 ldmo`
   和 `0x4D andnw-rb`；但 `validate_vectors.py` 只按 `(mnemonic, format)` 去重，因它们
   与其他 opcode 同名同格式，脚本仍报告 `79/79 ... covered OK`。脚本还只检查“至少
   一个 active case”，不能落实 `0002` 对每个适用 class 的要求。
   **要求**：schema 增加稳定的 opcode identity（major + minor/discriminator），校验
   `encoding.word` 是否满足对应 mask/value，并按 `opcode identity × applicable class`
   统计 coverage；修复后 `0x47`、`0x4D` 未补齐时 `make check` 必须失败。

### 重要问题

6. **[P1] Early Integration Checkpoint 被本路线图推迟到了 Phase 2/3 全完成之后。**
   `0002` 要求 LLVM/QEMU 各有第一条共同指令后，必须先打通一个 interface test，
   才能继续扩 opcode；本文到“阶段三”才创建 E2E，失去了尽早暴露 endian、loader、
   PC 和退出协议错误的作用。应在 Phase 2/3 的首条共同指令处增加硬门禁，完整
   Phase 4 再扩展到全部 instruction class。E2E 命令必须固定采用 ADR-0003 的
   `ET_REL → ld.lld ET_EXEC → objcopy flat binary → -kernel` 流水线。

7. **[P1] 通过标准允许空跑、漏跑和静默 skip。**
   “0 failures”不足以证明运行了目标集合。上一版记录明确出现过从错误目录运行得到
   `0 passed`，也长期依赖 timeout、grep `PASS` 和手工 skip；知识库后期才通过
   manifest 固化 1584 个已知 PASS。当前门禁应断言发现数/执行数、每 class/opcode
   的期望计数、`UNSUPPORTED/XFAIL/SKIP` allowlist，并把 timeout/crash 与 guest FAIL
   分开报告。测试生成器还应提供 `--check`，确保生成文件与 YAML 无 drift。

8. **[P1] 未建立“spec 条目 → vector → 测试 → 任务”的强覆盖矩阵和 legacy intent 审计。**
   “每 opcode 一个 normal case”只能证明 opcode 可运行，不能证明一个 opcode 内的
   多条合法性、精确异常、next-PC、snapshot、不同宽度/符号扩展等规则均被显式断言。
   应复用上一版 DL-058a 的强/弱/未覆盖定义，把 `contracts/isa/spec.md` 的可观测规则
   逐条映射到 vector ID 和测试 ID；greenfield 不复用旧实现代码，但应审计
   `DADAO-testset`、DL-035h/035i、DA-008a/008b 的测试意图，记录“迁移、替代、M1 排除”
   结论，避免已知故障模式丢失。

### 结论

当前文档的独立 oracle、分层方向和 TCG 历史教训是可用基础，但上述 P0 未关闭前，
不能把它作为 Phase 2/3 测试执行依据。优先顺序应为：先修 vector identity/completeness
门禁和 ADR-0007 D4，再定义 raw-encoding QEMU harness + state dump，最后补齐 MC
四类机制测试与 early interface gate。

### 历史证据索引

- `/home/holight/toolchain/DADAO/code-agent/tasks/DL-035i-interface-contract-tests.md`
- `/home/holight/toolchain/DADAO/code-agent/tasks/DL-058a-test-coverage-audit.md`
- `/home/holight/toolchain/DADAO/code-agent/tasks/DL-058b-test-supplement-p0.md`
- `/home/holight/toolchain/llvm-unicore/code-agent/tasks/DL-002h-add-mc-lit-tests.md`
- `/home/holight/toolchain/llvm-unicore/code-agent/knowledge/05-dadao-testset.md`
- `/home/holight/knowledge-graph/compiler-backend/01-llvm-backend-phases.md`
- `/home/holight/knowledge-graph/compiler-backend/02-mc-fixup-relocation.md`
- `/home/holight/knowledge-graph/compiler-backend/05-qemu-tcg-target-porting.md`
