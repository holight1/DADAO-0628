# ML-016y：DADAO frame lowering ABI 栈对齐修复

日期：2026-07-21

状态：Implementation completed；原始验收因 final-head provenance 被独立 review
拒绝，已由 ML-016z 重跑并闭合。nested LLVM commit
`d3bd9c15434fd7a48c0b7bab87354778cd932a72`。

原始独立 review：[ML-016y-independent-review-20260721.md](../../docs/reviews/ML-016y-independent-review-20260721.md)。
provenance 修复任务：[ML-016z-final-head-varargs-provenance.md](ML-016z-final-head-varargs-provenance.md)。

## 目标与范围

修复 DADAO frame lowering 对 ABI 8-byte frame alignment 的遗漏，统一
`emitPrologue`、`emitEpilogue` 与 `getFrameIndexReference` 的有效 frame size。
生产修改仅在 nested LLVM 的：

- `llvm/lib/Target/DADAO/DADAOFrameLowering.cpp`
- `llvm/test/CodeGen/DADAO/frame-lowering-stack-alignment.ll`

未修改 musl、QEMU、Gem5、ABI/spec、launcher、`docs/issues.yaml`、wiki 或 30-task
tracker；主仓库没有提交 LLVM 生产源。

## 实现

新增匿名命名空间 helper `getDADAOFrameSize`：

```text
raw = MFI.getStackSize() + VarArgsSaveSize
effective = alignTo(raw, 8)
```

prologue 发出 `-effective`，epilogue 发出 `+effective`。普通 frame index 使用
`objectOffset + effective`，因此 i32 local 的 `-4` frame 在实际 `-8` frame 中引用
`rb1+4`，不会继续使用未取整的 frame。

对 varargs save-area frame index：当 `VarArgsSaveSize != 0` 时，helper 先从 rounded
frame 中扣除 varargs save size 和普通 MFI frame，得到 save area 所在的 lower padding，
再向下取整到 8-byte boundary。这样 64-bit `sto` 的 base 对齐，save area 不与 local 或
callee-saved slot 重叠；没有寄存器 save 时保留 incoming overflow argument 的 fixed-object
语义。

## 验收矩阵

| 场景 | 静态结果 | QEMU | Gem5 |
|---|---|---:|---:|
| i32 local，raw frame 4 | `addi rb1,-8` / local `rb1+4` / `+8` | — | — |
| i64 local，raw frame 8 | `addi rb1,-8` / `+8` | — | — |
| no-frame direct trap | 无 frame adjustment | 42 | 42 |
| `direct_syscall1` | helper `-40`，caller 无窄 frame | 42 | 42 |
| `wrapper_noreturn` | 外层 `-8`，helper `-40` | 42 | 42 |
| `exit_shape` | 外层 `-8`，helper `-40` | 42 | 42 |
| `trap_stack_minus4` 对照 | 手写 `-4` 后 64-bit store | 129 | 129 |
| `trap_stack_minus8` 对照 | 手写 `-8` 后 64-bit store | 42 | 42 |
| include-free varargs runtime | `-128/+128`，save stores `0..112`，local `rb1+124` | 0 | 0 |

varargs 探针最终 compile/link/objcopy 全部 rc=0；最终 runtime 两端 rc=0。中间一次
试验用 `padding=4` 作为 save-area base，QEMU/Gem5 均 rc=129，静态定位为未对齐的
64-bit `sto rb1,4`；该证据促成最终 `alignDown(...,8)` 修订，未被隐藏。

## 回归测试

`frame-lowering-stack-alignment.ll` 是 include-free LLVM IR，包含：

- assembly FileCheck：i32 `-8/+8`、i64 `-8/+8`、i32 frame-index `+4`；
- MIR FileCheck：prologue/epilogue 和 no-frame direct trap；
- variadic function save-area placement，确认 save area 不覆盖上方 slot。

assembly FileCheck rc=0，MIR FileCheck rc=0。目录级 `llvm-lit` 未能启动，准确 rc=2：
当前构建树没有 `.work/build/llvm/bin/llvm-config`，lit 在初始化时失败；直接
`llc | FileCheck` 证据已保存，未将 lit 阻塞伪报成测试失败或成功。

## 提交与证据

- final nested commit：`d3bd9c15434fd7a48c0b7bab87354778cd932a72`
- parent：`be99e5505abe341100c62d70cd955b2df7e4711e`
- final source hash：见 `/tmp/ml-016y-frame-rounding-fix-20260721/hashes/final-source.sha256`
- 完整命令、stdout/stderr、rc、MIR、assembly、ELF/BIN、runtime 输出与 hash：
  `/tmp/ml-016y-frame-rounding-fix-20260721/`
- 版本：LLVM/clang 22.1.8，final clang VCSVersion 为 nested commit；QEMU runtime
  输出为 10.0.0，Gem5 runtime 输出为 25.1.0.1。

## 未决风险

`llvm-lit` 仍受缺少 `llvm-config` 阻塞；本轮没有运行完整 LLVM test suite、musl
全量构建或完整 E2E/differential 矩阵，因此不对这些范围作通过声明。varargs runtime
探针验证了当前 save-area/frame 形状，但更复杂的 overflow argument、动态 stack
object 和异常路径仍应由后续 target 级测试覆盖。
