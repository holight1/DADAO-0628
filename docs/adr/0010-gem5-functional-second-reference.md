# ADR-0010: DADAO-gem5 功能第二参考（三方差分 · SE 先行 · 上游 fork）

**状态**：Accepted（2026-07-08）
**日期**：2026-07-08
**关联**：ADR-0009（验证链机械化·golden model）、ADR-0006（QEMU baseline）、ADR-0004（Test Machine·exit-MMIO）、ADR-0007（测试方法论·独立预期值）

---

## 背景

ADR-0009 的验证链是 `spec.md（权威）→ {dadao_interp（黄金模型）, QEMU, LLVM}`，
以 spec 独立的 `dadao_interp` 作差分裁判。本轮 rela bug 证明了它的价值：interp 从
spec 派生，才敢判「QEMU rb0 未维护，是 QEMU 错、不是向量错」。但当前只有 **两个可
执行 ISA 实现**（interp + QEMU），分歧时靠 interp 破平——**二方 + 裁判**。

引入 gem5 作 ISA 的**第三个独立可执行实现**，把结构升级为**三方投票**：任意两方
分歧，第三方 + spec 定谳。gem5 同时打开跑**更大程序 / OS**（QEMU 之外的第二功能
参考）与后续微架构探索的门。

```
              spec.md（权威契约）
           /         |          \
   dadao_interp     QEMU        gem5      ← 三个独立实现，各自从 spec 派生
           \         |          /
        run_differential —— 三路 AGREE / 分歧定位
```

---

## 决策

### D1 — 域：功能 ISA 正确性，**时序 out of scope**

DADAO-gem5 本 ADR 只做 **functional second reference**——指令语义 + fault + 寄存器
终态正确性。**流水线 / cache / 性能时序不在本 ADR 范围**（当前验证链无时序 oracle；
功能向量全过 ≠ 时序对）。时序建模留作独立后续（需微架构参考 / RTL tandem，另立 ADR）。
CPU 模型用 **AtomicSimpleCPU**（功能原子），不用 O3/Minor。

### D2 — SE 先行，FS 留 G4

功能验证（向量 + 三方差分 + M3 矩阵）全在 gem5 **SE（syscall emulation）模式**下完成，
最快拿到"功能第二参考"。裸机 halt 退出码天然对应 SE 的 `m5 exit(code)`。**FS（全系统）
+ 自定义 platform** 留到 G4 跑 OS 时再上。

### D3 — 从上游社区 fork，新建 `arch/dadao/`

从 **gem5 上游**（pin 一个近期 stable tag，fork 时定）起，新建 `src/arch/dadao/`。
**不**复用 UPU/gem5-a4e fork（避免继承其历史包袱；换取干净上游基线）。gem5 用其 ISA
描述 DSL（`.isa` → 生成 decoder + execute），是 QEMU decodetree+translate.c 的对应物。

### D4 — 独立性纪律（与 interp / QEMU 同规）

**gem5 的 `.isa` 指令语义只从 `spec.md §` 派生，绝不抄 QEMU `translate.c` / helper.c。**
每条指令 execute 标注 `spec §`。否则 gem5-vs-QEMU 差分退化成循环自证，抓不到共性 bug。

### D5 — 三方差分接线

- `run_gem5_test.py`：对标 `tests/scripts/run_qemu_test.py` 的**同接口**适配器——吃同一
  份向量 yaml，用同一个 `build_test_binary.py` 造二进制，跑 gem5，取退出码 + 终态寄存
  器，比对 expected。
- `tools/run_differential.py` 加 **gem5 列** → interp / QEMU / gem5 三路。`dadao_interp`
  仍是中立裁判。
- gem5 binary 路径可配置（env / config），镜像 harness 引用 `.work` QEMU 的方式。

### D6 — 仓库布局

- **新仓 `~/DADAO-gem5`**（上游 gem5 fork），DADAO arch 在 `src/arch/dadao/`。
- **验证适配器归 DADAO-0628**（它 owns 向量 + harness + interp + 矩阵）；`run_gem5_test.py`
  引用一个可配置的 gem5 可执行路径。语料/裁判不进 gem5 仓，保持单一 owner。

---

## 设计

### ISA 建模（从 spec 派生）

| 部件 | 内容 | spec 源 |
|------|------|---------|
| 寄存器 banks | **RD** rd0-31（64b 数据，rd0 恒 0，作目标→ILLI）；**RB** rb0-63（64b 地址，低 48b 有效、高 16b 保留；**rb0=PC+4 硬件维护、不可写**）；**RF**（浮点）；**RA**（返回地址栈 RAS，call/ret） | §1.3、§1.x |
| decode | 5 格式（riii/rrii/rrri/orrr/orri…）+ MISC-Norm（op=0x10）按 ha 嵌套子译码 | §2.2/§2.3/§2.5 |
| execute | 87 指令语义，逐条标 `spec §` | §3–§5 |
| fault | ILLI=0x82 / MALIGN=0x81 / UNDI=0x83 → gem5 Fault 类；SE 下映射为 exit code（对齐 harness FAULT_CODES） | §2.5/§2.6/§2.8 |
| halt | op=0x00，execute 触发 `exitSimLoop`，退出码 = rdha 值（对应 QEMU shutdown-with-code） | ADR-0004 |

### SE workload

- 载入 `build_test_binary.py` 产出的 flat 二进制 @ `BINARY_BASE=0x80000000`，SP 初值同
  trampoline 约定（rb1=0x87FF0000）。裸机 flat binary 在 SE 下用最小 workload 包装载入。
- 正常 halt → `m5 exit(rdha)`；fault → `m5 exit(fault_code)`。
- 终态寄存器读出机制须与 harness 比对方式兼容（**G1 待定项**，见开放问题）。

### 已知坑：day-1 从 spec 正确实现（不重犯 QEMU 的错）

issues.yaml 里 QEMU/向量踩过的坑，gem5 一开始就按 spec 做对：

| 坑 | 正确做法（spec） |
|----|-----------------|
| `QEMU-rb0-not-maintained` | rb0 读取物化为 **PC+4**（不读陈旧槽）；§1.3/§4.8 |
| `QEMU-rela-rbha-hi16-not-preserved` | rela 写 rbha 保留 [63:48]；§4.8 L785 |
| `QEMU-reserved-UNDI`（已修） | 保留编码 → **UNDI(0x83)**，非 ILLI；§2.5/§2.8.1 |
| `ldo-align-MALIGN`（已修） | ldo EA 非 8B 对齐 → MALIGN；§3.1 |
| store-from-rd0 / cs / RB legality | 按 opcodes.yaml legality（已补全）→ ILLI；§2.6 |
| `RASUF-cold-ret` | 冷 RAS ret → RASUF；§5.6 |

### 里程碑（验收挂验证链）

| 里程碑 | 内容 | 验收 |
|--------|------|------|
| **G1 骨架** | RD/RB/RF/RA 堆 + 部分格式 decode + halt→exit + SE workload | 3 个 smoke（arith/add/jump）gem5 exit 与 QEMU 一致（42/42/0） |
| **G2 全 87 + fault** | 全指令 execute + fault 模型 + `run_gem5_test.py` | 全 203 向量 gem5 PASS；**三路差分 interp/QEMU/gem5 全 AGREE**（← 功能第二参考达成） |
| **G3 M3 矩阵** | fault 完备性过 legality 矩阵 | gem5 对矩阵 137 cell 抛对 fault；三方 fault 一致 |
| **G4 大程序 / OS** | LLVM 编译 C → gem5 SE；再 FS 模式 OS bring-up | 编译程序三方一致；FS 起最小 OS |

---

## 开放问题（G1 前需定/调研）

1. **gem5 版本 pin**：fork 时选定近期 stable tag（fork 任务里定）。
2. **SE 裸机 workload 载入**：gem5 SE 默认吃 ELF + syscall ABI；flat binary @ 0x80000000
   的最小载入方式（裹 ELF？raw load？）——G1 调研项。
3. **终态寄存器读出**：`run_qemu_test.py` 如何取 QEMU 终态寄存器比对 expected_state？gem5
   需提供等价读出（arch state dump / m5 机制）——G1 对齐。
4. **RB bank 在 gem5 RegClass 的表达**：48b 有效 + 16b 保留 + rb0 特殊，映射到 gem5 寄存器
   类系统的方式——G1 设计。
5. **interp 的 rb0 近似**：interp 用固定 rb0=0x80000000，gem5 SE 实际 PC 亦 @0x80000000 →
   三方在 rela 类应一致；确认无偏差（G2 差分自然暴露）。

## 不做（本 ADR 明确排除）

- 时序 / 流水线 / cache / 性能建模（另立 ADR）。
- O3/Minor CPU。
- RTL tandem / 形式化。
- 复用 UPU/gem5-a4e fork 基建。

---

## 后续（落地顺序）

1. **fork 任务**：从上游 clone、pin tag、建 `src/arch/dadao/` 骨架、能 build 出带 dadao 的 gem5。
2. **G1 任务**：寄存器堆 + 少量格式 decode + halt→exit + SE workload + 3 smoke 对齐 QEMU。
3. G2 → G3 → G4 依次（各挂三方差分验收）。

> 本 ADR 为设计基线；G1 起每里程碑拆独立任务下发，验收挂三方差分/矩阵。
