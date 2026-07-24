# ML-033a：实现 DADAO 动态栈分配与恢复，关闭 VLA/alloca CodeGen 崩溃簇

**执行环境**：本地 subagent

**状态**：排队（ML-032a 收口后执行）

## 背景

ML-031a 后的 fresh gcc-c-torture 全量基线为
`PASS=1429 / FAIL_COMPILE=113 / FAIL_LINK=131 / FAIL_RUN=35`。其中 9 个
`FAIL_COMPILE` 不是 Clang 前端不支持，而是 DADAO 后端缺失动态栈节点：

- `DYNAMIC_STACKALLOC`：
  `20040811-1.c`、`20070824-1.c`、`920929-1.c`、`frame-address.c`、
  `pr36321.c`、`pr86528.c`
- `STACKRESTORE`/动态区生命周期：
  `920721-2.c`、`pr43220.c`、`vla-dealloc-1.c`

同一缺口还阻塞 musl 的 7 个对象：
`process/execl.c`、`process/execle.c`、`process/execlp.c`、`process/execvp.c`、
`unistd/getcwd.c`、`network/res_msend.c`、`locale/dcngettext.c`，已由
`docs/issues.yaml` 的 `musl-backend-dynamic-stackalloc-unimplemented` 记录。

## 目标

在当前 LLVM HEAD 上实现符合 DADAO ABI 的动态栈分配、`stacksave` 和
`stackrestore` lowering：

- SP 使用保留寄存器 `rb1`，栈向低地址增长；
- 动态大小按 ABI 至少 8 字节对齐；
- `stacksave` 返回调整前的真实 SP 指针；
- `stackrestore` 恢复保存值，不把动态调整错误折进固定 frame size；
- 固定 frame、callee-saved、动态区、调用序列和 epilogue 组合时仍正确；
- 大动态 size 不得依赖 imms12，使用合法的 RD/RB 物化与桥接路径；
- 不把真实 SP 调整误当成 `ADJCALLSTACKDOWN/UP` 的可消除 pseudo。

## 硬约束

- 先读 `contracts/abi/spec.md` §4、现有 `DADAOFrameLowering`/
  `DADAORegisterInfo`/`DADAOISelLowering` 和
  `musl-backend-dynamic-stackalloc-unimplemented` issue，不凭其它 target
  直接猜 DADAO 寄存器语义。
- 禁止用 `-O0`、固定 VLA 大小、改 testcase、禁用优化或为 9 个文件加特殊 flags
  绕过。
- 不顺带给外部 `alloca()` C 函数提供 libc stub；当前 6 个
  `missing_symbol:alloca` 是独立链接/API 问题，不作为本任务通过数。
- 正常普通 commit 落到 `.work/llvm`，立即导出一个或多个 patch，追加
  `components/llvm/patches/series`；禁止 rebase/reset/am 历史。
- 不启动 nested subagent，不提交根仓库。

## 判别性测试

新增 target in-tree CodeGen 测试和项目 E2E，至少覆盖：

1. 运行时 size（含非 8 字节倍数）分配、写入、读回；
2. 两次嵌套/顺序动态分配互不覆盖；
3. `stacksave` → 动态分配 → `stackrestore` → 再分配，确认地址和旧数据边界；
4. 固定局部变量与 VLA 同函数；
5. VLA 函数内部再调用普通函数，返回后数据正确；
6. size 足以触发非 imms12 调整；
7. O0/O2，QEMU 与 gem5 同一 ELF/语义双后端通过；
8. negative control 确认测试确实读回目标内存而非被优化折叠。

## 验收

- 上述 9 个 torture 文件由 `FAIL_COMPILE` 推进到可编译；逐项报告最终
  `PASS/FAIL_LINK/FAIL_RUN`，不强行要求无关缺陷也全消失。
- fresh musl 重建后，上述 7 个对象不再因
  `DYNAMIC_STACKALLOC/STACKRESTORE` 失败；报告对象级状态及 musl 总体变化。
- 全量 gcc-c-torture 1708 项重扫，和 `1429/113/131/35` 逐文件对账；
  允许目标项正向变化，禁止任何既有 PASS 回归。
- 全量 `llvm-lit -v tests/lit/E2E/`、DADAO CodeGen lit、
  `tools/run_differential.py`、manifest/issues checks 通过。
- 清理/归档对应 issue 时保留历史和精确 resolved commit/patch；若仅部分关闭，
  更新原 issue 的现状，不得直接删除。
- 填写任务完成区，并接受独立 subagent review，review 特别检查 SP 恢复、
  对齐、固定 frame 交互、大 size 和测试判别力。

## 非目标

- 不实现 Clang 不支持的 VLA-in-struct GCC 扩展。
- 不处理向量 legalize、BlockAddress、`__int128` 返回分配或外部
  `alloca()` libc symbol。
- 不修改 QEMU/gem5 来配合错误 lowering。

## 完成区

待执行。
