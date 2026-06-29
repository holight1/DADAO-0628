# DL-002a — ABI 合约（非变参标量）

**状态**：待执行  
**执行环境**：本地 DS · DADAO-0628  
**类型**：合约文档  
**优先级**：Phase 0.5A 交付物；可与 DL-001b/001c 并行  
**前置任务**：DL-001a（`contracts/isa/spec.md` Accepted）

---

## 目标

从 Wiki `13a414da` (SimRISC 0.4.1) 的 AEE 文档撰写
`contracts/abi/spec.md`，覆盖 M1 BasicCodeGen 所需的非变参标量调用约定。

M1 scope 限定：**非变参函数**（no varargs）、**标量整数/指针参数和返回值**。
ABI contract 内容必须足够让 Phase 5 BasicCodeGen 实现正确的参数传递、返回值处理
和栈帧布局，不需要涵盖浮点 HFA/HPA 或复杂聚合。

---

## 交付物

| 文件 | 内容 |
|------|------|
| `contracts/abi/spec.md` | M1 非变参标量 ABI 合约（版本 0.1.0，Candidate）|

---

## spec.md 结构要求

```
# ABI Contract — DADAO SimRISC (M1 Non-variadic Scalar)

**Version**: 0.1.0
**Source**: Wiki commit `13a414da158dc780ae5501c1443acbffd15cbf4a` (SimRISC 0.4.1)
**Status**: Candidate

§1. Register Roles and Caller/Callee Classification
§2. Argument Passing
§3. Return Values
§4. Stack Frame Layout
§5. Call Sequence (Prologue/Epilogue)
§6. Open Issues
Appendix: Wiki Citations
```

---

## 内容要求

### §1 寄存器角色与保存约定

从 AEE 文档中提取：

- **GPRD**（rd0–rd63）：哪些是 caller-saved，哪些是 callee-saved，rd0 是 zero register
- **GPRB**（rb0–rb63）：rb0 是 PC，哪些是 caller-saved，哪些是 callee-saved（栈指针 SP = 哪个 rb？）
- **RA（RegRAS）**：call 指令自动 push，ret 自动 pop；不属于 caller/callee-saved 框架
- **RF**：M1 BasicCodeGen 不使用浮点，RF 全部标为 "M1 Excluded"

每条必须有精确 Wiki 章节引用（文件名 + 章节标题，不用行号）。

### §2 参数传递

M1 非变参函数参数规则（从 AEE §调用约定 提取）：

- 第 N 个整数/指针参数放入哪个寄存器（RD 或 RB 序列）
- 超出寄存器数量时栈上布局（如果 AEE 有规定）
- i64 / i32 / i16 / i8 的传递规则（sign/zero extend？）
- 指针参数用 RB 还是 RD？

如 AEE 未明确某点，标 `[OPEN: 描述]`，不猜测。

### §3 返回值

- 标量整数返回寄存器（rd 序列中的哪个）
- 指针返回寄存器（rb 序列中的哪个）
- i64 / i32 / 指针 的扩展规则
- 多返回值（如 AEE 有规定；否则标 OPEN）

### §4 栈帧布局

从 AEE 或推论得到：

- 栈指针寄存器编号（RB 中的哪个）
- 帧指针（是否使用？寄存器号？）
- 调用前栈对齐要求（8 字节？16 字节？）
- 局部变量区、溢出区、callee-saved 区在帧内的相对位置

如 AEE 未明确，标 `[OPEN]`。

### §5 Call Sequence

描述 DADAO `call` / `ret` 与 RegRAS 的关系：

- `call` 指令效果：push return address 到 ra63，PC = target
- `ret` 指令效果：pop ra63 → PC
- Callee prologue 必须做什么（保存 callee-saved RD/RB）
- Callee epilogue 必须做什么（恢复 callee-saved，ret）

### §6 Open Issues

列出 AEE 未明确、影响 BasicCodeGen 但非阻断项：

- varargs（Excluded from M1）
- 浮点参数（Excluded from M1）
- 复杂聚合（Excluded from M1）
- 多返回值混合 bank（`docs/open-spec-issues.md` 记录）

---

## 约束

1. **每条规则有精确 Wiki 引用**（文件名 + 章节标题）；无 wiki 来源的推论必须标 `[OPEN]`
2. **不引用旧仓库**（llvm-unicore、DADAO）
3. **不与 ISA contract 重复**：指令语义（call/ret 的编码）不在此文件定义，引用 `contracts/isa/spec.md §5`
4. **M1 Excluded 项必须明确标出**：varargs/HFA/HPA 写明 Excluded，不留空白
5. 完成后**不自行 commit**，等待 Claude review
6. 文件版本 0.1.0，Status: Candidate（不自行升级为 Accepted）

---

## 参考

- `~/DADAO-wiki/DADAO-11-AEE-应用程序运行环境.md` — 主要来源（AEE §寄存器约定、§调用约定）
- `contracts/isa/spec.md` §1（寄存器模型）、§5（call/ret/RegRAS）— ISA 层基础
- `docs/open-spec-issues.md` — varargs、multiple returns 等已知 OPEN 项
- `code-agent/designs/0001-foundation-scope.md` §BasicCodeGen — M1 scope 边界
- `code-agent/designs/0002-detailed-roadmap.md` §Scope Matrix — 包含/排除范围
