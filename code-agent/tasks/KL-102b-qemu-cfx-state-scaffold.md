# KL-102b：QEMU CFX 状态容器与 reset scaffold

**执行环境**：本地 subagent，QEMU 单后端实现切片

**状态**：Accepted（30-task run：17/30）

## 背景

KL-102a 已冻结实现顺序：先有每 hart CFX 状态容器和可观察 reset 初值，再接
`cfx2rc`/`escape` 的 O1 语义。本任务只做 QEMU 状态 scaffold，不实现 handoff、
权限检查、guest vector、MMU 或 nested trap。

## 目标与 ownership

worker 独占 QEMU scaffold 的实现与证据，负责：

- `.work/source/qemu/target/dadao/cpu.h`：加入明确的 mode/code/mask 及最小
  power frame 字段，不复用 `trap_*` 或寄存器 bank；
- `.work/source/qemu/target/dadao/cpu.c`：在 reset 初始化 hypv/power/all-ones
  的 scaffold，并保留测试机 `0x00100000` 入口策略；
- root `components/qemu/patches/0019-dadao-cfx-state-scaffold.patch` 及
  `components/qemu/patches/series`：以可重放 patch 记录源码变更；
- task-owned validation sidecars，至少包含 patch check、编译/静态检查命令和
  现有 host shortcut 不变的证据。

## 约束

- 不实现 `cfx2rc`、`escape`、CFX dispatch、O1/O2 测试，不改 gem5/LLVM/kernel。
- 不访问或引用 `~/toolchain`、`~/knowledge-graph`；不修改 `docs/issues.yaml`
  或 wiki pin。
- 不回滚其他人的修改；若源码不是干净的，保留并在任务记录中说明。

## 验收

- QEMU 源码与 root patch series 可重放，`git apply --check`/等价 patch 校验通过。
- 字段初始化不影响已有 ML-014 host `cfx_smon` 路径；至少做编译或等价静态检查。
- 独立 reviewer 复核字段、初始化、patch 可重放性及 scope 没有越界。

## 完成区

### 结果

- `.work/source/qemu/target/dadao/cpu.h` 新增独立的 `DADAORunMode`、
  `DADAOCfxCode`、`DADAO_CFX_MASK_ALL`，以及只含
  `prev_run_mode`/`prev_cfx_mask`/`cause_ip` 的 `DADAOCfxPowerFrame`；状态放在
  `CPUArchState`，不复用 `trap_*` 或寄存器 bank。
- `.work/source/qemu/target/dadao/cpu.c` 在 `dadao_cpu_reset_hold()` 初始化
  `hypv=3`、`cfx_power=63`、全 1 mask 和 power frame，并保留测试机 PC
  `0x00100000`。
- 新增 `components/qemu/patches/0019-dadao-cfx-state-scaffold.patch`，并追加
  到 `components/qemu/patches/series`。

### sidecar / 命令

- `git -C .work/source/qemu diff --check`：通过。
- `git apply --check components/qemu/patches/0019-dadao-cfx-state-scaffold.patch`：通过。
- 静态 grep 核对字段、reset 初值、`0x00100000` 及既有 host `cfx_smon` 路径：通过。
- 在临时 QEMU worktree 以 `git am` 重放 0019，并以 `git diff --exit-code` 对照当前源码：通过。

### scope

仅实现 QEMU CFX 状态容器与 reset scaffold；未实现 `cfx2rc`、`escape`、CFX
dispatch、权限、guest vector、MMU、nested trap，也未接入或修改现有 host
`cfx_smon`。未修改 gem5、LLVM、kernel、docs、issues 或 wiki；保留根仓库既有
并行任务改动。

### 独立 review

- `docs/reviews/KL-102b-independent-review-20260721.md`：`Accepted`。
- reviewer 确认字段/初始化符合 scaffold scope，测试机 PC 与 HBI vector 已区分，
  patch 可重放，host `cfx_smon` 未受影响，且没有越界实现 handoff/CFX/MMU。
