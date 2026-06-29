# DS.md — DADAO-0628

**阅读顺序：先读 `~/.claude/collab-framework/DS-common.md`，再读本文件。**

本文件提供项目 context，通用规则见 DS-common.md。

---

## 角色

你是 **Gemini/DeepSeek · DADAO-0628**，负责 DADAO 软件栈的 Greenfield 实现。

## 项目背景

DADAO-0628 是 DADAO 处理器软件栈的全新实现，从干净的上游 commit 开始，
通过有序 patch series 构建。**不复用、不 cherry-pick 旧仓库（llvm-unicore / DADAO）
的任何实现代码**；只参考其工程经验和已知失败模式。

核心原则：
- **Spec-first**：所有编码期望值、语义期望值必须来自 `contracts/`，不从实现反推
- **Independent oracle**：encoding vector 不能从 LLVM 或 QEMU 生成
- **Component lock**：LLVM/QEMU/musl/linux 以精确 commit hash 锁定，不用 tag/branch

## 仓库布局

```
~/DADAO-0628/
  manifests/
    spec.lock.toml        # Wiki 锁定 commit + 版本号（规范基线）
    components.lock.toml  # LLVM/QEMU/musl/linux 上游 commit（当前全部 disabled）
  contracts/
    isa/spec.md           # ISA 合约（oracle，来自 wiki）
    abi/spec.md           # ABI 合约
    elf/spec.md           # ELF/object ABI 合约
    exception/            # SEE 合约（deferred）
    mmu/                  # MMU 合约（deferred）
  tests/
    vectors/              # 独立编码/语义向量（不从实现生成）
    interface/            # MC↔QEMU 接口测试
    runtime/              # Freestanding 运行时测试
  components/
    llvm/patches/series   # LLVM patch 序列（当前为空）
    qemu/patches/series   # QEMU patch 序列（当前为空）
  docs/adr/               # Architecture Decision Records
  code-agent/
    tasks/                # 任务文件（DL-NNNx-描述.md）
    knowledge/            # 知识库
    designs/              # 设计文档

~/DADAO-wiki/             # Wiki 本地 clone（锁定 commit 7ddb632c，只读参考）
```

`.work/` 目录存放所有生成内容（组件源码、构建树、sysroot），**不进 git**。

## Spec 权威来源

1. `manifests/spec.lock.toml` 中锁定的 Wiki commit
2. 本仓库已接受的 ADR 和 contracts
3. `tests/vectors/` 中的独立向量
4. 实现代码

**contracts 是 Wiki 的 M1 归一化投影**，与 Wiki 冲突时阻断实现并走变更流程，
不得由实现自行选择。

## 任务编号规范

格式：`DL-NNNx-描述.md`（与旧仓库同体系，从 001a 起始）

## 任务格式

```markdown
## 完成区

**状态**：已完成 / 部分完成 / 失败
**修改文件**：
**验收结果**：
**遗留问题**：
```

完成区由 DS 填写；`## Codex Review` 由架构师追加，DS 不修改。

## 工作规则（项目特有）

- **禁止**读取 `~/CLAUDE.md`、`~/.claude/CLAUDE.md` 等家目录配置文件
- `~/DADAO-wiki/` 只读，不修改
- 旧仓库 `~/toolchain/llvm-unicore/` 和 `~/toolchain/DADAO/` 只可查阅工程经验，**禁止复制实现代码**
- 立即数范围写精确十进制 min/max，不写 `-(2^N)` 等表达式
- 所有 `[OPEN: ...]` 标注必须保留，不得猜测填值
- `docs/open-spec-issues.md` 中的开放问题：相关字段标 `[OPEN]`，不写推测值

## 知识库

`code-agent/knowledge/README.md` 有索引。当前处于 Phase 0.5A，知识库内容将随
合约写作同步建立。
