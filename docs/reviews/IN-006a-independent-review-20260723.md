# IN-006a 独立审查：LLVM patch series 裸 pin 重放修复

日期：2026-07-23
角色：独立 reviewer

## 判决

**Accepted-partial**

0005 的修复可以接受：独立从裸 pin 使用 plain `git am` 重放 0001～0005
成功，所得完整源码 tree 与历史提交 `79e6b7958a670ba72a76df1ef55a5e868bc33ab6`
逐字节一致；`DADAO.td` 的 preimage 适配没有夹带目标 tree 之外的语义改动。

但 IN-006a 的全量目标没有完成：0006 自身仍是 malformed patch，48/48
重放及最终 tree 与 `4b812d2f...` 的比较均未发生。因此：

- IN-006a 只能接受为“0005 子问题已修复”，不能标记整体完成；
- `llvm-patch-series-full-replay-corrupt-at-0005` 原 issue 不能关闭；
- 应继续修复 0006，并扫描、重放余下 series，直到满足原任务全部验收项。

## 独立复验环境

审查在新建临时 clone
`/tmp/in-006a-independent-review-1MhAFQ/llvm` 中进行。clone 使用独立
worktree、index 和 refs，只读共享 `.work/llvm` object store；项目内
`.work/llvm` 未被 checkout、修改或提交。

裸 pin：

```text
ca7933e47d3a3451d81e72ac174dcb5aa28b59d1
```

按 `components/llvm/patches/series` 顺序逐条执行 plain `git am`：

```text
Applying: DADAO triple registration
Applying: DADAO target skeleton
Applying: DADAO register info
Applying: DADAO instruction info
Applying: DADAO AsmParser, MCCodeEmitter, MCInstPrinter
```

结果为 0001～0005 全部成功，临时仓干净。

## 0005 目标 tree 核对

重放后：

```text
replay HEAD: 21f7343731138d13448deff22bd8d9ba9deb5bd0
replay tree: 9c62c5421eb1e9fc716b528e5304ce35d2166c9e
79e6 tree:   9c62c5421eb1e9fc716b528e5304ce35d2166c9e
git diff --exit-code HEAD 79e6b795...: rc=0
```

commit ID 不同来自邮件/提交元数据；tree ID 和空 diff 证明源码内容一致。

修复前的 0005 无法解析，因而不存在可直接执行得到的“修复前 tree”。独立
审查以原补丁内已有的十个 postimage blob ID 作为其语义目标，并逐个与
`79e6b795...` 对应路径核对。十个 blob 全部匹配：

```text
ee6011d15cda  AsmParser/CMakeLists.txt
74540f99fd3c  AsmParser/DADAOAsmParser.cpp
08db6fd37cd6  DADAO/CMakeLists.txt
86f36095cdb9  DADAO/DADAO.td
7d73a99b2c75  MCTargetDesc/CMakeLists.txt
b64a1b737afc  MCTargetDesc/DADAOInstPrinter.cpp
c0f1a3e8cfc4  MCTargetDesc/DADAOInstPrinter.h
8c62185573ba  MCTargetDesc/DADAOMCCodeEmitter.cpp
0ffe732e9426  MCTargetDesc/DADAOMCTargetDesc.cpp
cc7e3a73ff4e  MCTargetDesc/DADAOMCTargetDesc.h
```

当前修复后的 0005 仍声明完全相同的十个 postimage blob ID。结合重放后的
完整 tree 相等，可以确认恢复缺失的 CMake、InstPrinter 和 MCCodeEmitter
行是在恢复原补丁已经声明的目标内容，不是新增另一套实现。

## `DADAO.td` preimage 适配专项审查

当前 0001～0004 重放后的 `DADAO.td` blob 为：

```text
cb11ed847f3a911da287d8ad36ba7491a3074ec2
```

历史 `79e6b795^` 的对应 preimage blob 为：

```text
0bbe4f8174d27c1f4d3aebc875ea35befd372e45
```

两者完整 diff 只有两处：

- 当前 series preimage 多一行 `include "DADAOInstrInfo.td"`；
- 当前 series preimage 缺少 `def DADAO : Target` 的文件末尾 `}`。

修复后的 0005 在加入原目标
`defm : RemapAllTargetPseudoPointerOperands<GPRD>;` 的同时，删除上述多余
include 并补回闭合括号。所得 blob 为：

```text
86f36095cdb98581c62004644d38abfe45d33ac2
```

它同时等于：

- 原 malformed 0005 已声明的 `DADAO.td` postimage；
- 当前修复后 0005 已声明的 postimage；
- 历史 `79e6b795` 的实际 `DADAO.td` blob。

因此这两行变化是让当前 series 的不同 preimage 收敛到既定 postimage 所必需
的适配，不构成借格式修复夹带语义变化。补丁统计从 `+528/-10` 变为
`+529/-11` 是 preimage 不同造成的计数变化，不能据此判为目标语义增加。

## 0006 独立阻塞复现

在已经得到 0005 正确目标 tree 的临时仓继续执行：

```text
git am components/llvm/patches/0006-dadao-disassembler.patch
Applying: DADAO Disassembler
error: corrupt patch at line 27
rc=128
```

随后又在 `/tmp`、不依赖任何 Git 仓库和源码 preimage 的条件下执行
`git apply --numstat`，同样在解析 0006 时返回 `corrupt patch`、`rc=128`。
0006 第一段新文件 hunk 声明 `@@ -0,0 +1,12 @@`，但到下一条
`diff --git` 前实际只有十条 `+` 行。纯语法解析已经失败，尚未进入上下文
匹配，所以该失败独立于 0005 的内容和目标 tree。

## 其它检查

```text
python3 scripts/manifest_check.py
manifest validation: PASS

git -C .work/llvm status --short
<empty>
```

审查未修改任务、patch、series、issues、roadmap、wiki、测试或 component
源码，也未提交；只新增本独立审查报告。
