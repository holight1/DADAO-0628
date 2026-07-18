# ML-014y：真实 mallocng 单次大块 free probe

**执行环境**：本地 subagent worker；承接 Accepted ML-014w/x

**状态**：Ready（30-task run：5/30）

## 目标

隔离验证真实 mallocng 的单次大块分配、首尾写读和 `free` 返回路径。probe 不做
高层输出、不做第二次分配；用分阶段 guest exit 区分 NULL、首写读、末写读以及
free 之前/之后的控制流，成功返回 42。

## Ownership

- worker 只写 `.work/ML-014y-*` probe/runner/产物与本 task MD。
- 沿用当前 ML-014v clang、锁定 lld/crt1/libc.a/script 与当前 QEMU/gem5；不得
  修改源码、root tests、patch series、issues、contracts、manifests 或 ML-014a。
- 分配大小固定 `131052`，必须调用真实 `free`；不得以 stub/no-op 替代。
- 无 printf/puts/varargs；外部架构资料不在 worker scope。

## 执行阶梯

1. 构造 `malloc(131052)`，检查非 NULL；首尾 byte 写读，各失败码独立。
2. 调用真实 `free(p)`，随后只设置/检查栈上或全局 marker，禁止 use-after-free；
   成功返回 42。
3. 核对 ELF/map/undefined/archive member，证明拉入 mallocng `free`/munmap 路径，
   且末端访问使用完整地址、无 `-21`。
4. 同一产物跑 QEMU/gem5，记录退出码、fault、syscall/munmap 可得证据。
5. 更新记录、自审并等待独立 review。

## 验收

- 双后端真实 exit 42，且反汇编与 archive 证据证明调用真实 free；否则记录 blocker。
- 无 use-after-free、无输出依赖，不把单次 free 冒充复用、多尺寸或 allocator 总体。
- 不宣称 ML-014f/ML-014a 完成。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

