# ML-014x：建立真实 malloc 返回指针合同 probe

**执行环境**：本地 subagent worker；承接 Accepted ML-014w

**状态**：Ready（30-task run：4/30）

## 目标

替代历史 `malloc_pointer_after` 将返回值错误硬编码为 mmap arena base 的判定。
创建最小真实 mallocng-linked probe，直接把 malloc 返回指针编码为固定 16 位十六
进制并通过固定参数 `write` 输出，同时检查非 NULL、自然对齐、位于当前 mmap arena
范围内，以及首字节可写读。用同一 ELF/bin 在 QEMU/gem5 建立一致返回合同。

## Ownership

- worker 只写本任务 `.work/ML-014x-*` probe/runner/产物与本 task MD。
- 沿用 ML-014w 已锁定 clang/lld/crt1/libc.a/linker script 和当前双后端；不得
  修改实现源码、root tests、patch series、issues、contracts、manifests 或原始
  ML-014a。
- 不使用 printf/varargs/puts；只允许手工 hex 转换和固定参数 write。
- 外部架构资料不在 worker scope；多人共享仓库，不回滚他人改动。

## 执行阶梯

1. `malloc(131052)`，保存返回值；输出 `p=0x<16hex>\n`，输出失败单独编码。
2. 检查 p 非 NULL、至少 16-byte 对齐、处于 `[0x100000000,0x100020000)`，并对
   `p[0]` 做写读；每个失败使用不同 guest exit，成功 42。
3. 编译/链接/反汇编，确认没有历史大偏移访问或 printf 依赖；记录 undefined /
   archive member 和锁定输入 hash。
4. 同一产物跑 QEMU/gem5，保留 stdout/stderr/exit/fault；输出值必须两端一致。
5. 记录结论、未验证项、自审并等待独立 review。

## 验收

- 双后端 exit 42，固定 hex 输出一致并提供 probe 自身的 raw pointer 证据；否则
  按真实结果收口 blocker。
- 不把 arena base 当 payload pointer，不把单次返回合同冒充 allocator 总体验收。
- 不触及 free、复用、多尺寸、输出库高层接口、ML-014f 或 ML-014a。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）

