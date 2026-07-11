# DL-051a: Phase 5 CodeGen ② — load/store SelectionDAG patterns（指针 load/store 存活到 MIR）

**执行环境**: 本地 DS · DADAO-0628（LLVM backend）

**状态**: 已完成

**前置**: DL-050a（GPRB 接入 ISelLowering，指针参数→gprb 存活到 MIR）

**依据**: ADR-0008 §Phase 5 序列 第 2 步（load/store patterns）

---

## 背景
DL-050a 让指针**参数**落 GPRB 并存活到 MIR，但**指针 load/store 本身**还没有 ISel pattern——`define i64 @ld(ptr %p){ %v = load i64, ptr %p  ret i64 %v }` 在 ISel 崩溃（`Cannot select: load`）。本任务补 **load/store 的 SelectionDAG patterns**（GPRB 地址 base + imm12 偏移），让指针 load/store 程序存活到 MIR。

**这是 Phase 5 第 2 步**：只到"load/store 程序存活到 MIR 有实证"，不求 CallingConv / .s 发射（那是 DL-052a/053a）。

---

## ⚠️ 防造假硬门槛（DS 必读）
这是 LLVM CodeGen——历史上此域反复出现「没 build llc 就报可行 / 伪造 MIR / 删前置改动去解锁」。本任务硬性要求：
- **完成区必须粘贴真实终端输出**：`ninja llc` 真跑成功 + `llc -stop-after=finalize-isel` 的**真实 MIR**（含 LOAD/STORE MachineInstr + gprb 地址寄存器）。**严禁估算 / 复制预期 / 伪造 MIR。**
- **架构师会亲自重 build llc + 重跑 llc + grep MIR 核对**，并核 DL-050a 不回归——伪造/估算一律**打回**。
- **崩在哪层如实剥**（`Cannot select` 缺哪个 pattern 就说哪个），卡住就在完成区写 `❌ + 根因`，**不糊「可行」**。
- **禁止删 / 破坏 DL-050a 的 GPRB 改动去「解锁」**本任务（= 回归）；确需改先在完成区写明理由。

## 起点
DL-050a 的改动在 `.work/source/llvm/`（GPRB 已注册进 ISelLowering，spike 地基）。本任务在其上继续。

---

## 目标
1. **load/store patterns**：`ldo`（GPRB base + imms12 → GPRD 结果）、`sto`（GPRD 值 → GPRB base + imms12）的 ISel 选择（TableGen pattern 或 ISelLowering，DADAO 地址=RB bank，48 位有效，big-endian 语义由后续 asm 层保证，本步只到 MIR）。
2. **FrameIndex 消解**（如需）：栈槽地址（`alloca`/spill）作为 GPRB base 的 lowering，够让含局部变量的 load/store 到 MIR。
3. **RD→RB 桥（DL-050a 遗留）**：DL-050a 里指针参数落 `$rd16`(RD) 却赋 gprb vreg，形成跨 bank COPY。本任务处理到「load/store 程序能到 MIR」所需的程度（copyPhysReg 的 rd2rb、或 lowering 时的 bank 归属）——**不求全，够本步验收即可**。
4. **存活到 MIR**：下列程序经 `llc -stop-after=finalize-isel` 产出含 **LOAD/STORE MachineInstr + gprb 地址** 的 MIR：
   - load：`define i64 @ld(ptr %p){ %v = load i64, ptr %p  ret i64 %v }`
   - store：`define void @st(ptr %p, i64 %v){ store i64 %v, ptr %p  ret void }`

---

## 约束
- 改动在 `.work/source/llvm/`（spike 阶段）。
- **不回归**：DL-050a 的 `pass_ptr`→gprb、`i64 add`→gprd 仍成立（`llc -stop-after=finalize-isel` MIR 不退步）。
- 只到 MIR；不做 .s 发射、不做完整 CallingConv（DL-052a/053a）。
- 根因风格：崩在哪一层就剥哪一层（`Cannot select` 看缺哪个 pattern），别猜。

---

## 过程要求
1. 完成区**贴真实终端输出**：`ninja llc` 真 build 成功、上述 load/store 程序的**真实 MIR**（含 LOAD/STORE MI + gprb 地址寄存器）、DL-050a 不回归（pass_ptr→gprb、add→gprd）。**不许估算/伪造 MIR**。
2. 交付前自跑通。
3. **自审（见 DS.md §自审流程 · 强制）**：DS 实现完开 subagent review，本任务 ground-truth = 重 build llc + 重跑 ld/st 程序取 MIR（含 LOAD/STORE MI + gprb 地址）+ 核 DL-050a 不回归；review 意见 + 修复情况写入下方「## 审阅记录（subagent）」区，修完再返回。架构师最终独立复跑验收后提交。

---

## 验收（架构师亲自复跑 —— 会真 build llc + grep MIR，不采信完成区）
```bash
cd ~/DADAO-0628
ninja -C .work/build/llvm llc 2>&1 | tail -2
LLC=.work/build/llvm/bin/llc
echo 'define i64 @ld(ptr %p){ %v = load i64, ptr %p  ret i64 %v }' > /tmp/ld.ll
$LLC -march=dadao -stop-after=finalize-isel /tmp/ld.ll -o - 2>&1 | grep -iE "LOAD|LDO|gprb"     # load MI + gprb 地址
echo 'define void @st(ptr %p, i64 %v){ store i64 %v, ptr %p  ret void }' > /tmp/st.ll
$LLC -march=dadao -stop-after=finalize-isel /tmp/st.ll -o - 2>&1 | grep -iE "STORE|STO|gprb"    # store MI + gprb 地址
# 不回归
echo 'define ptr @pp(ptr %p){ ret ptr %p }' > /tmp/pp.ll && $LLC -march=dadao -stop-after=finalize-isel /tmp/pp.ll -o - 2>&1 | grep -i gprb
echo 'define i64 @ad(i64 %a,i64 %b){ %s=add i64 %a,%b  ret i64 %s }' > /tmp/ad.ll && $LLC -march=dadao -stop-after=finalize-isel /tmp/ad.ll -o - 2>&1 | grep -i gprd
```

---

## 参考指针
- ADR-0008（§Phase 5 序列、§修复清单、大小写注记 grep -qi）；DL-050a 完成区（GPRB 接入 + RD→RB 遗留）
- `.work/source/llvm/.../Target/DADAO/`：`DADAOInstrInfo.td`（load/store pattern 落点）、`DADAOISelLowering.cpp`（DL-050a 加了 GPRB；本步补 load/store lowering / setOperationAction）、`DADAORegisterInfo.td`（GPRB 类）、`DADAOInstrInfo.cpp`（copyPhysReg——RD↔RB 用 rd2rb/rb2rd）
- `contracts/isa/spec.md §3.1/§3.2`（ldo/sto 语义：EA=rbhb[47:0]+imm）；`tools/opcodes.yaml`（ldo/sto 编码）
- LLVM 22 范式：load/store TableGen pattern、`getFrameIndex` lowering、`copyPhysReg` 跨 class（参 riscv/其它 target——借范式，语义是 DADAO RB 48 位）
- 后续 **DL-052a**（CallingConv：指针入 RB、栈参数、prologue/epilogue）→ DL-053a（AsmPrinter→.s）

---

## 完成区

**状态**：已完成
**修改文件**：
- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOInstrFormats.td` — `F_RRII_LOAD` 加 `mayLoad=1`；`F_RRII_STORE` 加 `mayStore=1`
- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.td` — `LDO_RRII`/`STO_RRII` 加 zero-offset `def : Pat<...>` ISel patterns
- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.h` — 加 `copyPhysReg` 声明 + `using TargetInstrInfo::copyPhysReg`
- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOInstrInfo.cpp` — 实现 `copyPhysReg`（GPRD↔GPRB 用 rd2rb/rb2rd，同 bank 用 addi r, r, 0）
- `.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp` — 修复 `LowerReturn` void 返回（`Glue.getNode()` 判空）

**验收结果**：

### llc build 成功
```bash
$ ninja -C .work/build/llvm llc 2>&1 | tail -3
[6/7] Linking CXX static library lib/libLLVMDADAOCodeGen.a
[7/7] Linking CXX executable bin/llc
```

### LOAD: LDO MI + gprb 地址
```bash
$ echo 'define i64 @ld(ptr %p){ %v = load i64, ptr %p  ret i64 %v }' > /tmp/ld.ll
$ .work/build/llvm/bin/llc -march=dadao -stop-after=finalize-isel /tmp/ld.ll -o - 2>&1
---
name:            ld
...
registers:
  - { id: 0, class: gprb, preferred-register: '', flags: [  ] }
  - { id: 1, class: gprd, preferred-register: '', flags: [  ] }
liveins:
  - { reg: '$rd16', virtual-reg: '%0' }
body:             |
  bb.0 (%ir-block.0):
    liveins: $rd16

    %0:gprb = COPY $rd16
    %1:gprd = LDO_RRII %0, 0 :: (load (s64) from %ir.p)
    $rd31 = COPY %1
    RET_PSEUDO implicit $rd31
```

`grep -iE "LDO|gprb"` 命中 3 处。

### STORE: STO MI + gprb 地址
```bash
$ echo 'define void @st(ptr %p, i64 %v){ store i64 %v, ptr %p  ret void }' > /tmp/st.ll
$ .work/build/llvm/bin/llc -march=dadao -stop-after=finalize-isel /tmp/st.ll -o - 2>&1
---
name:            st
...
registers:
  - { id: 0, class: gprb, preferred-register: '', flags: [  ] }
  - { id: 1, class: gprd, preferred-register: '', flags: [  ] }
liveins:
  - { reg: '$rd16', virtual-reg: '%0' }
  - { reg: '$rd17', virtual-reg: '%1' }
body:             |
  bb.0 (%ir-block.0):
    liveins: $rd16, $rd17

    %1:gprd = COPY $rd17
    %0:gprb = COPY $rd16
    STO_RRII %1, %0, 0 :: (store (s64) into %ir.p)
    RET_PSEUDO
```

`grep -iE "STO|gprb"` 命中 3 处。

### DL-050a 不回归

**pass_ptr → gprb**:
```
  - { id: 0, class: gprb, ... }
    %0:gprb = COPY $rd16
```
gprb 命中 2 处 ✓

**add → gprd**:
```
  - { id: 0, class: gprd, ... }
  - { id: 1, class: gprd, ... }
  - { id: 2, class: gprd, ... }
    %1:gprd = COPY $rd17
    %0:gprd = COPY $rd16
    %2:gprd = ADD_PSEUDO %0, %1
```
gprd 命中 6 处 ✓

**遗留问题**：
- load/store 仅支持 zero-offset（`imm12=0`）；带偏移的 `(add base, simm12)` pattern 未加（TableGen `imms12` operand 与 pattern DAG 匹配需要额外适配）。后续 DL-052a 补。
- `F_RRII_RB` 和 `STO_RBRRII` 格式未加 mayLoad/mayStore，后续按需补。

---

## 审阅记录（subagent）

### Step 2: Build
```bash
$ ninja -C /home/holight/DADAO-0628/.work/build/llvm llc 2>&1 | tail -5
ninja: no work to do.
```

### Step 3: Load test — full MIR output
```bash
$ echo 'define i64 @ld(ptr %p){ %v = load i64, ptr %p  ret i64 %v }' > /tmp/review_ld.ll
$ $LLC -march=dadao -stop-after=finalize-isel /tmp/review_ld.ll -o - 2>&1
--- |
  ; ModuleID = '/tmp/review_ld.ll'
  source_filename = "/tmp/review_ld.ll"
  target datalayout = "E-m:e-i64:64-n64-S64"

  define i64 @ld(ptr %p) {
    %v = load i64, ptr %p, align 8
    ret i64 %v
  }
...
---
name:            ld
alignment:       1
...
registers:
  - { id: 0, class: gprb, preferred-register: '', flags: [  ] }
  - { id: 1, class: gprd, preferred-register: '', flags: [  ] }
liveins:
  - { reg: '$rd16', virtual-reg: '%0' }
...
body:             |
  bb.0 (%ir-block.0):
    liveins: $rd16

    %0:gprb = COPY $rd16
    %1:gprd = LDO_RRII %0, 0 :: (load (s64) from %ir.p)
    $rd31 = COPY %1
    RET_PSEUDO implicit $rd31
...
```
grep hits: `gprb` (register class + livein + COPY) = 3 hits. `LDO_RRII` present. `RET_PSEUDO` present.
**PASS**

### Step 4: Store test — full MIR output
```bash
$ echo 'define void @st(ptr %p, i64 %v){ store i64 %v, ptr %p  ret void }' > /tmp/review_st.ll
$ $LLC -march=dadao -stop-after=finalize-isel /tmp/review_st.ll -o - 2>&1
--- |
  ; ModuleID = '/tmp/review_st.ll'
  source_filename = "/tmp/review_st.ll"
  target datalayout = "E-m:e-i64:64-n64-S64"

  define void @st(ptr %p, i64 %v) {
    store i64 %v, ptr %p, align 8
    ret void
  }
...
---
name:            st
...
registers:
  - { id: 0, class: gprb, preferred-register: '', flags: [  ] }
  - { id: 1, class: gprd, preferred-register: '', flags: [  ] }
liveins:
  - { reg: '$rd16', virtual-reg: '%0' }
  - { reg: '$rd17', virtual-reg: '%1' }
...
body:             |
  bb.0 (%ir-block.0):
    liveins: $rd16, $rd17

    %1:gprd = COPY $rd17
    %0:gprb = COPY $rd16
    STO_RRII %1, %0, 0 :: (store (s64) into %ir.p)
    RET_PSEUDO
...
```
grep hits: `gprb` (register class + livein + COPY) = 3 hits. `STO_RRII` present with GPRD (data) + GPRB (address) operands. `RET_PSEUDO` present.
**PASS**

### Step 5: DL-050a non-regression

**pass_ptr → gprb:**
```bash
$ echo 'define ptr @pp(ptr %p){ ret ptr %p }' > /tmp/review_pp.ll
$ $LLC -march=dadao -stop-after=finalize-isel /tmp/review_pp.ll -o - 2>&1 | grep -i gprb
  - { id: 0, class: gprb, preferred-register: '', flags: [  ] }
    %0:gprb = COPY $rd16
```
gprb 命中 2 处 ✓ PASS

**add → gprd:**
```bash
$ echo 'define i64 @ad(i64 %a,i64 %b){ %s=add i64 %a,%b  ret i64 %s }' > /tmp/review_ad.ll
$ $LLC -march=dadao -stop-after=finalize-isel /tmp/review_ad.ll -o - 2>&1 | grep -i gprd
  - { id: 0, class: gprd, preferred-register: '', flags: [  ] }
  - { id: 1, class: gprd, preferred-register: '', flags: [  ] }
  - { id: 2, class: gprd, preferred-register: '', flags: [  ] }
    %1:gprd = COPY $rd17
    %0:gprd = COPY $rd16
    %2:gprd = ADD_PSEUDO %0, %1
```
gprd 命中 6 处 ✓ PASS

### Step 6: Code review

| 检查项 | 文件 | 结果 |
|--------|------|------|
| mayLoad=1 on F_RRII_LOAD | DADAOInstrFormats.td:173 | PASS |
| mayStore=1 on F_RRII_STORE | DADAOInstrFormats.td:186 | PASS |
| Zero-offset load Pat: `(load GPRB:$rbhb) → (LDO_RRII ... 0)` | DADAOInstrInfo.td:146 | PASS |
| Zero-offset store Pat: `(store GPRD:$rdha, GPRB:$rbhb) → (STO_RRII ... 0)` | DADAOInstrInfo.td:160 | PASS |
| copyPhysReg: GPRD→GPRD (ADDI_RRII imm0) | DADAOInstrInfo.cpp:37-43 | PASS |
| copyPhysReg: GPRB→GPRB (ADDI_RBRRII imm0) | DADAOInstrInfo.cpp:44-50 | PASS |
| copyPhysReg: GPRD→GPRB (RD2RB_ORRI) | DADAOInstrInfo.cpp:23-29 | PASS |
| copyPhysReg: GPRB→GPRD (RB2RD_ORRI) | DADAOInstrInfo.cpp:30-36 | PASS |
| `using TargetInstrInfo::copyPhysReg` to prevent overload hiding | DADAOInstrInfo.h:23 | PASS |
| Void return fix: `Glue.getNode()` null guard | DADAOISelLowering.cpp:89-90 | PASS |

### Verdict: **PASS**

All 4 bank combinations in copyPhysReg correctly implemented. mayLoad/mayStore properly set on format classes. Zero-offset load/store Pat patterns correctly match. Void return Glue null guard correct. DL-050a (gprb/gprd) non-regression confirmed. Build succeeds, MIR outputs all contain expected instructions and register classes.
