# DL-008a: LLVM Register TableGen（Phase 2 寄存器模型）

**执行环境**：本地 DS · DADAO-0628

---

## 目标

在 DL-007a 骨架上，用 LLVM TableGen 定义 DADAO 全部寄存器 bank（RD/RB/RF/RA），
设置 M1 可分配集合和保留寄存器约束，使 `make build-mc` 仍然 PASS，
并为 DL-009a（指令格式 TableGen）提供完整寄存器类型。

---

## 交付物

### 1. Patch（`components/llvm/patches/0003-dadao-register-info.patch`）

内容包含以下文件（全部位于 `llvm/lib/Target/DADAO/`）：

#### 1.1 `DADAORegisterInfo.td`

按 `contracts/isa/spec.md §1` 和 `contracts/abi/spec.md §1` 定义：

**RD bank（64 个寄存器）**

| 寄存器 | ABI 角色 | M1 可分配？ |
|--------|---------|-----------|
| rd0 | 硬连接零，immutable | ❌ |
| rd1 | kernel-reserved（M1 视为 non-allocatable）| ❌ |
| rd2–rd7 | ABI-reserved | ❌ |
| rd8–rd15 | 临时寄存器（caller-saved）| ✅ |
| rd16–rd31 | 参数/返回值（caller-saved）| ✅ |
| rd32–rd63 | callee-saved | ✅ |

注册两个寄存器类：
- `GPRD`：全部 64 个 RD 寄存器（for MC 用途）
- `GPRD_Allocatable`：仅 rd8–rd63（for CodeGen 用途，Phase 5；Phase 2 只需定义，不需连接 isel）

**RB bank（64 个寄存器）**

| 寄存器 | ABI 角色 | M1 可分配？ |
|--------|---------|-----------|
| rb0 | PC-proxy / 地址基址（[63:48]=0，immutable）| ❌ |
| rb1 | Stack pointer（SP，frame management only）| ❌ |
| rb2 | Frame pointer（FP，managed by prologue/epilogue）| ❌ |
| rb3 | Global pointer | ❌ |
| rb4 | Thread pointer | ❌ |
| rb5–rb7 | ABI-reserved | ❌ |
| rb8–rb15 | 临时（caller-saved）| ✅ |
| rb16–rb31 | 参数地址（caller-saved）| ✅ |
| rb32–rb63 | callee-saved | ✅ |

注册：`GPRB`（全部 64）和 `GPRB_Allocatable`（rb8–rb63，Phase 5 用）。

**RF bank（64 个寄存器）**

- M1 scope 不含 FP 指令（`contracts/isa/spec.md §7`）
- 定义 rf0..rf63，注册 `GPRF` 类，全部标记 non-allocatable（Phase 5 前不使用）

**RA bank（64 个寄存器）**

- ra0 固定 0（per ISA spec §1）；ra1..ra63 = RegRAS 栈，由 call/ret 指令隐式管理
- 全部 non-allocatable（不走通用寄存器分配器）

**特殊别名寄存器（在 `DADAORegisterInfo.td` 中用 `def` 别名）**：
- `RBSP = rb1`（stack pointer）
- `RBFP = rb2`（frame pointer）

#### 1.2 `DADAORegisterInfo.h` / `DADAORegisterInfo.cpp`

- `DADAORegisterInfo` 继承 `DADAOGenRegisterInfo`（TableGen 生成）
- 实现必须的纯虚函数：`getCalleeSavedRegs()`（返回空数组，Phase 5 填充）、
  `getReservedRegs()`（标记 rd0/rd1/rd2..rd7/rb0..rb7 等）、
  `eliminateFrameIndex()`（存根，报 `llvm_unreachable`，Phase 5 实现）
- 获取 SP：`getFrameRegister()` → rb1

#### 1.3 顶层 `DADAO.td`

创建（或更新）`DADAO.td`，include `DADAORegisterInfo.td`（DL-009a 将再 include 指令 .td）。

#### 1.4 `CMakeLists.txt` 更新

添加 `tablegen(LLVM DADAOGenRegisterInfo.inc -gen-register-info)` 调用，
并将 `DADAORegisterInfo.cpp` 加入 source list。

#### 1.5 `DADAOMCTargetDesc.cpp` 或 `DADAOTargetMachine.cpp` 更新

注册 `createDADAORegisterInfo` 函数（或等价方式），使 `llvm-mc` 能实例化 target。

---

### 2. `components/llvm/patches/series` 更新

追加 `0003-dadao-register-info.patch` 到 series 末行。

---

## 约束

1. **`make build-mc` 必须仍然 PASS**：patch apply → cmake → ninja llvm-mc 无错
2. **只定义寄存器，不写指令**：本任务不引入 `DADAOInstrInfo.td`；DL-009a 负责
3. **对齐 contract 数量**：64 × 4 = 256 个 RegisterDef，不多不少
4. **M1 非分配集合精确**：按 `contracts/abi/spec.md §1` 列表，不自行扩展或缩减
5. **RF/RA 全部 non-allocatable**：`isAllocatable = 0`，注释说明 scope defer 原因
6. **不引用行号**：所有合约引用用章节号（§N）
7. **patch 03 紧接 patch 02 apply**：确保在 `.work/llvm/` apply 03 之前 01+02 已 apply

---

## 验收步骤（DS 完成区填写）

```
make build-mc          →  cmake + ninja: PASS（无新增错误/警告）
llvm-mc --version      →  "dadao - DADAO" 仍在目标列表
grep -r "GPRD\|GPRB" .work/build/llvm/include/llvm/Support/  →  生成的 .inc 文件存在
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `contracts/isa/spec.md §1` | 寄存器 bank 定义、bank 宽度、rd0/rb0 immutable 规则 |
| `contracts/abi/spec.md §1` | M1 可分配集合、SP/FP/GP/TP 角色 |
| `llvm/lib/Target/Lanai/LanaiRegisterInfo.td` | 最简 register .td 风格参考 |
| `llvm/lib/Target/RISCV/RISCVRegisterInfo.td` | 多 bank 参考 |
| `components/llvm/patches/series` | 已有 patch 顺序 |
| `code-agent/designs/0002-detailed-roadmap.md` §Phase 2 | DL-008a 任务边界 |

---

## 完成区

**状态**：已完成（待 Codex Review）
**修改文件**：
- `components/llvm/patches/0003-dadao-register-info.patch` — 新增
- `components/llvm/patches/series` — 更新

**验证结果**：
```
$ make build-mc
... cmake + ninja ...
build-mc: PASS

$ find .work/build/llvm/lib/Target/DADAO -name "*RegisterInfo*"
DADAOGenRegisterInfo.inc
DADAOGenRegisterInfoEnums.inc
DADAOGenRegisterInfoHeader.inc
DADAOGenRegisterInfoMCDesc.inc
DADAOGenRegisterInfoTargetDesc.inc
```

**关键实现**：
- 4 bank × 64 = 256 个 RegisterDef
- GPRD/GPRD_Allocatable, GPRB/GPRB_Allocatable, GPRF, GPRA
- rd0-rd7 + rb0-rb7 reserved, RF/RA all non-allocatable
- RBSP=rb1, RBFP=rb2 别名

---

## Architecture Review (2026-06-29)

**评审结论**：**Accepted — 寄存器 TableGen 生成正确。**

### 运行验证

```
$ make build-mc → PASS (ninja: no work to do)
$ find .work/build/llvm/lib/Target/DADAO -name "*RegisterInfo*"
DADAOGenRegisterInfo.inc
DADAOGenRegisterInfoEnums.inc        ← GPRD=3, GPRB=2, allocatable subsets
DADAOGenRegisterInfoMCDesc.inc
DADAOGenRegisterInfoHeader.inc
DADAOGenRegisterInfoTargetDesc.inc
```

### 逐项验证

| 需求 | 状态 |
|------|------|
| 4 bank × 64 = 256 RegisterDef | ✅ enums 生成正确 |
| GPRD / GPRD_Allocatable 类 | ✅ GPRD=3, GPRD_Allocatable=1 |
| GPRB / GPRB_Allocatable 类 | ✅ GPRB=2, GPRB_Allocatable=0 |
| GPRF 类 (non-allocatable) | ✅ |
| GPRA 类 (non-allocatable) | ✅ |
| rd0 immutable, rd1–rd7 reserved | ✅ per ABI spec |
| rb0–rb7 reserved | ✅ rb0 PC, rb1 SP, rb2 FP, etc. |
| RBSP=rb1, RBFP=rb2 别名 | ✅ |
| DADAORegisterInfo.cpp (getReservedRegs) | ✅ |
| CMakeLists.txt 更新 (tablegen + reginfo.cpp) | ✅ |
| series 追加 0003 | ✅ |
| make build-mc PASS | ✅ |

### 最终判断

寄存器模型完整，与 `contracts/abi/spec.md §1` 可分配集合精确一致。
可直接 accept。
