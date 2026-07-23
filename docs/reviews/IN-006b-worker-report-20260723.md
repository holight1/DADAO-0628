# IN-006b worker report：LLVM patch series 格式审计与完整重放修复

日期：2026-07-23  
角色：worker（非独立 reviewer）

## 1. Worker 判决

**PASS；等待独立 reviewer。**

LLVM series 已从 manifest 裸 pin 使用 plain `git am` 顺序重放 48/48，最终
源码 tree 与 `.work/llvm` 的目标提交 `4b812d2f...` 完全一致。本轮没有修改
当前 LLVM 源码，只修复 patch 序列化、前像适配和缺失 postimage。

原 issue `llvm-patch-series-full-replay-corrupt-at-0005` 在独立 reviewer 验收前
仍应保持开放。

## 2. 静态扫描

扫描范围为 `components/llvm/patches/0006-*.patch` 至 `0048-*.patch`，同时
执行两类检查：

1. 逐 hunk 解析声明的 old/new 行数并与正文实际行数比较；
2. 对每个 patch 执行 `git apply --numstat`，检查 mbox/diff parser 完整性。

初始扫描只有 0006 存在 hunk 计数损坏；其五个 hunk 全部异常：

| 原 hunk | 声明 old/new | 正文 old/new | 结论 |
|---|---:|---:|---|
| Disassembler CMake 新文件 | 0/12 | 0/10 | 新文件正文为 10 行 |
| DADAODisassembler.cpp 新文件 | 0/127 | 0/106 | 新文件正文为 106 行 |
| DADAO CMake | 6/7 | 5/6 | 计数与前像均不完整 |
| DADAOInstrFormats.td | 6/7 | 5/6 | 上下文计数错误 |
| DADAOInstrInfo.td | 7/15 | 10/16 | 混入不存在于声明 old blob 的上下文 |

修复后对 0006～0048 重扫：

```text
STATIC_HUNK_COUNT_AUDIT=PASS patches=43 range=0006..0048
STATIC_PARSE_AUDIT=PASS patches=43 range=0006..0048
```

顺序重放进一步找出三个静态 parser 无法发现的前像/postimage 问题：0007、
0013 和 0019。

## 3. 修复证据

### 3.1 0006-dadao-disassembler.patch

0006 首行没有历史 commit SHA，新文件也没有 postimage hash，因此没有仅靠修改
hunk count 宣称恢复。证据链如下：

- `DADAO/CMakeLists.txt` 的 old blob 是 `08db6fd37cd6...`，patch 原声明的
  postimage 是 `728f8ffb5fcb...`。权威 blob diff 证明除添加
  Disassembler tablegen/subdirectory 外，还必须把 MCCodeEmitter 行移动到
  AsmWriter 之后；原 patch 正文漏了这组前像/后像。
- 两个新文件恢复后的 blob 分别是：
  - `8bb9b25edd23...`（CMakeLists.txt）
  - `3220fd99d201...`（DADAODisassembler.cpp）
- 这两个 blob 与它们在历史 `bb5415abcd13577585e3aec0437ad42be60aa9bc`
  中首次落地的 blob 完全一致。
- InstrFormats/InstrInfo 的 decoder changes 与后续历史 `e99cb0d...`、
  `bb5415a...` 的对应 postimage 内容一致。

应用后的 0006 tree 为：

```text
46928a3790fe04c6339e2131839095a0a3415f6f
```

这是 series 特有的中间 tree；历史主线当时没有把 0006 独立提交，不能伪称它
对应某个不存在的历史 commit。

### 3.2 0007-dadao-control-flow.patch

历史 0007 的 `DADAOInstrInfo.td` diff 从 `db600d7...` 再次引入 decoder
methods；series 中 0006 已先引入相同内容，实际 preimage 是 `974043071d07...`。

本轮只把该文件 diff 适配为：

```text
974043071d07... -> 6ea5e385cb0a...
```

输出 blob `6ea5e385...` 与历史提交
`e99cb0d2f275434f780858300b974f9b281d163c` 完全一致；其它 0007 语义未改。

### 3.3 0013-dadao-globals-lowering.patch

历史在 `bb5415a...` 才首次把 Disassembler 文件纳入提交，所以原 0013 会在
series 已执行 0006 后：

- 重复创建两个已存在文件；
- 对 CMake 与 InstrFormats 使用不再成立的前像。

因此按以下两端 tree 机械重建 0013 diff：

```text
series 0012 后 tree: 510b612f9fe9113f92dbca62b632c34e503bdc00
历史 0013 目标 tree: 6ea8b53cdb0bd15c995231458cd6fdc6d90d50d5
权威历史 commit: bb5415abcd13577585e3aec0437ad42be60aa9bc
```

重放后的 tree 为 `6ea8b53...`，与历史目标逐字节一致。此处 series 重新汇合
历史主线。

### 3.4 0019-dadao-select.patch

原 0019 mbox 格式正确、也能 plain `git am`，但应用后的 tree 是
`a3f74cef...`，而首行声明的历史提交 `b4f88e5...` 的 tree 是
`76479e5a...`。检查历史发现 `b4f88e5...` 的父提交
`e902b104c97704c86e681761a2871ea2382c54da` 没有独立 series patch；原 0019
只带了第二段 select pattern，漏了 SEL node。

本轮按正确的 0018 tree 到权威历史目标 tree 重建：

```text
0018 tree: 129bb7003b276da9f96bdc46200363301896dbad
0019 target tree: 76479e5a5f384661d5c4c4c13728209c4cdb0a28
authority: b4f88e5f98ad390b3eb6e5971c876df4f7ad437f
```

修复后的 0019 同时携带 `DADAOISelLowering.h` 的 SEL node 和
`DADAOInstrInfo.td` 的 select pattern，输出精确命中历史 tree。

## 4. 最终裸 pin 重放

使用独立临时 checkout：

```text
/tmp/in-006b-final-replay-20260723-6iEUNI/llvm
```

来源是只读共享 `.work/llvm` object store 的独立 clone；checkout 到 manifest
pin 后按 `components/llvm/patches/series` 逐条执行 plain `git am`。没有使用
`--3way`、`--reject`、skip 或其它放宽条件。

```text
pin: ca7933e47d3a3451d81e72ac174dcb5aa28b59d1
0001..0048: PASS (48/48)
final replay tree: f4adf7c77a6d5287442993d89d94cbb17eeb3136
expected target tree: f4adf7c77a6d5287442993d89d94cbb17eeb3136
git diff --exit-code replay_HEAD 4b812d2f...: rc=0
```

从 0013 重新汇合历史后，0014～0018 每一步都命中对应历史 commit tree；修复
0019 后，0019～0048 每一步也都命中对应历史 commit tree。

## 5. 其它门禁与边界

```text
python3 scripts/manifest_check.py
  manifest validation: PASS

git diff --check -- repaired patches
  PASS

git -C .work/llvm rev-parse HEAD
  4b812d2f99305a259a3d37a827d67c6c1ae14546

git -C .work/llvm status --short
  empty
```

本 worker 修改：

- `components/llvm/patches/0006-dadao-disassembler.patch`
- `components/llvm/patches/0007-dadao-control-flow.patch`
- `components/llvm/patches/0013-dadao-globals-lowering.patch`
- `components/llvm/patches/0019-dadao-select.patch`
- `code-agent/tasks/IN-006b-llvm-patch-series-format-audit.md` 完成区
- 新增本报告

未修改 0001～0005、series、manifest、`.work/llvm`、测试、issues、roadmap、wiki
或其它 component；主仓未提交。主仓中并发的 IN-007a/QEMU 改动不属于本任务，
未读取、改写或纳入验证。

## 6. 独立 reviewer 重点

1. 从 manifest pin 独立 plain `git am` 48/48，并比较最终 tree
   `f4adf7c77a6d...`。
2. 复核 0006 的 CMake `08db6fd... -> 728f8ff...` blob 证据与两个新文件
   在 `bb5415a...` 的 blob identity。
3. 复核 0007 的 `974043... -> 6ea5e385...` 前像适配。
4. 复核 0013 应用后重新命中 `bb5415a...` tree。
5. 复核 0019 原 tree 偏差以及缺失 `e902b104...` SEL node 的恢复。
6. reviewer 通过前保持原 issue 开放。
