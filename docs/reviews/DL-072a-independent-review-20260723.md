# DL-072a 独立审查（2026-07-23）

## 判决

**Accepted**

未发现阻断 DL-072a 合入的 correctness、测试真实性、patch 可重放性或文档
越界声称问题。具体的
`varargs-pointer-args-lost-rb-bank-save-area` 问题可以关闭；更广义的
`Varargs` issue 应继续保持 open，等待 wiki 的栈布局文字冲突以及 RF/aggregate
范围澄清。当前变更正是这样记录的。

## 审查范围与方法

本审查独立重读并交叉核对：

- `code-agent/tasks/DL-072a-varargs-caller-populated-save-area.md`
- `~/DADAO-wiki/DADAO-21-ABI-应用程序二进制接口.md:240-337`
- 主仓库未提交 diff
- LLVM 普通提交
  `3aa546d1d0cd516e04edc599e8c32a964acd96b2`
- `components/llvm/patches/0050-DADAO-implement-caller-populated-varargs-save-area.patch`
  及 50 项 `series`

本审查未修改实现、测试、task、issue、wiki 或任何其它文件；本文件是唯一写入。
未访问或参考 `~/toolchain`、`~/knowledge-graph`。

## Findings

无 blocking finding。

### 非阻断性规范风险：wiki 两段文字不能同时满足

wiki 第 259 行要求低地址到高地址为
“overflow → locals → varargs save area”，但第 316-320 行又规定 save-area
base 就是 incoming SP，`ap = sp + N*8`。当固定参数或未命名参数还需要普通
overflow 副本时，这两条缺少额外 base 元数据，无法同时成立。

实现选择可执行的 incoming-SP/`va_start` 语义：

- 固定参数 overflow 副本在 save area 之前；
- save area 按源参数顺序连续存放；
- 未命名 overflow 的普通副本移到 save area 之后；
- callee 用固定 overflow 大小加命名参数 slot 数定位首个未命名 slot。

这不是 pointer-loss issue 的残留：混合 RD/RB、固定 overflow、未命名
overflow、真实 `printf` 和真实 `scanf` 均已运行通过。文档也没有把该选择
冒充完整 ABI 闭合：`docs/issues.yaml` 中 broader `Varargs` 仍为 open，
`docs/open-spec-issues.md:11` 和 `contracts/abi/spec.md:318` 明确保留冲突及
RF/aggregate 限制。因此该规范风险不阻止关闭具体 pointer-loss issue。

## 独立静态审查结论

### Caller lowering 与源顺序

- `CLI.IsVarArg` 来自 LLVM call-site function type 的 `FTy->isVarArg()`；
  固定/未命名边界由 `CLI.NumFixedArgs` 设置的 `OutputArg::Flags.isVarArg()`
  表示。因此新增保存区只在真正 variadic call 生效。
- `LowerCall` 按 `ArgLocs`/`OutVals` 顺序单次遍历，每个 RD/RB 标量参数都在
  保留正常 register/overflow 传递的同时写入一个 8-byte slot。mixed O0
  汇编可见七个 slot 位于 `sp+0..48`，顺序对应
  `1, 2, &x, 4, 5, &y, 6`。
- 固定 overflow、save area、未命名 overflow 使用不相交区间。O0 overflow
  探针的实际汇编中，固定 `a16` 普通副本在 `sp+0`，19 个 save slots 在
  `sp+8..159`，最后一个未命名 int 的普通 overflow 副本在 `sp+160`；
  caller 的局部/保存对象从 `sp+168` 开始。
- `Outs.size()`/逐项 `i64` 断言明确把实现限制在一项一个 64-bit slot 的
  RD/RB 标量；没有声称 split aggregate 或 RF 已完成。

### Call-frame pseudo 与普通调用

- `ADJCALLSTACKDOWN/UP` 没有显式寄存器 def/use，标记
  `hasSideEffects=1` 能防止 PEI 计算 `MaxCallFrameSize` 前被通用 dead-MI
  删除；PEI 随后仍通过 `eliminateCallFramePseudoInstr` 删除 pseudo，不会
  生成重复 SP 调整。
- DADAO 的 `hasFPImpl()` 恒为 false，基类本来就把 call frame 视为 reserved；
  显式 `hasReservedCallFrame=true` 与既有策略一致。非 variadic call 的
  `NumBytes` 计算没有改变，只有原本丢失的 call-frame size 现在能被 PEI
  正确计入。
- 72 项全 E2E 零回归；上述 overflow 汇编还直接证明 outgoing
  `sp+0..167` 与 caller locals `sp+168+` 不重叠。

### Callee、`va_start` 与 `va_arg`

- `LowerFormalArguments` 中原 RD16-RD31 remaining-register spill 已完全删除。
  variadic callee 只建立指向 caller save area 的 fixed frame object。
- 无固定 overflow 时，save base 为 incoming SP，`va_start` 为
  `incoming SP + named_count*8`。有固定 overflow 时，按上面的已记录冲突，
  使用 `fixed_stack_size + named_count*8`；overflow 探针中 callee 实际
  计算得到 incoming SP + 144，正好指向第一个未命名 pointer slot。
- Clang 的 DADAO arch switch 明确选择新增 `DADAOTargetCodeGenInfo`，不是
  仅新增了未使用文件。`EmitVAArg` 使用 8-byte slot、每次前进 8，并在
  big-endian 下强制 right-adjust。定向 IR 测试锁定两次 `int` 读取均为
  `ap+8` 和 slot `+4`；pointer/i64 为完整 8-byte 读取，mixed、printf、
  scanf 运行测试进一步覆盖实际指针值。

### 测试真实性

- `varargs_mixed.test` 在 O0 和 O2 下均运行 QEMU+gem5；C 断言同时覆盖四个
  named 值及 `5, &y, 6` 三个未命名值，能捕获 RD/RB 乱序。
- `varargs_narrow.test` 运行双后端，验证 `0x11223344` 和负数 `-2`，不是
  只做 IR 文本检查。
- `varargs_overflow.test` 同时覆盖 17 个 named RD 参数后的固定 overflow，
  以及 17 个 unnamed RD 参数的 overflow，并混入 pointer。
- `musl_printf_ptrs.test` 真实链接当前 musl `crt1.o + libc.a`，两后端同时
  检查退出码 42 和精确顺序 `left right`。
- `musl_scanf_int.test` 已删除 `XFAIL: *`，真实 stdin 输入 `42`，两后端同时
  检查退出码 42 和输出 `got=42`，没有绕开 `scanf("%d", &x)`。

## 独立验证命令与结果

| 命令 | rc | PASS | FAIL | XFAIL | XPASS | SKIP |
|---|---:|---:|---:|---:|---:|---:|
| `.work/build/llvm/bin/llvm-lit -sv .work/llvm/clang/test/CodeGen/DADAO/varargs-slot.c .work/llvm/llvm/test/CodeGen/DADAO/varargs-save-area.ll` | 0 | 2 | 0 | 0 | 0 | 0 |
| `.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/varargs_mixed.test tests/lit/E2E/varargs_narrow.test tests/lit/E2E/varargs_overflow.test tests/lit/E2E/musl_printf_ptrs.test tests/lit/E2E/musl_scanf_int.test` | 0 | 5 | 0 | 0 | 0 | 0 |
| `.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/` | 0 | 72 | 0 | 0 | 0 | 0 |
| `python3 tools/run_differential.py` | 0 | 200 four-way agree | 0 divergence | — | — | 2 out-of-slice |
| `python3 scripts/manifest_check.py` | 0 | PASS | 0 | — | — | 0 |
| `python3 scripts/check_issues.py` | 0 | PASS; open 20, closed 37, total 57 | 0 | — | — | 0 |

差分的完整计数为：

- `AGREE(3-way)=200`
- `AGREE(interp+QEMU, gem5-SKIP)=2`
- `DIVERGE=0`
- `HARNESS=0`
- `QEMU-SKIP=0`
- `AGREE(4-way)=200`
- `Sail-SKIP(out-of-slice)=2`
- `SAIL-DIVERGE=0`

附加完整性检查：

| 命令/检查 | rc | 结果 |
|---|---:|---|
| `git diff --check` | 0 | 主仓库 diff 无 whitespace error |
| `git -C .work/llvm show --check 3aa546d1d0cd...` | 0 | LLVM commit 无 whitespace error |
| `git -C .work/llvm apply --check --reverse .../0050-...patch` | 0 | 0050 正好对应当前 LLVM commit |
| `git -C .work/llvm rev-list --parents -n1 3aa546d1d0cd...` | 0 | 单一 parent `72cb112b4c1e...`，为普通非 merge commit |
| `sha256sum 0050...patch` 与 `git format-patch -1 3aa546d1d0cd... --stdout` | 0 | SHA-256 同为 `71109b6b0bc41999c54f726dfda9895315f00135903d5406d0fceff37403ad6d` |

## 50/50 full replay 复核

由于本 reviewer 的硬约束只允许写本审查文件，未另建或改写 worktree。对实现者
已创建的独立 replay worktree
`/tmp/dl072a-llvm-replay-20260723` 做了只读独立核验：

- `git status --porcelain=v1`：空，worktree clean；
- manifest base：`ca7933e47d3a3451d81e72ac174dcb5aa28b59d1`；
- `git rev-list --count <base>..HEAD`：50；
- `git merge-base --is-ancestor <base> HEAD`：rc=0；
- replay HEAD：`271a3632f5431360afa5702b96d549e0eeb34f8c`；
- replay tree：
  `c9f9803b7fb5f35c8199174bfb1ff4a29ff420fe`；
- LLVM implementation commit `3aa546d1d0cd...` tree：
  `c9f9803b7fb5f35c8199174bfb1ff4a29ff420fe`；
- `series` 恰为 50 行，末项为 0050。

因此现有证据足以独立确认：50 个 patch 从 manifest pin 全部重放完成，最终
tree 与实现提交逐字节一致。

## 最终意见

DL-072a 在其明确的 RD/RB 标量范围内修复了 caller/callee/Clang 三层不一致，
并用真实双后端 libc 场景闭合了原 pointer-loss 故障。保留 broader
`Varargs` open issue 是必要且充分的边界控制；当前实现和文档均未越界声称
RF 或完整 aggregate 已支持。

**最终判决：Accepted。**
