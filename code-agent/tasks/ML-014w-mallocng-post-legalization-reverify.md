# ML-014w：修复后真实 mallocng 双后端最小复验

**执行环境**：本地 subagent worker；承接 Accepted ML-014v

**状态**：Ready（30-task run：3/30）

## 目标

在不重建 musl/lld 的前提下，用 ML-014v 后端重新构建 clang，且只重编译真实
`malloc_pointer_after`/`malloc_rw_after` probe object；沿用锁定 crt1、libc.a、
linker script 和 lld 重链接，用同一新产物在 QEMU 与 ML-014p 后 gem5 复验。

## Ownership 与 locked inputs

- worker 负责本任务 `.work/ML-014w-*` 产物和本 task MD；可增量构建 LLVM
  `clang`，不得改任何源码。
- 必须先后核对 `ld.lld`、musl `crt1.o`、`libc.a`、`dadao.ld` 的 hash 未变化；
  不运行 musl build、不构建 lld/all target、不覆盖 ML-014m/s 历史产物。
- 只使用当前 QEMU 和 ML-014p 后 gem5；不修改后端、patch series、root tests、
  issues、contracts、manifests 或用户原始 ML-014a。
- 外部架构资料不在 worker scope；多人共享仓库，不回滚他人改动。

## 执行阶梯

1. 增量构建 `clang`，记录命令/退出码及 LLVM source HEAD。
2. 重编译两个 probe，核对 undefined symbols、object identity 差异和链接拉入的
   libc.a member 集合；pointer object 应为控制样本，rw object 应消除末端 `-21`。
3. 保留 rw object/ELF 反汇编，证明完整 `0x1ffeb` 地址物化和合法访存立即数。
4. 同一 ELF/bin 分别运行 QEMU/gem5，记录 timeout、guest exit、stdout/stderr、
   fault；区分 pointer probe 的显式 13 与 simulator fault。
5. 记录最窄结论、未验证项、自审并等待独立 review。

## 验收

- locked lld/crt1/libc/script 身份不变；两个新 probe 可复现构建。
- `malloc_rw_after` 不再含 `stb/ldbu ... -21`，QEMU/gem5 预期均 exit 42；若不符，
  按真实结果定位新 blocker，不得伪报。
- pointer probe 作为控制，不把 exit 13 当作 selector 修复失败，也不冒充 raw
  pointer 直接观测。
- 不宣称 free、输出、allocator 总体、ML-014f 或 ML-014a 完成。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

