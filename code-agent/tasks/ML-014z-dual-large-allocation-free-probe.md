# ML-014z：双大块并存分配与反序 free probe

**执行环境**：本地 subagent worker；承接 Accepted ML-014y

**状态**：Ready（30-task run：6/30）

## 目标

验证两个不同尺寸、均走 mallocng mmap 阈值路径的大块能够同时存在、地址区间不
重叠、各自首中尾 sentinel 不串扰，并按反序调用真实 free。成功返回 42，不引入
输出依赖。

## Ownership

- worker 只写 `.work/ML-014z-*` probe/runner/产物与本 task MD。
- 使用尺寸 `131052` 与 `262144`；沿用当前锁定 toolchain/libc 和双后端。
- 不修改实现、root tests、patch series、issues、contracts、manifests 或 ML-014a；
  不做 use-after-free，不使用 printf/puts/varargs。
- 外部架构资料不在 worker scope；多人共享仓库，不回滚他人改动。

## 执行阶梯

1. 分配 a/b，检查非空、对齐、区间不重叠；每项失败码独立。
2. 对两块按 page stride 写 marker，再写首/中/尾 sentinel；完整读回并确认互不覆盖。
3. `free(b); free(a);`，以独立全局 marker 确认控制流返回，无 UAF。
4. 核对 map/archive/反汇编和 gem5 可得 syscall trace，证明两次 mmap 与两次
   munmap；同一产物跑 QEMU/gem5。
5. 更新记录、自审并等待独立 review。

## 验收

- 双后端 exit 42，无 timeout/fault；两块读写与反序 free 都在条件成功路径内。
- 证据能区分两次 mmap/munmap，不把地址偶然值或单后端结果冒充 allocator 总体。
- 不宣称复用、small-size/brk、输出或 ML-014f/ML-014a 完成。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

