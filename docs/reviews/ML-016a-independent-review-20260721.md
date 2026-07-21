# ML-016a 独立 review

日期：2026-07-21  
结论：**Diagnosis-accepted-with-findings**

## 核对范围

已阅读 `code-agent/tasks/ML-016a-mallocng-runtime-failure-repro.md` 与
`docs/reviews/ML-016a-mallocng-runtime-failure-repro-20260721.md`，并检查
`/tmp/ml-016a-mallocng-runtime-failure-repro/` 的原始 stdout/stderr、Gem5
trace、ELF 与 hash。未访问或引用用户指定的受限目录。

本次 review 未修改主仓库、`.work` source 或 ML-014a。检查开始和结束时，
`code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md` 均为未跟踪材料（`??`），
没有该路径的 tracked diff；`.work/source/qemu` 的既存
`target/dadao/cpu.c`/`.h` 修改被保留，未由本任务触碰。

## 核对结果

- 最终运行产物 ELF SHA-256 为
  `28484ac6ec0190a647181888a228d951c1543049be473b7112d54f19c5ee80e8`；
  对应 QEMU flat BIN SHA-256 为
  `c45429b20026f241de069949717e0ccb74f5c25cebca0f1fddf433ae4da7f578`。
  QEMU 使用该链接产物的配套 BIN，Gem5 使用同一次链接生成的 ELF。
- 独立重跑同一 probe：QEMU `timeout 60s` 返回 `42`，Gem5 `timeout 60s`
  返回 `42`；Gem5 输出 `SIM_END: trap-exit code=42`。两端均无 timeout、
  fault、panic 或 abort。
- 阶段证据覆盖完整：`MAIN`（startup→main）、`A_RETURN`、`B_RETURN`、
  `FIRST_WRITE`、`READBACK`、`FREE_B`、`FREE_A`、`OUTPUT_OK`，并以 guest
  exit `42` 收束。`OUTPUT_OK` 是固定参数 `write` 成功后的 marker，不是
  `puts` 输出结果。
- 两端第一块地址均为 `0x100000010`。第二块为 QEMU
  `0x1000021030`、Gem5 `0x1000200030`；相对间隔分别为 `0x21020` 和
  `0x200020`，差异为 `0x1df000`。两端都完成非空、对齐、不重叠检查以及
  两块内存的首/中/尾和 page-stride 写入、读回、逆序 free。
- 本轮没有重现历史 QEMU `130`/挂起、Gem5 `0` 或后续 Gem5 `134`；这只
  证明当前锁定产物下该失败未被复现，不能外推为 ML-014a 已解决。

## Findings

1. 第二次 `malloc` 返回地址存在真实的跨后端差异。这是本轮应保留的
   diagnosis finding，不应单独判作失败，也没有足够证据把它唯一归因于
   responder backing、对齐/游标策略或 mallocng 元数据布局。
2. 用同一类 probe 尝试链接 `puts` 时，`ld.lld` 实际返回 `rc=1`，诊断为
   `undefined symbol: puts`（由 probe 的 `main` 引用）；因此该版本没有可
   运行 ELF，也没有后端运行结果可供验收。固定 `write` 的 `rc=42` 不能替代
   ML-014a 所要求的高层输出里程碑。
3. 所以 ML-014a 仍为 **Not Accepted**；本轮没有修改 ML-014a、没有新增主仓库
   E2E 测试，也没有把本轮双后端成功误报为 ML-014a 验收。

## Review verdict

ML-016a 的诊断目标已被当前证据支持，结论为
**Diagnosis-accepted-with-findings**。后续最小切片应补充双端 mmap 参数/返回值
与 arena cursor 的 trace，并单独确认可链接的高层输出成员；不应在本轮结果上
扩大为 allocator 总体合同或 ML-014a 完成声明。
