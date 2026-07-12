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

完成区由 DS 填写。

## 自审流程（subagent · 强制）

**只要任务有任何代码改动，DS 在返回架构师之前，无论以何种原因返回（已完成 / 部分完成 / 失败 / 卡住 / 撞墙），都必须先自己开一个 subagent 做 review。** 「没做完」不是跳过 review 的理由——恰恰相反，卡住的任务更需要 review 来判断卡点是否真的无解。

> **硬门槛（机械强制）**：任务 md 里的 **`## 审阅记录（subagent）` 区是必填交付物**——架构师建任务时已预置占位。**返回时该区若仍是占位/为空 = 没做 subagent 自审 = 架构师直接打回，即使代码正确、测试全过、任务顺利也一样。** 任务"顺利"绝不豁免自审（DL-062b 数据点：代码工作但 DS 跳自审→打回）。subagent 判决为「通过」也**必须留下判决行 + 逐条核验**，不能只删占位。

步骤：

0. **返回前自检**：准备以任何形式交回架构师（哪怕只写了"部分完成/卡在 X"）→ 先走完下面 1-5，**不得直接返回**。
1. DS 实现（或实现到卡点）→ 填 `## 完成区`（贴**真实**构建/运行输出，禁伪造/估算；未完成如实写状态=部分完成/失败 + 卡点）。
2. **DS 开一个 subagent 做「代码级 review」**：subagent 先读 `reviewer.md`，然后**逐行读本任务的 diff / 改动源码**，审：
   - **逻辑正确性**——不只被测样本，推敲**未测输入 / 边界 / 其它情形**会不会错；
   - **设计 / 惯用法**——是否脆弱、非标准、埋雷（典型：「简单样本能过、换个情形就错」的实现），是否偏离任务设计；
   - **防造假底线**——顺带确认**真 build 过 + 完成区输出非伪造**（构建/运行一次即可，重点是读代码，不是复跑覆盖）。
3. subagent 把 **review 意见（含未测输入 / 脆弱性隐患）+ 发现的问题 + 判决** 写进任务 md 的 **`## 审阅记录（subagent）`** 区。
4. DS 据 review **修复**，并**逐条把处置写进「## 审阅记录（subagent）」区**——**这一步强制、不可省**（DS 常漏此步：subagent 记了问题、DS 改了却不写回，架构师无从判断哪些改了）。对 subagent 的**每一条 finding**，追加一行处置：
   | finding | 处置 | 改了什么 | 复验证据 |
   |---|---|---|---|
   | 例：exts i8 立即数错 | ✅已修 8→56 | .td L351 | QEMU sext(i8 -128)=负 ✓ |
   处置只能是 **✅已修**（附改动+复验）/ **⏸延后**（附新任务号 + 为何可延）/ **❌不修**（附为何是误报/不成立，要有证据）。**不允许 finding 无处置就返回。**
   - **review 若指出可推进的路（根因/下一步/绕法），DS 必须继续推进**，把能做的做完，别一 review 完就返回。反复「实现→自审→按 review 推进」直到真正无法再进（外部阻塞、需架构师定夺）或全部通过。**卡住 ≠ 立即返回**：先让 subagent 判断卡点是否真无解、有无 DS 能自行解决的路。
5. **完成区状态必须与 subagent 判决对账**：
   - subagent 判决 = 通过 / 所有 finding 均 ✅已修并复验 → 完成区可标「已完成」。
   - subagent 仍有未修 finding（延后/不修/未复验）→ 完成区**不得标「已完成」**，须标「部分完成」并在遗留列出，**不得写「遗留:无」**。**「subagent 说有问题、DS 却标已完成/遗留:无」是禁止的自相矛盾**——架构师看到即直接打回、不复跑（DL-062a 数据点）。
6. DS 返回架构师（此时交回的已是自审 + 逐条处置 + 尽力推进过的版本）。**架构师另做最终独立 ground-truth 复跑验收**（重 build + 重跑 + grep）后 commit——两道 review 互补：**subagent 读代码逻辑/设计，架构师跑行为真值**。

> 真正卡住 / 某条无法通过（已按 review 尽力推进仍无解）：如实在完成区 + 审阅记录写 `❌ + 根因 + 已尝试的推进`，别删前置改动去"解锁"、别糊"可行"、别跳过 subagent review 直接返回、别 finding 无处置就交、别状态与判决打架。

## 工作规则（项目特有）

- **CodeGen / E2E 任务的被测对象是编译器产物**：`.s` / `obj` / flat binary **必须来自 `llc`/编译流水**（IR/C → llc → .s → llvm-mc …）。**禁止手搓汇编替代**去过验收——那绕过了本该被测的 CodeGen（DS-common §5 反偷换的本项目实例）。真实产物跑不通就如实报卡在哪层。
- **禁止**读取 `~/CLAUDE.md`、`~/.claude/CLAUDE.md` 等家目录配置文件
- `~/DADAO-wiki/` 只读，不修改
- 旧仓库 `~/toolchain/llvm-unicore/` 和 `~/toolchain/DADAO/` 只可查阅工程经验，**禁止复制实现代码**
- 立即数范围写精确十进制 min/max，不写 `-(2^N)` 等表达式
- 所有 `[OPEN: ...]` 标注必须保留，不得猜测填值
- `docs/open-spec-issues.md` 中的开放问题：相关字段标 `[OPEN]`，不写推测值

## 知识库

`code-agent/knowledge/README.md` 有索引。当前处于 Phase 0.5A，知识库内容将随
合约写作同步建立。
