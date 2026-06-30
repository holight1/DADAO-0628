# ADR-0007: 测试方法论（独立预期值原则）

**状态**：Accepted  
**日期**：2026-06-30  
**关联**：ADR-0003（ELF ABI）、ADR-0004（Test Machine）、ADR-0005（LLVM baseline）、ADR-0006（QEMU baseline）

---

## 背景

DADAO-0628 是从零开始的 greenfield 工具链重建（ADR-0001）。工具链同时包含
汇编器（LLVM MC）和执行器（QEMU）；两者输出的期望值如果互相依赖，任何系统性
偏差都会被掩盖，直到集成测试才暴露，代价极高。

历史教训（上一版本 llvm-unicore）：部分 encoding 测试的 CHECK 字节来自 LLVM
输出的复制粘贴，导致编码 bug 和测试同时存在，在长时间内保持"绿色"，
直到实际运行时才崩溃。

---

## 决策

### D1：独立预期值原则（核心）

**所有测试的期望值必须来自 `contracts/` 或 `tests/vectors/isa/*.yaml`，
不得从被测实现（LLVM/QEMU）的输出中获取。**

- `tests/vectors/isa/*.yaml` 中的每条 vector 是从 `contracts/isa/spec.md`
  手推的，与实现无关
- lit 测试的 CHECK 行字节序列必须手算（公式来自 §2.2–§2.4 + §2.8 opcode table）
- 禁止流程：`llvm-mc -o test.o && xxd test.o | copy-paste → CHECK`

### D2：五类向量分层

测试按向量 class 分层，各层有独立的通过标准：

| Class | 验证目标 | 工具 | Phase |
|-------|---------|------|-------|
| `encoding` | 指令字节序列正确 | `llvm-mc` + FileCheck | Phase 2 |
| `legality` | 非法操作数触发 ILLI，不产生寄存器写入 | `llvm-mc`（语法错误）或 QEMU（runtime ILLI）| Phase 2/3 |
| `semantic` | 正常执行后寄存器/内存状态正确 | QEMU + exit port | Phase 3 |
| `boundary` | 边界值（signed-min/max、zero、overflow）行为正确 | QEMU | Phase 3/4 |
| `overlap` | src=dst 寄存器重叠行为正确 | QEMU | Phase 4（C-27 resolved 后）|

### D3：两条 LLVM 路径分别测试

`-filetype=asm`（文本汇编）和 `-filetype=obj`（ELF object）的 fixup 处理
路径不同；两条路径必须独立测试。

只测 `-filetype=asm` 通过不代表 `-filetype=obj` 正确（MCFixup → ELF reloc 的
转换逻辑是独立代码路径）。

**每个 lit 测试文件必须包含两条 RUN 行：**

```asm
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d %t | FileCheck %s
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM
```

### D4：随修附测（不单独建测试任务）

lit 测试随 fix 任务同批提交，不独立开"补覆盖度"任务。理由：
- lit 测试的价值是防回归，不是发现新 bug
- 已知 bug 的情况下先写测试不加速进度
- 在 QEMU 语义测试高度收敛后才考虑系统性补 boundary/overlap 向量

### D5：QEMU 测试协议（exit port 签名）

QEMU 语义测试基于 ADR-0004 定义的 exit port（@0x10000000）：

| exit code（低字节）| 含义 |
|------------------|------|
| 0x00 | PASS |
| 0x01 | ILLI（非法指令，precise — 无寄存器写入）|
| 0x02 | MALIGN（对齐异常，precise — 无内存写入）|
| 0x03 | UNDI（保留编码）|
| 0xFF | 测试 harness 错误 |

exit code 的值由 trampoline + 测试程序协商写入，harness 读取并断言。

### D6：MCFixup 每指令一个原则

对于需要多条指令加载 64-bit 地址的序列（如 `setzw + orw × 3`），
每条指令发出独立的 MCFixup，不用单个 fixup 描述整个序列。

理由：链接器逐指令处理 reloc entry；单 fixup 只能填入一条指令，
其余指令永远是 0，链接后地址错误（历史教训：DL-010b/DL-010d）。

---

## 后果

### 正面

- 任何系统性编码 bug 在 Phase 2 lit 测试就能被发现，不推迟到运行时
- LLVM 和 QEMU 可以独立验证，互相交叉检查
- 向量文件（`tests/vectors/isa/*.yaml`）是永久性的人工记录，不随实现变化

### 负面 / 限制

- 手推字节比 copy-paste 更费时（每个 encoding vector 需要按 §2.2 公式计算）
- C-27 open issue 导致 overlap 向量暂时无法完整，需要 wiki 确认后补充

### 已知风险

- boundary 向量当前普遍空缺，是 Phase 4 前的计划性债务
- 汇编器（DL-010a）就绪前，QEMU 语义测试无法运行（汇编器是生成测试 binary 的工具）

---

## 参考

- `code-agent/designs/0003-testing-roadmap.md` — 完整分阶段测试计划
- `tests/vectors/schema.md` — 向量文件格式规范
- `tests/vectors/inventory.md` — 当前覆盖矩阵（各 opcode 各 class 是否已有向量）
- `knowledge-graph/compiler-backend/01-llvm-backend-phases.md` — lit 分层策略
- `knowledge-graph/compiler-backend/02-mc-fixup-relocation.md` — MCFixup 两层机制、每指令一 fixup
- `knowledge-graph/compiler-backend/05-qemu-tcg-target-porting.md` — TCG 异常处理陷阱
