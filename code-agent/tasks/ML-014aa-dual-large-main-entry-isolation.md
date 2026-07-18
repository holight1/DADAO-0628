# ML-014aa：双大块 ELF 的 startup→main-entry 分阶段隔离

**执行环境**：本地 subagent worker；承接 ML-014z Needs-isolation

**状态**：Ready（30-task run：7/30）

## 目标

只定位 ML-014z ELF 在 startup 间接调用 main 时为何偏离到栈地址。先证明或否定
同一代码布局、同一 archive member 集合下能进入 main；在 main-entry 双端成立前
不运行 allocator 阶段，不修改任何实现。

## Ownership

- worker 只写 `.work/ML-014aa-*` 派生 probe/runner/trace 与本 task MD。
- 保留 ML-014z 完整后续 body 和链接成员，通过 volatile stage 在 main 第一段
  立即返回专用码；不得让编译器消去后续 malloc/free 引用。
- 沿用锁定 clang/lld/crt1/libc.a/script 和双后端；不修改源码实现、root tests、
  patches、issues、contracts、manifests 或 ML-014a。
- 外部架构资料不在 worker scope；多人共享仓库，不回滚他人改动。

## 执行阶梯

1. 构造 stage=0 的 main-entry 变体：入口第一项可观测 marker/专用 guest exit，
   后续保留 ML-014z 完整 body；核对 object/ELF/map/成员与 main 入口地址。
2. 同一 ELF/bin 跑 QEMU/gem5，并保留 QEMU in_asm 与 gem5 Exec trace，证明实际
   call target、main 是否命中、返回/退出路径。
3. 与 Accepted ML-014y 和失败 ML-014z 的 startup/main callsite、寄存器搬运、
   relocation、代码/页布局逐项比较，指出首个静态或动态差异。
4. 若 main-entry 双端均命中，才提出后续 allocator stage 任务；若未命中，下一
   任务必须收口到 startup/call/relocation/code-layout，不进入 malloc。
5. 记录结论、置信度、自审并等待独立 review。

## 验收

- 同一 stage ELF 的两后端有可审计 main-entry 命中或未命中证据，不能只看 host rc。
- 给出首个可证明差异和最窄后续实现/诊断边界。
- 不宣称双块 allocator、ML-014f 或 ML-014a 完成。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

