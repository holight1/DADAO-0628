# IN-006b 独立审查：LLVM patch series 格式审计与完整重放修复

日期：2026-07-23  
角色：独立 reviewer  
判决：**Accepted**

## 1. 审查结论

IN-006b 的修复满足验收条件：

- `0006`～`0048` 共 43 个 patch 的 unified-diff hunk 声明计数与正文一致，
  mbox/diff parser 全部接受；
- 从 manifest 裸 pin
  `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` 顺序执行 plain
  `git am`，48/48 成功；
- 最终重放 tree 为
  `f4adf7c77a6d5287442993d89d94cbb17eeb3136`，与目标提交
  `4b812d2f99305a259a3d37a827d67c6c1ae14546` 的 tree 完全一致；
- 四个修复 patch 均可由历史 blob/tree 或受控的 series 中间 tree 解释，
  未发现夹带当前目标 tree 之外的功能；
- manifest 通过，`.work/llvm` HEAD 正确且工作树 clean。

无 blocking finding。

## 2. 独立静态格式校验

reviewer 未复用 worker 的临时目录或结论，重新逐 hunk 解析
`0006`～`0048`：

```text
STATIC_HUNK_COUNT patches=43 failures=0
GIT_APPLY_PARSE patches=43 failures=0
```

第一项逐个比较 hunk header 的 old/new 行数与实际可消费的 context、
deletion、addition 行；第二项独立调用 `git apply --numstat` 检查完整
mbox/diff 解析。

四个修复 patch 的 `git diff --check` 通过。

## 3. 独立裸 pin 重放

在新建的临时 shared clone 中 detached checkout 到 manifest pin，逐条执行：

```text
git am <series 中对应 patch>
```

没有使用 `--3way`、`--reject`、skip、重排或其它放宽手段。

```text
APPLIED=48
FINAL_TREE=f4adf7c77a6d5287442993d89d94cbb17eeb3136
TARGET_TREE=f4adf7c77a6d5287442993d89d94cbb17eeb3136
git diff --exit-code replay_HEAD 4b812d2f...: rc=0
```

## 4. 四个修复 patch 的历史核对

### 4.1 `0006-dadao-disassembler.patch`

该 patch 的 `From` 为全零，历史中没有可供整棵 tree 一一对应的独立提交；
应用后是 series 特有的中间 tree：

```text
46928a3790fe04c6339e2131839095a0a3415f6f
```

因此不能把它表述为“应用后 tree 等于某个真实历史 commit”。独立 blob 核对
结果为：

- `Disassembler/CMakeLists.txt`：
  `8bb9b25edd23ea60dc512bfb2fc8029a7d72de92`；
- `Disassembler/DADAODisassembler.cpp`：
  `3220fd99d201cab87d64c4fa9d3b503a5efd165a`；
- 上述两个新文件均与其在历史提交
  `bb5415abcd13577585e3aec0437ad42be60aa9bc` 中落地的 blob 完全一致；
- DADAO CMake postimage 为 patch `index` 指定的
  `728f8ffb5fcb9b8a8beb90911b18c5dff28e1f1b`；
- InstrFormats/InstrInfo 的 decoder 变更在后续历史目标中存在，并在
  `0013` 处重新汇合到完整历史 tree。

这证明本次修复恢复的是被截断的 postimage 和 hunk，而非新增无来源语义。

### 4.2 `0007-dadao-control-flow.patch`

应用后 series tree：

```text
de8c291a74eafec5324de625af93d010cad8f414
```

它与真实历史提交 `e99cb0d2f275434f780858300b974f9b281d163c`
的整棵 tree 不同，差异仅为 `0006` 已提前引入的四个 Disassembler/CMake/
InstrFormats 路径。排除这些有来源的提前引入项后，`0007` 的历史输出一致；
尤其修复的 `DADAOInstrInfo.td` postimage 在两边均为：

```text
6ea5e385cb0abf4afc7b08e07a896fdce649b93c
```

这属于适配 series 实际前像，不改变 `0007` 的历史目标语义。

### 4.3 `0013-dadao-globals-lowering.patch`

应用后 tree：

```text
6ea8b53cdb0bd15c995231458cd6fdc6d90d50d5
```

与真实历史提交 `bb5415abcd13577585e3aec0437ad42be60aa9bc`
的 tree 完全一致。此前由 `0006` 提前引入的 Disassembler 内容在此处正确
收敛，没有重复创建或遗漏。

### 4.4 `0019-dadao-select.patch`

reviewer 另建临时 checkout，先应用修复后的 `0001`～`0018`，再应用主仓
HEAD 中的旧版 `0019`。旧版虽然能被 `git am` 接受，但结果为：

```text
old 0019 tree: a3f74cef80d76d4923df1cdb742a4d4d32bc2244
target tree:   76479e5a5f384661d5c4c4c13728209c4cdb0a28
```

两者只差 `DADAOInstrInfo.td` 的 9 行 plain-select pattern。该 pattern
逐字节来自目标提交的父提交
`e902b104c97704c86e681761a2871ea2382c54da`；目标提交
`b4f88e5f98ad390b3eb6e5971c876df4f7ad437f` 自身再增加
`DADAOISelLowering.h` 中的 `SEL` enum node。

修复后的 `0019` 合并了被 series 漏掉的父提交 postimage，应用后 tree
精确等于 `b4f88e5...`：

```text
76479e5a5f384661d5c4c4c13728209c4cdb0a28
```

因此补回内容是达到声明历史目标所必需的前置变更，不是夹带的新功能。

## 5. 其它门禁

```text
python3 scripts/manifest_check.py: PASS
.work/llvm HEAD: 4b812d2f99305a259a3d37a827d67c6c1ae14546
.work/llvm tree: f4adf7c77a6d5287442993d89d94cbb17eeb3136
.work/llvm status --short: empty
```

## 6. Findings

### Blocking

无。

### Non-blocking

1. `0006`、`0007` 因历史改动被 series 提前拆分，应用后的整棵中间 tree
   没有一一对应的历史 commit。后续记录应继续使用“blob identity + 受控
   额外路径 + `0013` tree convergence”的准确表述。
2. plain `git am` 在未由本任务修改的 `0024` 和 `0030` 各报告一处既有
   trailing-whitespace warning；不影响 48/48 重放或最终 tree identity，
   不属于本次 replay 修复的阻塞项。
3. `docs/issues.yaml` 中原 issue 的标题仍写“38 条”，状态仍为 open；
   当前 series 已为 48 条。这是验收后的记录同步事项。

## 7. 原 replay issue 判断

`llvm-patch-series-full-replay-corrupt-at-0005` 的技术阻塞已经解除，可以关闭。
关闭时建议：

- 将状态改为 resolved/closed；
- `resolved_by` 同时指向 IN-006a 与 IN-006b；
- 把“38 条”更新为当前的“48 条”，记录 0005 后又发现并修复
  0006、0007、0013、0019；
- 保留本报告中的 48/48 裸 pin 重放与最终 tree identity 作为关闭证据。

