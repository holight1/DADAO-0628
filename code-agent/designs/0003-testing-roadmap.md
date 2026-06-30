# 0003 — DADAO-0628 测试路线图

**版本**：0.1.0  
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
4. **两条路径都测**：LLVM MC 测试必须覆盖 `-filetype=asm`（文本汇编）和
   `-filetype=obj`（ELF object）两条路径，二者行为不同（fixup 处理路径不同）。

---

## 向量基础设施（已就绪）

向量文件在 `tests/vectors/isa/`，覆盖全部 M1 指令，5 种 class：

| Class | 来源 | 期望字段 | 当前状态 |
|-------|------|---------|---------|
| `encoding` | Appendix A mask/value + §2.8 | `encoding.word` | 大部分空缺，DL-010a 填补 |
| `legality` | §2.6 ILLI 触发规则 | `expected_fault: ILLI` | 部分有 |
| `semantic` | §3–§6 指令语义 | `expected_state` | **大部分已有 ✓** |
| `boundary` | 边界值（min/max/zero/overflow）| `expected_state` | 普遍空缺 |
| `overlap` | src=dst 寄存器重叠 | `expected_state` | C-27 deferred |

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
| `legality-rd.s` | rd0 目标非法，越界 immu6，div-by-zero 触发 error | legality |
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

**前提**：DL-010a（汇编器）+ DL-016a（load/store）+ DL-017a（控制流）+ 0002 patch 修复。

> 汇编器是生成测试 binary 的工具；汇编器不可信，QEMU 测什么都没意义。
> **汇编器测试 PASS 是 QEMU 测试的前提。**

### 测试位置

`tests/lit/QEMU/Dadao/`

### 测试架构

```
tests/vectors/isa/*.yaml (semantic/boundary/legality class)
        │
        ▼
tests/scripts/gen_qemu_test.py   ← 从向量 YAML 生成汇编 + 期望 exit code
        │
        ▼ 生成
tests/lit/QEMU/Dadao/
  ├── <mnemonic>-semantic.s     ← llvm-mc → .bin → qemu-system-dadao
  ├── <mnemonic>-legality.s     ← 验证 ILLI 触发（exit code = ILLI signature）
  └── lit.cfg.py
```

### 测试协议（基于 ADR-0004 exit port）

```
trampoline.bin（ROM @0x0）
  → 设置 rb1(SP) = 0x87FF0000
  → jump 0x80000000

test.bin（RAM @0x80000000）
  → 执行被测指令序列
  → 写 expected_state 验证值到内存
  → 写 8 字节到 exit port（0x10000000）：低字节 = exit code
  → QEMU 自动 shutdown

test harness（Python/shell）
  → 运行 qemu-system-dadao -M dadao-m1 -bios trampoline.bin -kernel test.bin
  → assert exit code == 期望值
```

### ILLI 故障签名（per ADR-0004）

```
exit code 0x00 = PASS
exit code 0x01 = ILLI（非法指令）
exit code 0x02 = MALIGN（对齐异常）
exit code 0x03 = UNDI（保留编码）
exit code 0xFF = 测试 harness 自定义错误
```

### 覆盖目标（Phase 3 exit gate）

- semantic 向量：每条 M1 指令至少 1 个 normal case 通过 ✓
- legality 向量：所有 ILLI 触发路径（rd0 目标、除零、bank 越界、rb0 目标）
- MALIGN 向量：每种宽度（wyde/tetra/octa）各 1 个对齐异常用例

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
llvm-mc assembles .s → .o → qemu-system-dadao → 验证 exit signature
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
| DL-010a | `tests/lit/MC/Dadao/encoding-*.s`（11 文件）| Phase 2 |
| DL-016a | encoding-mem*.s + legality-rd.s 补充 | Phase 2 |
| DL-017a | encoding-ctrl.s, encoding-jump-call.s | Phase 2 |
| DL-018a | encoding-rb.s + legality-rb.s | Phase 2 |
| DL-019a | `tests/interface/` + trampoline.bin + gen_qemu_test.py | Phase 4 |
| DL-019a-vectors | boundary 向量补充（`tests/vectors/isa/*.yaml`）| Phase 4 前 |
| DL-020a | `make test-interface` + CI 集成 | Phase 4 |
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
