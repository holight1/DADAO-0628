# Sail 调研报告：定位 B（权威可执行 spec）可行性评估

**日期**: 2026-07-10  
**版本**: 0.1.0  
**依据**: ADR-0009 §M2b；架构决策 2026-07-10  
**范围**: 纯调研，不安装 Sail、不写代码  

---

## 摘要（一页决策所需信息）

| 维度 | 结论 |
|------|------|
| **Sail 定位 B 可行性** | **可行**。sail-riscv 是成品蓝本；DADAO 特性（双寄存器组、48 位地址、big-endian、精确异常、RAS）均可在 Sail 干净建模 |
| **工具链成熟度** | 高。opam 安装，C 模拟器、定理证明后端（Isabelle/Coq/Lean）均已生产使用。SystemVerilog 导出实验性 |
| **RTL tandem** | TestRIG + RVFI-DII 协议成熟，已在 CHERI 项目中对拍 Sail vs Spike/RVBS/Piccolo/Flute/Toooba/Ibex |
| **形式化证明** | Morello 安全证明（ESOP 2022）为标志性成果；可 export 到 Coq/Isabelle/HOL4/Lean |
| **治理迁移路径** | Sail 成为新权威源，spec.md 退为 human-readable 对照物；wiki 团队审计背书是外部依赖 |
| **推荐动作** | 按 ADR-0009 计划执行 M2b 垂直切片彩排（~20-30 条指令），时间盒 2-4 周，产出 `wiki → Sail → C 仿真器 → 差分 QEMU` 闭环 |
| **主要风险** | wiki 团队审计背书节奏不可控（权威性前置条件）；Sail 学习曲线（OCaml 生态 + 依赖类型） |

---

## 1. Sail 工具链

### 1.1 语言概况

Sail 是 **Cambridge REMS 项目** 开发的 ISA 语义规格语言（POPL 2019 论文）。定位为"工程师友好的伪码 + 精确语义 + 多后端工具链"。

**核心特征**：
- 一阶命令式语言，类 ARM ASL / IBM Power 伪码风格
- 轻量依赖类型：自动检查 bitvector 宽度和整数约束（用 Z3 SMT solver）
- 支持 scattered definitions（分散定义），允许指令的 AST clause / decode / execute / assembly 散落在不同文件中，但逻辑上聚集——这是 ISA spec 写作的关键能力
- 可扩展：ad-hoc overloading、polymorphic types、implicit parameters

**许可证**: BSD 2-clause（Sail 编译器本身及手写模型）。

### 1.2 安装方式

**方式 A（推荐）—— opam 二进制发布**：
```
opam install sail
```
需要 opam >= 2.0，OCaml >= 5.2（推荐 5.4.1）。系统依赖：`build-essential libgmp-dev z3 pkg-config`。Sail 编译器和标准库一起安装，`sail --help` 验证。

**方式 B —— 源码安装**：
```
git clone https://github.com/rems-project/sail.git
cd sail
opam pin add .
```

**方式 C —— Docker**：Sail 官方提供 Dockerfile.nightly 和 Dockerfile.release。sail-riscv 也提供 Linux x86_64 / aarch64 二进制发布。

### 1.3 后端

| 后端 | 选项 | 成熟度 | 用途 |
|------|------|--------|------|
| **C** | `-c` | **生产** | 生成高效 C 仿真器（sail-riscv 可启动 Linux） |
| **OCaml** | 默认 | 生产 | 直接执行/交互式解释器 |
| **Coq** | `-coq` | 生产 | 定理证明定义导出 |
| **Isabelle** | `-isabelle` | 生产 | 定理证明（Morello 安全证明使用） |
| **HOL4** | `-hol4` | 生产 | 定理证明 |
| **Lean** | `-lean` | 生产 | 定理证明 |
| **Lem** | 内部 | 内部 | 中间语言（桥接 OCaml/Isabelle/HOL4） |
| **SystemVerilog** | `--sv` | 实验 | 生成参考模型用于硬件形式验证（如 JasperGold） |
| **SMT** | `-smt` | 实验 | SMT-based 符号执行 |
| **LaTeX** | — | 生产 | 文档 snippet 生成（含入 ISA 手册） |
| **AsciiDoc** | — | 生产 | RISC-V spec 文档标注原型 |
| **JSON/HTML** | — | 生产 | 用于文档标注 |

**关键依赖链**：
- C 后端需要 GMP（高精度算数）和 zlib（ELF 加载）
- Z3 用于类型检查时的约束求解（bitvector 宽度恒等式等）
- 所有后端共用同一套 Sail 源码 + 类型检查流水线

### 1.4 编译流水线

```
Sail 源文件 (.sail + .sail_project) 
    → Sail 类型检查器 (Z3 约束求解)
    → 后端代码生成
    → C 代码 (sail_riscv_model.{h,cpp})
    → 用户提供的 C++ harness (ELF 加载、platform 设备、内存映射)
    → 可执行仿真器
```

**来源**: Sail 官方 README、INSTALL.md、manual.html（alasdair.github.io）；sail-riscv README。

---

## 2. sail-riscv = 定位 B 的范例

### 2.1 官方地位

sail-riscv（`github.com/riscv/sail-riscv`）**已被 RISC-V International 采纳为 RISC-V 的正式形式化规格**。仓库在 `riscv` GitHub org 下，不是个人项目。

### 2.2 Ratification 流程与 Sail 的关系

RISC-V 的 ratification 流程中，**Sail 模型是 Golden Model**：
- ISA 扩展提案需提供 Sail 形式化定义作为规范化参考
- 邮件列表 `tech-golden-model@lists.riscv.org` 负责协调
- RISC-V 非特权卷的文档标注原型使用 Sail 生成的 JSON/HTML artifact 直接嵌入 prose 手册（`github.com/Timmmm/riscv-isa-manual`）
- 这意味着**官方 ISA prose 手册与 Sail 模型双轨同步维护**，Sail 是机器可执行 truth

### 2.3 主从关系

- **Prose 手册**（PDF/AsciiDoc）: 人类阅读 + ratification 审批
- **Sail 模型**: **机器可执行 truth**，是所有 simulator 实现（Spike、QEMU 等）的终极 oracle
- Sail → prose: AsciiDoc/LaTeX 代码片段直接由 Sail 模型生成嵌入手册（避免 drift）
- prose → Sail: prose 中的语义描述必须在 Sail 中有对应实现

### 2.4 仓库结构与维护模式

```
sail-riscv/
  model/                    # Sail 规格模块
    prelude/                # 类型定义 + 错误定义
    core/                   # 寄存器、CSR、内存接口、扩展基础设施
    sys/                    # 物理/虚拟内存、异常分发、platform 设备
    exceptions/             # 同步异常
    pmp/                    # 物理内存保护
    extensions/             # 各 ISA 扩展子模块（I/M/A/F/D/C/V/Zk*...）
      I/base_insts.sail     # ITYPE/LOAD/STORE 等基础指令
      ...
    postlude/               # fetch-decode-execute 循环、配置验证
  c_emulator/               # C++ harness（ELF 加载、platform 设备、内存映射）
  handwritten_support/      # 定理证明器的手写支撑文件
  test/                     # riscv-tests 集成
  doc/                      # ReadingGuide.md（357行）、AddingExtensions.md
  config/                   # JSON 配置模板
```

**关键架构特征**：
- **模块化**：每个 ISA 扩展是独立模块，在 `riscv.sail_project` 中声明依赖
- **Scattered definitions**：指令的 union clause、decode mapping、execute function、assembly mapping 可以跨越文件但逻辑聚合
- **配置驱动**：JSON 配置文件控制 RV32/RV64、扩展启用、物理内存布局
- **贡献指南**：完整的 CONTRIBUTING.md + CODE_STYLE.md
- **测试套件**：riscv-tests 自动下载执行（CMake CTest）

### 2.5 新增扩展指南

`doc/AddingExtensions.md`（102 行）给出标准流程：
1. `<ext_name>.sail` 文件放在 `model/extension/<ext_name>/`
2. 在 `extensions.sail` 中注册 enum clause
3. 在 `config.json.in` 中添加 `"supported"` 字段
4. 定义 `hartSupports` / `currentlyEnabled` clause
5. 指令通过 `union clause instruction` + `mapping clause encdec` + `function clause execute` 定义

**来源**: sail-riscv README, ReadingGuide.md, AddingExtensions.md, CONTRIBUTING.md。

---

## 3. RTL Tandem 流程

### 3.1 核心协议：RVFI-DII

TestRIG 定义 **RVFI-DII**（RISC-V Formal Interface - Direct Instruction Injection）协议：

**指令注入包（8 bytes）**:
```
padding | rvfi_cmd | rvfi_time(16) | rvfi_insn(32)
```
- `rvfi_cmd = 0`: EndOfTrace (重置 DUT)
- `rvfi_cmd = 1`: Instruction (执行 rvfi_insn)

**执行追踪包（88 bytes）**:
```
rvfi_intr | rvfi_halt | rvfi_trap | rvfi_rd_addr | rvfi_rs2/rs1_addr | 
rvfi_mem_wmask/rmask | rvfi_mem_wdata(64) | rvfi_mem_rdata(64) |
rvfi_mem_addr(64) | rvfi_rd_wdata(64) | rvfi_rs2/rs1_data(64) |
rvfi_insn(64) | rvfi_pc_wdata/rdata(64) | rvfi_order(64)
```

关键字段涵盖：寄存器读写地址与数据、内存读写地址/数据/mask、PC 前后值、trap flag。

### 3.2 TestRIG 差分验证框架

```
Vengine (QuickCheck/GHC)
   ├── DII 指令流 → Sail (Golden Model) → RVFI 执行追踪
   └── DII 指令流 → RTL DUT → RVFI 执行追踪
                     ↓
           逐指令比对 RVFI trace → 分歧定位
```

**已验证的组合**（TestRIG README）：
- Sail vs Spike
- Sail vs RVBS (Bluespec SystemVerilog)
- Sail vs Toooba (RTL)
- Sail vs Piccolo (RTL)
- Sail vs Flute (RTL)
- Sail vs Ibex (RTL)
- Sail vs QEMU

**关键要求**（对 DUT）：
1. **直接指令注入**：绕过 ICache/分支预测，直接从 RVFI-DII socket 接收指令
2. **RVFI trace 报告**：保留 pipeline 执行追踪到结束，经 socket 发送
3. **TestRIG 触发复位**：每个 EndOfTrace 后完整复位寄存器/内存
4. **64KB 内存 @ 0x80000000**：统一地址空间便于测试生成

### 3.3 Sail 在 DV 流程中的位置

```
        Sail Golden Model
              |
    ┌─────────┼─────────┐
    |         |         |
  TestRIG  RVFI-DII  Formal
  (rand)   (tandem)  (JasperGold via SV backend)
    |
  RTL DUT
```

- **Sail 是黄金参考**：所有 RTL 比对都对 Sail（与 spec 保持一致）
- **Random instruction generation**：QuickCheck vengines 生成随机 DII 流，覆盖率远超人写测试
- **Counterexample reduction**：分歧后自动缩短到最少指令数
- **覆盖率测量**：Sail C 仿真器自带 spec branch coverage 测量（可 HTML 标注源码）

### 3.4 SystemVerilog 后端（实验性）

Sail 0.20+ 支持 `--sv` 生成 SystemVerilog 参考模型，可与 verilator 集成（`--sv-verilate`）。这使 Sail 不仅能生成 C 仿真器用于 tandem，还能**直接生成 SV 参考模型**用于形式验证工具（如 JasperGold）。

**来源**: TestRIG README, RVFI-DII.md, sail-riscv ReadingGuide.md。

---

## 4. 形式化证明流程

### 4.1 Sail → 定理证明器导出

Sail 生成**三种层次的定理证明器定义**：

| 层次 | 目标工具 | 用途 |
|------|---------|------|
| State monad (nondet + exceptions) | Isabelle, Rocq, Lean | 顺序代码推理 |
| Free monad (memory actions) | Isabelle, Rocq, Lean | 并发/弱内存模型推理（RMEM 工具） |
| SMT symbolic evaluator | Isla | 自动测试生成 + 二进制代码验证 |

**Islaris**（PLDI 2022）：集成 Isla 符号求值器 + Iris 程序逻辑，对**真实二进制代码**进行交互式验证（proof about binary code against authoritative ISA semantics）。

### 4.2 已验证的性质（以 Morello 为例）

Morello（CHERI-Arm）安全证明（ESOP 2022，Thomas Bauereiss et al.）：

- Sail Morello 模型从 Arm 内部 ASL 自动翻译生成
- Sail → Isabelle/HOL 导出
- 在 Isabelle 中证明：
  - **Capability monotonicity**：capability 权限在体系结构执行中单调递减
  - **Sealed capability integrity**：sealed capability 不能被非授权代码操纵
  - **Exception safety**：异常处理不泄露 capability 权限
- 这是 **ISA 级形式化证明的标杆**——Sail 是使此类证明成为可能的语言基础

### 4.3 sail-riscv 的形式化现状

sail-riscv 定理证明器导出已支持 **Isabelle**、**Rocq (Coq)**、**Lean**。仓库包含 `handwritten_support/` 为各证明器提供库定义。具体已证明的 ISA 级性质：
- **编码无歧义**：Sail 类型检查确保 decode 双向映射完整性
- **寄存器不变量**：通过 Sail 类型系统静态保证（如 `rd0` 硬连线零）
- **异常完备性**：Sail 的 `match` exhaustiveness check + exception mechanism
- **Concurrency**: RVWMO 弱内存模型与 axiomatic model 一致（7000+ litmus tests）

**投入产出**：
- Morello 证明：多人年工作量（但包含完整的 CHERI capability 模型复杂度）
- 对 DADAO 规模（87 条标量指令、无并发需求、无 MMU 复杂度），形式化证明门槛显著降低

**来源**: Sail 官方 README（Papers section），sail-riscv README，Morello ESOP 2022 论文。

---

## 5. DADAO 在 Sail 的表达可行性

针对 DADAO 5 个关键特性逐条评估：

### 5.1 双寄存器组 RD/RB

**Sail 惯用法**: 已有蓝本。

sail-riscv 的通用寄存器用 `vector(32, dec, xlenbits)` 实现，并 overload `X(r)` 同时做 read/write。DADAO 类似：

```sail
// RD bank
register RDs : vector(64, dec, bits(64))
// RB bank  
register RBs : vector(64, dec, bits(64))

// RB0 special: hardware-maintained, bits[63:48] = 0
// Similar to RISC-V x0 hardwired zero pattern
```

**已知实践**：CHERI 模型中 capability 寄存器伴随通用寄存器，与 RD/RB 双 bank 结构类似。Sail 的 `register` + overload 组合足以实现。

### 5.2 48 位有效地址 + 16 位保留

**Sail 惯用法**: 天然支持。

Sail 的轻量依赖类型允许精确指定 bitvector 宽度：

```sail
type ea_bits = bits(48)   // 有效地址
type rb_bits  = bits(64)  // 寄存器全宽

// EA 计算：rbhb[47:0] + offset mod 2^48
function compute_ea(rbhb : bits(64), offset : bits(48)) -> bits(48) = {
  let lo = rbhb[47 .. 0];
  (lo + offset)[47 .. 0]  // 隐式 mod 2^48
}
```

高位位截断和保留规则直接通过 slice notation 表达。sail-riscv 中已有类似的地址截断模式（如 Sv39/Sv48 地址翻译）。

### 5.3 Big-endian

**Sail 惯用法**: Sail 内存接口本身与 endianness 解耦。

Sail 的 `read_ram` / `write_ram` builtin 由后端实现提供；C harness 中用户代码负责 endianness 转换。实际做法：
- 在 Sail DSL 层用 bitvector 操作实现 big-endian byte layout（`spec.md §2.1`）
- 或通过 memory interface 的 `byte_width` 参数控制

**已知实践**：POWER model（旧版 Sail）使用了 increasing bit-order（`default Order inc`），与 DADAO 的 big-endian 需求类似（虽然 POWER 使用的是大端位序而非大端字节序）。

### 5.4 Fault 模型（ILLI/MALIGN/UNDI） + 精确异常

**Sail 惯用法**: Sail 原生支持。

Sail 有内建 `throw` / `try-catch` 异常机制：

```sail
// 精确异常：无架构副作用（与 spec.md §2.7 对齐）
exception ILLI
exception MALIGN  
exception UNDI

function clause execute(ldo(rdha, rbhb, imms12)) = {
  let ea = compute_ea(RB(rbhb), sext_12(imms12));
  if rdha == 0b000000 then throw ILLI();     // spec §2.6.1
  if ea[2 .. 0] != 0b000 then throw MALIGN(); // spec §3.1 alignment
  RD(rdha) = read_mem(ea, 8);
  RETIRE_SUCCESS
}
```

sail-riscv 的 `Illegal_Instruction()` 即此类模式。**精确性**由 Sail 执行模型保证：exception 发生时所有副作用回滚。

### 5.5 RA 栈（RegRAS）

**Sail 惯用法**: 用 mutable `register` + 向量操作实现。

```sail
register RAs : vector(64, dec, bits(64))  // ra0..ra63

// ra63[63:48] = ref count, ra63[47:0] = return address
function push_ras(ret_addr : bits(48)) -> unit = {
  let rc = RAs[0][63 .. 48];  // ra63 ref count
  if rc == 0x0000 then {
    RAs[0] = 0x0001 @ ret_addr;  // set ref=1, store addr
  } else if rc < 0xFFFF & RAs[0][47 .. 0] == ret_addr then {
    RAs[0][63 .. 48] = rc + 1;   // recursion
  } else {
    if RAs[63][63 .. 48] != 0x0000 then throw RASOF();
    // shift down: ra{i-1} ← ra{i} for i=2..63
    foreach (i from 63 to 2) {
      RAs[i - 1] = RAs[i];
    };
    RAs[0] = 0x0001 @ ret_addr;
  };
}
```

复杂度中等但完全可行。sail-riscv 中 CSR 操作（`mstatus`、`mepc` 等 bitfield 操作）已有类似模式。

### 5.6 总体评估

| 特性 | 可行性 | 难度 | 风险 |
|------|--------|------|------|
| 双寄存器组 RD/RB | 可行 | 低 | 无 |
| 48 位有效地址 + 16 位保留 | 可行 | 低 | 无 |
| Big-endian | 可行 | 中 | C harness 端实现，需验证 |
| ILLI/MALIGN/UNDI 精确异常 | 可行 | 低 | 无 |
| RegRAS | 可行 | 中 | 实现复杂度中等，测试用例多 |
| 多 bank 块复制 (rd2rd/rd2rb...) | 可行 | 低 | Sail for loop 直接映射 |

**结论**: DADAO 全部 M1 特性可在 Sail 中干净建模，无阻挠问题。

**来源**: ISA spec.md §1-§5；Sail manual（类型系统、异常、bitvector 操作章节）；sail-riscv 源码结构分析；CHERI Sail 模型作为多 bank 寄存器参考。

---

## 6. 定位 B 的治理

### 6.1 权威层次重排

定位 B 将 Sail 变为新的权威源后：

```
          wiki（散文源）
            |
    ┌───────┼───────┐
    |       |       |
  Sail   spec.md  （人工对照参考）
（权威）    |
    ┌───────┼───────┬───────┐
    |       |       |       |
  QEMU   gem5    interp   LLVM
```

关键变化：
- **Sail 是 truth**：QEMU/gem5/interp 的差分 target 从 spec.md 迁移到 Sail
- **spec.md 退居对照参考**：保留为 human-readable 解释文档，其规范性断言引用 Sail clause（类似 sail-riscv 的 AsciiDoc 文档标注）
- **opcodes.yaml**：encoding 层可继续存在作为交叉校验工具（M3 legality 矩阵），但 encoding truth 由 Sail `mapping clause encdec` 派生

### 6.2 迁移路径

**阶段 1（彩排）**：垂直切片 Sail 模型与 spec.md 并存，不取代。建立 `wiki → Sail → C 仿真器 → 差分 QEMU` 闭环，验证可行性。

**阶段 2（完整 Sail）**：87 条全量 Sail 模型完成，开始取代 spec.md 的脚本生成（encoding vector、legality 矩阵从 Sail 派生而非 opcodes.yaml）。

**阶段 3（权威化）**：wiki 团队审计背书 → Sail 正式成为权威源。spec.md 重构为 Sail 注释 + human-readable 解释。

**阶段 4（下游）**：QEMU/gem5/LVM 的 oracle target 全部切到 Sail。

### 6.3 wiki 团队参与背书

**现实约束**（ADR-0009 §M2b）：
- wiki 团队是 16 个纯 markdown 文件的作者，非可执行规范团队
- **审计背书 = 人工逐条 review**，节奏不可控
- 类似 RISC-V：prose 手册作者 + Sail 作者协作维护双轨同步

**降低背书门槛的措施**：
- Sail 从 spec.md 生成的 AsciiDoc 标注可入 wiki 文档（可视化 diff）
- 差分（Sail vs QEMU vs gem5）结果作为变更证据包提交 wiki 团队
- 承诺"wiki 一旦更正 bug，Sail 立即跟随修改"→ 团队不担心 Sail 越权

### 6.4 spec.md 是否被取代

| 选项 | 推荐度 | 理由 |
|------|--------|------|
| Sail 完全取代 spec.md | 不推荐 | spec.md 承载 prose 解释、ADL 决策、historically resolved open issues，这些不是 Sail 擅长表达的 |
| 并存互校（双轨） | **推荐** | Sail 是机器 truth，spec.md 是 human-readable 注释 + 决策记录；类似 RISC-V prose manual ↔ sail-riscv |
| spec.md 作为 Sail 生成目标 | 长期可能 | 如果 Sail AsciiDoc/LaTeX 后端成熟到可直接生成 spec.md 的全部表格和编码记录 |

**来源**: ADR-0009 §M2b 及"研究终局"讨论；04-multi-implementation-differential.md §②→① 区分；sail-riscv AsciiDoc 标注实践。

---

## 7. 垂直切片方案草案 + 工作量

### 7.1 建议指令覆盖（~20-30 条）

| 类别 | 指令 | 覆盖特性 |
|------|------|---------|
| **算术** | addi, add, sub, muls, divu, and, orr, xor, xnor | RD 双输出、寄存器/立即数两种格式、全 64 位 + 128 位中间值 |
| **移位/扩展** | shlu(i), shrs(i), exts(i) | orrr/orri 格式、6-bit 移位量 |
| **比较** | cmps(i), cmpu(i), cmp-rb | 多 bank 操作、RB 低位比较 |
| **加载** | ldo, ldbs, ldmo(rb) | RD/RB 加载、签名扩展、多寄存器模式、地址对齐+MALIGN |
| **存储** | sto, stb, stmo(rb) | RD/RB 存储、多寄存器模式 |
| **分支** | brz, brnz, breq, brne | 条件分支、单/双寄存器条件 |
| **跳转/调用** | jump(imm), call(imm), ret | 控制流 + RAS push/pop |
| **Fault** | 触发 ILLI/MALIGN/UNDI | 精确异常验证 |
| **块复制** | rd2rd, rd2rb, rb2rd | 跨 bank 多寄存器传输 |
| **wyde 立即数** | setzw, orw | rwii 格式、wyde-position 控制 |

**选择原则**：
- 覆盖所有 6 种格式（iiii, oiii, orii, orri, orrr, rrrr, rrii, rrri, riii, rwii）
- 覆盖所有 4 个 bank（RD/RB/RA）
- 覆盖 fault 3 类（ILLI/MALIGN/UNDI）
- 覆盖 RAS push/pop
- 覆盖多寄存器操作

### 7.2 最小闭环流水线

```
(1) wiki (§SimRISC-00..04, §DADAO-11-AEE)
        ↓ 人工翻译
(2) Sail 源文件 (.sail + .sail_project)
        ↓ sail -c
(3) C 仿真器 (dadao_sail_sim)
        ↓ run_sail_test.py (封装 ELF 加载 + 寄存器/内存 dump)
(4) JSON 执行 trace
        ↓ run_differential (新增第 4 列: sail_col)
(5) 4 方 AGREE: QEMU vs gem5 vs interp vs Sail
        ↓
(6) 分叉 = 真 bug 信号
```

**各环节映射到现有基础设施**：
- (3) → 类似 sail-riscv 的 `c_emulator/riscv_sim.cpp`，DADAO 需要自己的 ELF 加载器（big-endian）和简单 platform
- (4) → 类似现有 `run_qemu_test.py` / `run_gem5_test.py` 模板
- (5) → 扩展现有 `run_differential` 增加 `sail_trace` 列

### 7.3 前置工具链安装

**步骤（一次性，2-4 小时）**：
1. `sudo apt-get install opam build-essential libgmp-dev z3 pkg-config`
2. `opam switch create 5.4.1`
3. `eval $(opam env)`
4. `opam install sail`
5. 验证：`sail --help` 输出正常

**不需要额外依赖**（Sail 编译器自带标准库 + Lem）。

### 7.4 工作量估算

| 阶段 | 内容 | 工时 | 风险 |
|------|------|------|------|
| **前置** | opam/OCaml/Sail 安装 + 环境验证 | ~0.5d | OCaml 版本兼容问题 |
| **Sail 学习** | 阅读 manual + sail-riscv ReadingGuide + 手写 5 条 toy 指令 | 2-3d | 依赖类型概念曲线 |
| **DADAO core 建模** | 寄存器 bank (RD/RB/RA)、内存接口、fault 基础设施、decode skeleton | 2-3d | 多 bank 初始化、big-endian 内存接口 |
| **指令编写 (20-30条)** | 算术(6) + 移位(4) + 比较(3) + 加载(4) + 存储(2) + 分支(4) + 控制流(3) + fault + 块复制 | 5-8d | 双输出 add/sub 的 128 位中间值在 Sail 中需显式表达 |
| **C harness** | ELF 加载器 (big-endian)、简单 platform (64KB 内存 @ 0x80000000)、trace 输出 | 2-3d | DADAO 没有现成的 ELF 加载器（需手写或适配 sail-riscv 的） |
| **差分集成** | run_sail_test.py + run_differential 第 4 列 | 1-2d | trace 格式对齐（确保 QEMU/gem5/interp/Sail 字段名一致） |
| **测试调试** | 编写 30+ 编码向量 + 来回调试 Sail vs QEMU 分叉 | 3-5d | 首次差分会暴露多个 QEMU bug——这正是彩排目的 |

**总计**: 约 **3-4 周**（1 人全职），含来回调试。

### 7.5 主要风险

| 风险 | 概率 | 对策 |
|------|------|------|
| DADAO big-endian 与 sail-riscv（小端）ELF 加载器不兼容 | 高 | 手写 ELF loader（~200 行 C）或直接 RVFI-DII 注入跳过 ELF |
| Sail C harness 的 ELF/内存模型与 QEMU 测试框架的 exit-MMIO 机制不同 | 中 | 简化：不用 ELF，用 RVFI-DII 指令注入直接对比 trace |
| Sail 模型与 wiki 不等价（翻译错误） | 中 | 彩排本身就是发现这种错误的手段；分叉即信号 |

**来源**: ADR-0009 §M2b（彩排 charter）；sail-riscv 代码结构 + build_simulator.sh 分析；TestRIG RVFI-DII 协议（可绕过 ELF 兼容性问题）。

---

## 结论与建议

### Sail 定位 B 可行性：**可行，推荐执行**

- **直接蓝本**：sail-riscv（1900+ commits, RISC-V International 官方采纳）
- **DADAO 特性全部可表达**：双寄存器组、48 位地址、big-endian、精确异常、RAS
- **RTL tandem 流程已成熟**：TestRIG + RVFI-DII 在 CHERI 项目中验证过多个 RTL 实现
- **形式化证明路径存在**：Sail → Coq/Isabelle/Lean，Morello 安全证明为标杆
- **现在是最佳时机**：87 条标量指令、无 MMU/并发——学习成本最低

### 推荐动作

1. **按 ADR-0009 执行 M2b 垂直切片**，时间盒 4 周
2. **优先选择 RVFI-DII 注入模式**（不是 ELF 加载），避开 big-endian ELF 兼容性工作
3. **输出物**：Sail 模型 + C 仿真器 + 4 方差分报告 + 学习笔记（入 knowledge base）
4. **不在此阶段追求**：完整 87 条、Theorem prover 导出、wiki 团队背书——这些是下一项目的事

### 给架构师的 M2b charter 要点

- 明确彩排 cutoff 条件（指令数 + 功能点 + 4 方全绿 count）
- 指定 Sail 作者独立于 QEMU 作者（差分独立性纪律）
- 定义"失败止损"——什么情况下提前终止彩排（如工具链不可安装、3 周无进展）
- 定义"成功移交"——产出哪些文件/文档供后续任务消费
