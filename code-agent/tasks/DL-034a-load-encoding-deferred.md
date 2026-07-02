# DL-034a: rd-load-store deferred 测试重设计（14 条 load encoding）

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行（可与 DL-033a 并行）

---

## 背景

`tests/vectors/isa/rd-load-store.yaml` 中有 **14 条 load encoding 测试**，当前 `status: deferred`。

原设计：用 `rb0=0`（零地址）作为 load base → addr=0 → 访问未映射区域 → QEMU hang（无超时机制触发干净退出）。

根本问题：addr=0 物理上未映射（§6.1：0x00000000-0x000FFFFF 为 unmapped）。QEMU 访问未映射 MMIO 时卡住，既不抛 ILLI 也不退出。

---

## 目标

将 14 条 load encoding 测试重新设计为**合法性测试（legality）**：
- 将 `ha=0`（rb0 = 0地址）改为 `ha=0`（rd0，即零寄存器作为 opcode field 中 ha）→ 触发 ILLI（rd0 用于需要非零基址的字段）
- **OR** 改为 `rb1` 基址 + 指向 RAM 区的有效地址

DS 需从 spec.md 确认：load 指令中 ha=0 是否触发 ILLI（零寄存器作为 load base → 非法），还是仅导致地址为 0（合法但访问异常）。

---

## 接口说明书

### 1. 现状诊断

读取 `tests/vectors/isa/rd-load-store.yaml`，找出全部 14 条 `status: deferred` 的 load 测试，记录：
- mnemonic（ldb/ldw/ldt/ldo 等）
- 当前 word（encoding）
- 当前 expected_fault

### 2. 重设计方案

**方案 A（优先）：ha=rd0 → ILLI**

若 spec.md §2.6.1 规定 load 指令的 ha 字段（base 寄存器选择）为 rd bank 且为 rd0 时触发 ILLI：
- 确认 translate.c 中对应 trans_ldb/ldw/ldt/ldo 有 `if (ha==0) raise ILLI` 检查
- 修改 yaml：`expected_fault: null → ILLI`；`status: deferred → active`
- 此方案不需要修改 expected_fault（只改 status），因 ILLI 本已是语义结果

**方案 B：使用有效基址**

若 ha=0 不触发 ILLI（只是地址为 0 的合法但不可访问操作）：
- 在 `input_state` 中加 `rb1: "0x0000000080000000"`（BINARY_BASE）
- 修改 encoding word 中 ha 字段 = 1（rb1 = 0x80000000）
- `expected_fault: null`，`status: active`（加载合法 RAM 地址）
- 加载值 = 测试 binary 自身的内容（随机但可接受）

### 3. load_reg 产生的二进制中的加载地址

若选方案 B：`rb1 = BINARY_BASE = 0x80000000`。load 目标地址 = `rb1 + imm12`，保持 imm12=0，访问 BINARY_BASE = setup code 第一条指令。这是安全的（RAM 内合法地址，能读到 setzw 指令字）。

### 4. 修复 encoding bits

若 ha 字段在 load 指令中位于 bits[23:18]（与 store 对称）：
- 原 `ha=0`（rb0）：bits[23:18] = 0 → 编码 0x38000000（ldb 示例）
- 改 `ha=1`（rb1）：bits[23:18] = 1 → 编码 0x38040000

DS 必须从 spec.md § 手推，不从 QEMU 行为反推。

---

## 约束

- 只修改 `tests/vectors/isa/rd-load-store.yaml`（纯数据任务）
- 不修改 translate.c（若 ha=0→ILLI 检查已存在则 PASS，若不存在需另建任务）
- 14 条全部 active 后基线不低于 137+14=151 PASS

---

## 验收

```bash
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-load-store.yaml
# 期望：≥ 34+14 = 48 PASS（原 34 + 新激活 14），0 FAIL，0 timeout
```

---

## 参考指针

- 知识库 §2（ISA 合法性约束）、§6.1（内存映射，addr=0 unmapped）
- spec.md §3.2（load/store legality，ha 字段约束）
- translate.c `trans_ldb`/`trans_ldw`/`trans_ldt`/`trans_ldo` 实现（ha==0 检查）
- rb-ops.yaml 的 deferred ldo 测试（类似问题，可参考同样设计）

---

## 完成区

（DS 填写）
