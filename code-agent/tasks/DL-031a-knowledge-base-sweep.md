# DL-031a: 知识库全面补全（任务历史扫描）

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行

---

## 背景

`code-agent/knowledge/` 目前只有一个文件（§1 QEMU translate 约定，commit 2b6f767）。  
已有 30 个完成任务（DL-001a 到 DL-030a），积累了大量可复用的技术结论，但尚未系统写入知识库。

---

## 目标

扫描所有已完成任务的完成区，提炼**可复用、非临时的技术结论**，写入 `code-agent/knowledge/` 下的章节文件。

---

## 输入

扫描以下任务文件的**完成区** + **Architecture Review 区**：

```
code-agent/tasks/DL-001a-isa-contract.md        # ISA 合约框架
code-agent/tasks/DL-001b-spec-revision.md       # spec v0.4.0 关键决策
code-agent/tasks/DL-001c-encoding-validator.md  # validate_encoding.py 设计
code-agent/tasks/DL-001d-vector-data.md         # 向量格式约定
code-agent/tasks/DL-002a-abi-contract.md        # ABI 关键约定
code-agent/tasks/DL-013a-qemu-skeleton.md       # CPUState / machine 结构
code-agent/tasks/DL-014a-qemu-decodetree.md     # insn.decode 格式规则
code-agent/tasks/DL-015a-qemu-rd-arith.md       # TCG gen_helper / tcg_add2 模式
code-agent/tasks/DL-016a-qemu-load-store.md     # MO_ALIGN flags，EXCP_MALIGN
code-agent/tasks/DL-018a-qemu-ctrl-flow.md      # RegRAS ra[63] 约定
code-agent/tasks/DL-019a-phase3-harness.md      # harness 架构（build_test_binary）
code-agent/tasks/DL-021a-harness-semantic.md    # XOR 比对引擎，CSZ guard
code-agent/tasks/DL-022b-harness-memory-check.md # expected_state.memory 协议
code-agent/tasks/DL-023a-issue-registry-trans-lint.md  # make check / CI gate
code-agent/tasks/DL-024a-qemu-trans-rela-fix.md       # trans_rela 修复根因
code-agent/tasks/DL-025a-qemu-ldmo-rb-impl.md         # ldmo 实现模式
code-agent/tasks/DL-026a-qemu-divs-divu-tcg-label-fix.md  # TCG label 顺序规则
code-agent/tasks/DL-027a-architect-direct-vector-fixes.md  # 向量编写约束（总结）
code-agent/tasks/DL-028a-control-flow-yaml-tdd.md       # 分支 encoding 修复思路
code-agent/tasks/DL-029a-control-flow-semantic-harness.md  # poison pattern（已在 §1）
```

---

## 知识提炼规则

**写入知识库的内容**：
- 确认的 ISA/ABI 行为（从 spec 推导 + QEMU 验证两路径均确认）
- 工具链实现中的非显然约定（"这里必须这样做，否则 X 原因会出错"）
- 测试框架的接口约定（binary layout、exit 协议、向量格式）
- 已 debug 的根因（值得记录的 bug 模式，避免重蹈）

**不写入知识库的内容**：
- 临时路径、commit hash、具体行号（代码在仓库里）
- 已归档/已解决的一次性问题（除非有通用教训）
- 重复现有 §1 内容（QEMU translate 约定已写）

---

## 章节规划（建议，DS 可按实际内容调整）

| 文件 | 内容 | 来源任务 |
|------|------|---------|
| `02-isa-encoding-rules.md` | DADAO 指令格式位域（rwii/rrii/rrrr/iiii/riii）、zero-reg 约束、rd0 禁止输入 | DL-001b/c/d, DL-027a |
| `03-test-vector-conventions.md` | 向量字段语义（class/status/expected_fault/branch_behavior）、5类向量定义、48-bit RB 约束、rd2rb/rb2rd 不对称 | DL-001d, DL-027a |
| `04-qemu-tcg-patterns.md` | TCG label 顺序规则、tcg_add2 模式、GEN_ILLEGAL_INSN、EXCP_* 常量、MO_ALIGN flags | DL-015a, DL-016a, DL-026a |
| `05-harness-binary-protocol.md` | build_test_binary 接口、emit_exit 协议、BINARY_BASE/ROM 地址、exit code 含义、FAULT_CODES、memory check 协议 | DL-019a, DL-021a, DL-022b |
| `06-machine-memory-map.md` | ROM 0x100000、RAM 0x80000000、exit MMIO、TLB identity map 范围、物理地址 0 未映射 | DL-013a, DL-019a |
| `07-abi-call-convention.md` | RegRAS 压栈方向（ra[i-1]←ra[i]，push 方向）、ra[63] 约定、rd/rb allocatable 分层 | DL-002a, DL-018a |

---

## 格式要求

每个文件遵循已有 §1 的格式：
- 顶部注明**来源**（任务编号 + commit）
- 每条结论独立小节（§N.M）
- 有代码示例时用 code block
- 有对比时用表格

---

## 约束

- 不修改任何源码或 yaml（纯文档任务）
- 不更新任务文件完成区
- 不重复 §1 的内容（可交叉引用：`参见 §1.1`）
- 写完后运行 `python3 scripts/validate_vectors.py tests/vectors/` 确认 yaml 未被误改（应 0 error）

---

## 验收

```bash
ls code-agent/knowledge/           # 应有 §01-§07（或 DS 实际划分的章节）
python3 scripts/validate_vectors.py tests/vectors/  # 0 error（yaml 未被改动）
```

---

## 完成区

（DS 填写）
