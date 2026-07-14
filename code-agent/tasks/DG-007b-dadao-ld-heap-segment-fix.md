# DG-007b: dadao.ld 堆区加 PT_LOAD 覆盖，修 gem5 SE 缺页

**执行环境**: 本地 subagent（链接脚本 + 双后端验证）

**状态**: 通过（架构师复核）

**前置**：DG-007a 根因定位（`code-agent/tasks/DG-007a-gem5-elf-load-crash-rootcause.md` 完成区）、issue `gem5-se-heap-not-covered-by-elf-segment`（`docs/issues.yaml`）。

## 背景（DG-007a 已确认，直接复用）

`tests/scripts/dadao.ld` 里：
```
. = ALIGN(4096);
__heap_start = .;
__heap_end = 0x87E00000;
```
这两个符号是裸 location-counter 赋值，没有落进任何 `PHDRS`（`:text`/`:data`）分配的输出 section。picolibc 的 `libos/fallback/sbrk.c`（`__fallback_sbrk`）纯指针递增（`__heap_start`..`__heap_end`），不经过任何 syscall，完全依赖链接脚本保证这段内存"真实存在"。

gem5 SE 严格按 ELF 的 `PT_LOAD` 段 `memsz` 建页表——`malloc_hello.elf` 的第二个 `PT_LOAD`(`:data`) 止于 `.bss` 结束处，不覆盖堆区，第一次 `malloc()` 写堆内存时缺页崩溃（`Page table fault @ 0x80009000`，DG-007a 已用 gdb 确认故障 PC 在 picolibc `malloc.c` 的 `_set_size` 内部）。

QEMU 端用 `llvm-objcopy -O binary` 产出裸 flat binary（`-kernel %t.bin`），不解析 ELF/PT_LOAD，是一整块已映射 DRAM，故不受影响——**gem5 的行为是对的，缺陷在 `dadao.ld`**。

## 做什么

1. 给堆区一个真正被 `PHDRS` 覆盖的输出 section（例如 `SHT_NOBITS` 的 `.heap`，放进 `:data` 段，或单独一个新 `PT_LOAD` 段），让该段的 `memsz` 真正扩展到 `__heap_end`（`0x87E00000`）。`SHT_NOBITS`（类似 `.bss`）不占文件字节，QEMU 侧的 flat binary 产出不受影响（`llvm-objcopy -O binary` 对 NOBITS 段本就不写文件内容）。
2. 确认 `__heap_start`/`__heap_end` 两个符号仍然可用（picolibc `libos/fallback/sbrk.c` 直接引用这两个符号名，不要改名）。
3. **不要**改动 QEMU 侧 `brk_base` 相关代码（那是 ADR-0014 D3 里 `pico_stubs.s` trap 版 `_sbrk` 路径用的，当前是死代码，与本任务无关，见 ML-003m 完成区）。

## 约束

- 不改 `pico_stubs.s`/`stdout_min.c`/`crt0.s`。
- 不改 gem5 源码（本任务修的是 DADAO-0628 侧的链接脚本，不是 gem5 加载器）。
- 不回归：E2E 29/29、四方 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200。

## 验收（架构师亲跑）

```bash
cd ~/DADAO-0628
# 重新链接 malloc_hello 测试产物为真实 ELF（非 objcopy 后的 flat binary），确认 PT_LOAD 覆盖堆区
.work/build/llvm/bin/ld.lld -T tests/scripts/dadao.ld -nostdlib <crt0.o> <stubs.o> <stdout.o> <hello.o> .work/picolibc/build-dadao/libc.a -o /tmp/malloc_check.elf
# 用 python struct 或 llvm-objdump 确认第二个 PT_LOAD 段 memsz 覆盖到 0x87E00000 附近
timeout 60 ~/DADAO-gem5/build/DADAO/gem5.opt ~/DADAO-gem5/tests/dadao/dadao_se.py /tmp/malloc_check.elf   # 应不再 panic，应真正执行到 malloc/free 逻辑（可能会撞到 codegen-indirect-call-rb0-misuse，那是另一个独立 issue，见下方约束）
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
```

**判别强调**：malloc_hello 的 ELF 在 gem5 SE 下不再因堆缺页崩溃（若因 `codegen-indirect-call-rb0-misuse` 或其它无关原因崩溃，说明这个独立 issue 需要一起修才能让 `malloc_hello.test` 补上 gem5 断言——**若 `malloc_hello.c` 本身不涉及函数指针间接调用，理论上不该撞上 rb0-misuse，须确认**；只需保证本任务范围内的"堆缺页"问题真正解决，若 gem5 因为其它独立原因还跑不通，如实报告，不要为了"让测试过"而绕过或篡改断言）。

## 参考指针

- DG-007a 完成区（`code-agent/tasks/DG-007a-gem5-elf-load-crash-rootcause.md`）：完整根因证据链
- `docs/issues.yaml` 的 `gem5-se-heap-not-covered-by-elf-segment` 条目
- `tests/scripts/dadao.ld`（现有 PHDRS/SECTIONS 结构）
- `.work/picolibc/libos/fallback/sbrk.c`（`__heap_start`/`__heap_end` 的消费方，符号名不能改）
- `tests/lit/E2E/malloc_hello.test`（gem5 断言待补，当前只有 QEMU 行）

—— 自审见 DS.md §自审流程同等标准（subagent 自己复核，逐条 finding + 判决），**必须真跑 gem5 验证不再缺页**，不能只检查链接脚本语法。

---

## 架构师复核（2026-07-14，ground-truth）：通过

- `dadao.ld` diff 审阅：`.heap (NOLOAD) : { __heap_start = .; . = 0x87E00000; __heap_end = .; } :data`——真实落进 `:data` PHDR 的 SHT_NOBITS section，符号名未变，picolibc `libos/fallback/sbrk.c` 引用不受影响。
- 独立重跑：`ninja llc/clang/lld/...` 全新构建 → `llvm-lit tests/lit/E2E/` 29/30（1 个既有失败 `syscall_hello.test` 已用 `git stash` 独立确认在两个修复之前的干净提交树上同样失败，与本任务无关，另登记 issue `syscall-hello-write-output-missing`）→ 四方差分 AGREE(3-way)=200/DIVERGE=0、Sail AGREE(4-way)=200，全部不回归。
- gem5 上 `malloc_hello` 真的推进过了原 heap 缺页点（tick 187000→3222000），如实撞上另一个独立已知 issue（`codegen-indirect-call-rb0-misuse`）而非声称"全过"——诚实报告，未绕过。
- issues.yaml 的 `status: resolved` 已更正为 `status: closed`（schema 只认 open/closed）。

**判定**：通过，提交。
