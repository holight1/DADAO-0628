# ML-014r：修正 direct brk probe 的失败编号映射

**执行环境**：本地 subagent worker；承接 ML-014q independent review

**状态**：Completed；等待独立 reviewer（2026-07-18）

## 目标

修正 ML-014q direct brk evidence probe 的诊断映射：独立 reviewer 已确认
六项 brk/backing 断言和成功路径真实，但 check 5 失败时当前分发会误报
`FAIL-6`。本任务只修正临时 probe 的失败消息选择并补跑 check 5 负向路径，
使每个失败编号可审计；不修改任何 gem5/QEMU/LLVM/musl 实现。

## Ownership

- worker 只负责 `.work/ML-014r-gem5-brk-evidence-fail-routing/` 下的 probe
  副本、编译产物、运行日志和本任务记录；不覆盖 ML-014q 原始产物。
- 不允许修改 `/home/holight/DADAO-gem5`、QEMU、LLVM、musl、root patch
  series、docs/issues、contracts、manifests 或用户原始 ML-014a。
- 不得把 `~/toolchain` 或 `~/knowledge-graph` 传给 subagent；架构师可自行
  参考，worker 不得依赖它们。
- 不处理 allocator、pointer ABI、`-O X`、puts、free、varargs 或 ML-014a。

## 执行阶梯

1. 复制 ML-014q probe 到本任务目录，修正 failure dispatch，使 FAIL-1 到
   FAIL-6 一一对应；确认 check 5 的故意错误变体输出 `FAIL-5`、exit 5，
   正常 probe 仍输出 PASS、exit 42。
2. 使用当前 gem5 `c7e92c7f80` 构建产物运行正常/负向 probe，保留命令、
   stdout/stderr/VMA 日志；不删除旧证据。
3. 完成本任务记录和自审，明确只修 probe 证据，不扩大到实现或 allocator；
   等待独立 reviewer。

## 验收

- 正常路径 `PASS/42`，check 5 负向路径 `FAIL-5/5`；失败映射代码可读且不
  依赖无条件 exit。
- 无实现源码或越权文件修改，ML-014q 的历史证据保持不动。
- 有 worker 自审和独立 reviewer 记录。

## 完成区

**Finding：Probe evidence routing fixed（仅限 direct `SYS_brk` 证据；不等同于实现、allocator、ML-014f 或 ML-014a 完成）**

### 修改与产物

- 将 ML-014q 的 `.work/ML-014q-gem5-brk-evidence-probe/brk_assert_probe.s`
  复制到本任务目录的 `brk_assert_probe.s`；ML-014q 原目录未覆盖、未修改。
- 修正 `fail` dispatch：不再使用检查阶段遗留的 `rd5` 作为第一次 selector，
  而是在每个 `breq` 前依次装载 1、2、3、4、5；未命中 1–5 时才进入
  `fail6_msg`。因此 `fail5` 设置的 `rd20/rd17=5` 会稳定选择
  `ML-014q FAIL-5`。
- 正常构建产物位于
  `.work/ML-014r-gem5-brk-evidence-fail-routing/normal/`；故意使 check 5
  失败的独立源文件和产物位于 `negative_check5/`。负向源仅将 check 5 的
  比较目标从 `rd4` 改为已知错误的 `rd2`，此前 check 1–4 保持不变。

### 构建与运行

使用 LLVM 工作构建的 `clang`、`ld.lld`、`llvm-objcopy`，以及当前 gem5
source `c7e92c7f80` 对应的构建产物
`/home/holight/DADAO-gem5/build/DADAO/gem5.opt`。两个运行均使用：

```text
--debug-flags=Vma,PageTableWalker,Faults
--debug-file=brk_assert_probe.debug.log
```

完整命令行、gem5 启动 stdout/stderr、`stats.txt`、`config.*`、VMA/debug 日志
和 exit code 均保存在：

```text
.work/ML-014r-gem5-brk-evidence-fail-routing/run_normal/
.work/ML-014r-gem5-brk-evidence-fail-routing/run_negative_check5/
```

结果摘要：

| 运行 | 断言源 | gem5 trap exit | probe stdout 关键结果 |
|---|---|---:|---|
| `run_normal` | 正常 `brk_assert_probe.s` | 42 | `ML-014q PASS` |
| `run_negative_check5` | check 5 故意错误变体 | 5 | `ML-014q FAIL-5` |

两份 debug 日志均保留了 heap VMA：
`[0x87e00000 - 0x87e01000]` 与
`[0x87e01000 - 0x87e02000]`；stderr 仅有既有 gem5 warning，没有 page-table
fault。负向路径在 check 5 失败后退出，未执行 check 6 marker 写读，这是预期
的 failure isolation。

### 自审

- 自审确认 dispatch 的 1–5 分支均有显式 selector 装载，check 5 不再依赖
  `rd5` 的历史值；6 仍是唯一兜底消息。
- 自审确认正常 ELF 和负向 ELF 的 SHA-256 分别为：
  `4638caefb01df7e74301e661436de21e7a643d0321f4af87bf5432549dc78591`、
  `de5085a67688e354afb2b1046f13e6e2e8da39d60332ab0f3b5abb5e94b00a8d`；
  运行输出与 exit code 分别真实为 PASS/42、FAIL-5/5。
- `/home/holight/DADAO-gem5` 在运行前后保持 clean，提交
  `c7e92c7f80` 未修改；root 工作树除用户原始 ML-014a 外仅有本任务记录。
- 本任务没有修改 gem5/QEMU/LLVM/musl、root patch series、docs/issues、
  contracts、manifests 或用户原始 `ML-014a`；没有使用或传递
  `~/toolchain`、`~/knowledge-graph`。
- 本任务没有处理 allocator、pointer ABI、`-O X`、puts、free、varargs，
  也没有重跑 QEMU、mallocng、全量 E2E、differential 或 `make check`；
  本任务结果不能关闭 ML-014f 或 ML-014a。

**自审结论：Confirmed（仅 direct brk evidence failure routing；等待独立 reviewer）。**

## 审阅记录

（待独立 reviewer 复核）
