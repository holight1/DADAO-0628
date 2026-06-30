# ADR-0007: 测试方法论（独立预期值原则）

**状态**：Accepted  
**日期**：2026-06-30  
**关联**：ADR-0003（ELF ABI）、ADR-0004（Test Machine）、ADR-0005（LLVM baseline）、ADR-0006（QEMU baseline）

---

## 背景

DADAO-0628 是从零开始的 greenfield 工具链重建（ADR-0001）。工具链同时包含
汇编器（LLVM MC）和执行器（QEMU）；两者输出的期望值如果互相依赖，任何系统性
偏差都会被掩盖，直到集成测试才暴露，代价极高。

历史教训（上一版本 llvm-unicore）：部分任务要求依据 LLVM 实际输出填写 CHECK，
且 DL-002h 曾在 lit 2/2 PASS 时遗漏 resolved `.equ` fixup 路径；第二个 fixup
实际被静默写成 0。测试 oracle 或覆盖范围依赖被测实现时，绿色结果不能证明编码正确。

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

`-filetype=asm` 覆盖解析和规范化文本输出，`-filetype=obj` 覆盖编码、fixup 和
ELF object 生成；两条路径必须独立测试。

只测 `-filetype=asm` 通过不代表 `-filetype=obj` 正确；MCFixup → ELF relocation
只在 object 路径中验证。

**每个 lit 测试文件必须包含两条 RUN 行：**

```asm
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=obj %s -o %t
# RUN: llvm-objdump -d %t | FileCheck %s
# RUN: llvm-mc --triple=dadao-unknown-elf -filetype=asm %s | FileCheck %s --check-prefix=ASM
```

### D4：测试先于实现（向量/失败测试与实现同批提交）

对应的 vector 和 lit 测试必须在实现或 fix 完成前就位，或与实现同批提交。
不单独建"补覆盖度"任务；禁止先实现再补测。

**各 class 归属 exit gate**：

| Class | 归属 Phase exit gate | 例外 |
|-------|---------------------|------|
| encoding | Phase 2 | — |
| legality | Phase 2/3 | — |
| semantic | Phase 3 | — |
| boundary | Phase 3 | — |
| overlap | Phase 3/4 | C-27 deferred（wiki 确认前） |

boundary 和已确定语义的 overlap 向量必须在各自 exit gate 前就位，不得以"Phase 3 收敛后补"为由推迟。

**根据**：上一版 DL-058a 审计发现 27 个已 PASS 测试中 42 条规格只有 16 条强覆盖、
12 条未覆盖；DL-058b 进一步发现 PASS 测试中存在"触发了错误机制却声称覆盖目标机制"
的问题——证明事后补测无法替代测试先行。

### D5：QEMU 测试协议（exit port 签名）

QEMU 语义测试基于 ADR-0004 定义的 exit port（@0x10000000）：

| exit code（低字节）| 含义 |
|------------------|------|
| 0x00 | PASS |
| 0x01–0x7F | 测试特定 FAIL |
| 0x81 | MALIGN（对齐异常，precise — 无内存写入）|
| 0x82 | ILLI（非法指令，precise — 无寄存器写入）|
| 0x83 | UNDI（保留编码）|

正常 PASS/FAIL 由测试程序写 exit port；fault code 由 QEMU 按 ADR-0004 直接返回，
harness 统一读取进程退出码并断言。

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

- boundary 向量当前普遍空缺；DL-010a/016a 配套 encoding/legality 向量亦尚未填充，是 Phase 2/3 exit gate 前必须关闭的债务
- C-27（条件赋值 overlap snapshot）overlap 向量 deferred，不阻塞 Phase 3 exit gate
- Phase 3 state-dump 协议（寄存器/内存完整状态读取）尚未定义，必须在第一个 Phase 3 任务下发前完成设计

---

## 参考

- `code-agent/designs/0003-testing-roadmap.md` — 完整分阶段测试计划
- `tests/vectors/schema.md` — 向量文件格式规范
- `tests/vectors/inventory.md` — 当前覆盖矩阵（各 opcode 各 class 是否已有向量）
- `knowledge-graph/compiler-backend/01-llvm-backend-phases.md` — lit 分层策略
- `knowledge-graph/compiler-backend/02-mc-fixup-relocation.md` — MCFixup 两层机制、每指令一 fixup
- `knowledge-graph/compiler-backend/05-qemu-tcg-target-porting.md` — TCG 异常处理陷阱
