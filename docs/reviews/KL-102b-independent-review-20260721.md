# KL-102b 独立 review（2026-07-21）

## 结论

**Accepted**。

本轮只读核查 `.work/source/qemu/target/dadao/cpu.h`、`cpu.c`、
`components/qemu/patches/0019-dadao-cfx-state-scaffold.patch`、`series` 与
KL-102b/KL-102a task/review 记录；未访问 `~/toolchain` 或
`~/knowledge-graph`，未修改 worker 代码、task MD 或其他文件。

## 核查结果

- **字段类型与初始化符合 KL-102a scaffold scope。** `cpu.h:37-57,71-84`
  增加独立的 `DADAORunMode`、`DADAOCfxCode`、64-bit 全 1 mask，以及只含
  `prev_run_mode`、`prev_cfx_mask`、`cause_ip` 的 `DADAOCfxPowerFrame`；字段放在
  `CPUArchState`，没有复用寄存器 bank 或 `trap_*` scratch。DADAO
  `TARGET_LONG_BITS=64`，frame 与 mask 使用 `target_ulong`/`UINT64_MAX` 相容。
  `cpu.c:55-60` reset 明确初始化 `hypv=3`、`cfx_power=63`、全 1 mask、power
  frame 和 `cause_ip=0`。该 frame 初值仅是 scaffold 的确定性状态；没有被
  `escape`/handoff 读取，因此没有提前声称实现 O1 语义。
- **PC 与 hypv scaffold 正确区分。** `cpu.c:55-61` 保留
  `env->pc=0x00100000`；该值对应 ADR-0004 的 M1 test-machine entry，不被写成
  HBI/SEE 的 `cfx_power_hypv_excp_vector`。patch 说明也明确是 “M1 test-machine
  entry PC”，且未加入 vector/guest handoff。
- **patch/series 可重放且顺序正确。** `0019` 只修改 `cpu.c` 和 `cpu.h`，其
  patch 前置索引 `547f7bd`/`02f5b78` 与 QEMU `HEAD` 对应 blob 一致；追加在
  `components/qemu/patches/series:20`，位于 0018 之后。当前已应用源码执行
  reverse `git apply --check` 通过，patch 与源码增量为 6+26 行，`git diff --check`
  通过。未执行实际 apply，以保持本轮只读。
- **host `cfx_smon` 未受影响。** patch 只改 reset 字段和 `CPUArchState`；现有
  `cpu.c:130-237` 的 `EXCP_CFXTRAP`/`cfxcode==2` responder、`helper.c:99-108`
  的 trap scratch/异常出口以及 `translate.c:452-464` 均未被该 patch 修改。
- **没有越界实现。** patch 未增加 `cfx2rc`、`escape`、CFX dispatch、权限/ mask
  检查、guest vector、MMU、nested trap 或 O1/O2 测试；其 commit message
  `0019:6-10` 明确列出这些排除项。新增字段没有消费者，因此不会把 scaffold
  误当作真实 handoff 或新的 `cfx_smon` 状态机。

## 可复核命令

```bash
cd /home/holight/DADAO-0628

nl -ba .work/source/qemu/target/dadao/cpu.h | sed -n '37,85p'
nl -ba .work/source/qemu/target/dadao/cpu.c | sed -n '40,63p;115,237p'
nl -ba components/qemu/patches/0019-dadao-cfx-state-scaffold.patch
nl -ba components/qemu/patches/series | tail -n 8

git -C .work/source/qemu rev-parse HEAD:target/dadao/cpu.c HEAD:target/dadao/cpu.h
git -C .work/source/qemu apply --reverse --check \
  /home/holight/DADAO-0628/components/qemu/patches/0019-dadao-cfx-state-scaffold.patch
git -C .work/source/qemu diff --check
git -C .work/source/qemu diff --name-only

rg -n 'cfx2rc|escape|inner_run_mode|inner_cfx|cfx_smon|EXCP_CFXTRAP' \
  .work/source/qemu/target/dadao \
  components/qemu/patches/0019-dadao-cfx-state-scaffold.patch
```

