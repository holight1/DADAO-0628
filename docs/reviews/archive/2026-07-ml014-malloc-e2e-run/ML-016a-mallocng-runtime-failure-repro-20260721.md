# ML-016a：mallocng runtime failure repro review（2026-07-21）

## 范围

本报告只记录 `/tmp/ml-016a-mallocng-runtime-failure-repro/` 的临时实验。没有修改主仓库、`.work` source、LLVM/QEMU/Gem5/musl、ML-014a、vectors、issues 或 wiki；没有访问或引用 `~/toolchain`、`~/knowledge-graph`。

## 构建

锁定输入为当前 `clang`/`ld.lld`、musl `crt1.o`/`libc.a` 和 `tests/scripts/dadao.ld`。最终 probe source 是从现有 exact ML-014af dual-large source 派生，仅加入阶段 marker、固定参数 `write` 和指针 hex 输出；临时文件：

```text
/tmp/ml-016a-mallocng-runtime-failure-repro/staged_dual_puts.c
/tmp/ml-016a-mallocng-runtime-failure-repro/staged_dual_puts.o
/tmp/ml-016a-mallocng-runtime-failure-repro/staged_dual_puts.elf
/tmp/ml-016a-mallocng-runtime-failure-repro/staged_dual_puts.bin
```

命令及真实 rc：

```text
clang --target=dadao -std=c99 -nostdinc -ffreestanding -O0 -c .../staged_dual_puts.c  => 0
ld.lld -T tests/scripts/dadao.ld --start-group crt1.o staged_dual_puts.o libc.a --end-group ... => 0
llvm-objcopy -O binary staged_dual_puts.elf staged_dual_puts.bin => 0
```

额外尝试将 `puts("MALLOCNG_OK")` 链入同一 probe，`ld.lld` rc=`1`：`undefined symbol: puts`。该 exact high-level-output probe 没有可运行 ELF，这是本轮的明确环境/产物缺口。

## 同一 ELF 双后端结果

QEMU rc=`42`，timeout=`no-timeout`；Gem5 rc=`42`，timeout=`no-timeout`，stdout 含 `SIM_END: trap-exit code=42`。QEMU stderr 为 0 bytes；Gem5 stderr 为 443 bytes 的既有 warning/info，无 fault/panic/abort。

阶段 marker 和实际返回地址：

```text
QEMU:
MAIN
A_RETURN p=0x0000000100000010
B_RETURN p=0x0000000100021030
RANGE_OK
FIRST_WRITE
READBACK
FREE_B
FREE_A
OUTPUT_OK

Gem5:
SIM_END: trap-exit code=42
MAIN
A_RETURN p=0x0000000100000010
B_RETURN p=0x0000000100020030
RANGE_OK
FIRST_WRITE
READBACK
FREE_B
FREE_A
OUTPUT_OK
```

解释边界：`MAIN` 是 startup→main 的用户态 marker；`A_RETURN`/`B_RETURN` 位于对应 `malloc` 返回后的分支；`FIRST_WRITE` 在两块写入完成后；`READBACK` 在全部 page-stride/sentinel 检查后；`FREE_B`/`FREE_A` 在逆序 `free` 返回并通过 marker 后；`OUTPUT_OK` 是固定 `write` 成功后的 marker；rc 42 是 guest exit。`131052` 与 `262144` 均覆盖已知 `MMAP_THRESHOLD=131052`。

## 当前诊断结论

本轮没有复现历史失败码。当前最窄、可复核的差异是第二次分配返回地址：QEMU 相对第一块间隔 `0x21020`，Gem5 间隔 `0x200020`，两者差 `0x1df000`；两端仍都完成全部写读/free/output 阶段。该差异不能单凭本 probe 唯一归因到某个实现组件。

ML-014a 仍未完成：`puts` 版本在当前 libc archive 中无法链接，且本轮没有修改/新增主仓库测试。下一诊断应只补双端 mmap 参数、返回值和 arena cursor 的寄存器级 trace，并确认可链接的高层输出成员；不应把本轮固定 `write` 的 rc 42 外推为 ML-014a 完成。

**Review verdict：Diagnosis complete / ML-014a Not Accepted。**
