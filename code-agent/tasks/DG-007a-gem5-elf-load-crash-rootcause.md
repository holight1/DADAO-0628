# DG-007a: 根因定位 — gem5 SE 无法加载 ld.lld 产出的真实多段 ELF

**执行环境**: 本地 subagent（gem5 内部语义调试，按 feedback_ds_gem5_semantic_unreliable 规则不派 DS）

**状态**: 待执行

**前置**：issue `gem5-se-lld-elf-load-crash`（`docs/issues.yaml`）。架构师已用两个不同的真实 lld 链接产物（`printf_hello.elf`、`malloc_hello.elf`）独立复现同一崩溃，证明与 malloc/heap 无关。

## 现象（架构师已复现，直接复用不必重跑）

```
timeout 60 ~/DADAO-gem5/build/DADAO/gem5.opt ~/DADAO-gem5/tests/dadao/dadao_se.py <elf>
```
两个 ELF 均在极早（tick=187000，`main()` 运行前）崩溃：
```
panic: Page table fault when accessing virtual address 0x80009000
```
`printf_hello.elf`（完全不涉及 malloc/heap）同样崩溃，证明与堆无关。

## 已知的 ELF 布局事实（架构师已 dump，直接复用）

`printf_hello.elf` 程序头（大端 ELF，`EI_DATA=2`）：
```
seg0: type=PT_LOAD flags=R+X offset=0x0    vaddr=0x7ffff000 filesz=0x7368 memsz=0x7368
seg1: type=PT_LOAD flags=R+W offset=0x8000 vaddr=0x80007000 filesz=0x20   memsz=0x20
```
节头（`llvm-objdump -h`）：`.text` sh_addr=0x80000000、`.rodata` sh_addr=0x80006000、`.data` sh_addr=0x80007000（size 0x20）。`.bss` 本例大小为 0。

`dadao.ld` 的 `PHDRS` 用 `text PT_LOAD FILEHDR PHDRS;`（ld.lld 把 ELF header + program headers 放进第一个 PT_LOAD 段的头部，段起始地址比 `.text` 低一页——`seg0.vaddr=0x7ffff000` 比 `.text` 的 `0x80000000` 低 `0x1000`，这是 lld 的标准页对齐布局，不一定是 bug）。故障地址 `0x80009000` 落在两个 PT_LOAD 段覆盖范围之外（`seg1` 止于 `0x80007020`，下一页 `0x80008000`，再下一页才是 `0x80009000`）。

## 已知的对照事实

- 已有的 gem5 双后端 E2E 测试（`div_rem.test`/`nested_call.test` 等）全部走 `%llvm-objcopy -O binary --only-section=.text` 从裸二进制截出 `.text`，再用 `%gen_min_elf`（`~/DADAO-gem5/tests/dadao/gen_min_elf.py`）**合成**一个单段最小 ELF 喂给 gem5——从未加载过 `ld.lld` 真实产出的多段 ELF。
- `crt0.s` 的 `_start` 不设置 `rb1`（SP），注释写"Trampoline 设 SP=0x87FF0000"——这是 QEMU 专属机制（`-bios %trampoline`）。gem5 SE 靠 `Process::argsInit`（`~/DADAO-gem5/src/arch/dadao/process.cc`）自己设 `rb1`，与 QEMU 完全不同的路径，理论上不受此影响，但需要在排查中确认。
- `~/DADAO-gem5/src/arch/dadao/process.cc` 的 `brk_point = roundUp(image.maxAddr(), PageBytes)`——`image.maxAddr()` 由 gem5 通用 ELF loader（`src/base/loader/elf_object.cc` 或类似）解析程序头得出，如果该 loader 对"headers 在段起始、entry 在段内偏移一页"这种布局的 `maxAddr()`/内存映射计算有误，可能是根因来源之一。

## 做什么

1. 确认崩溃发生的具体阶段：是 gem5 加载 ELF 时就已经把某个不该映射的地址标记为"已映射"（导致 `argsInit`/`brk_point` 算错），还是加载本身没问题、是程序执行到某条指令时访问了 `0x80009000`（用 gdbstub 或 gem5 debug trace，如 `--debug-flags=Exec` 之类，定位是哪条 DADAO 指令触发的访问，此时的 `pc`/寄存器状态）。
2. 若是执行阶段访问：追踪 `0x80009000` 是被谁计算出来的（是不是 `rb1`/栈指针、还是某个基于 ELF header 里某字段计算出的地址、还是 `argsInit` 里某个写死的 offset 撞上了这个巧合值）。
3. 若是加载阶段问题：读 gem5 通用 ELF loader 如何处理 PT_LOAD 段的 `p_vaddr`/`p_offset`/`p_filesz`/`p_memsz`（尤其关注 `p_vaddr < entry` 且 `p_offset=0` 这种"headers 内嵌在第一个可加载段"的布局，是否被正确处理），对比 `gen_min_elf.py` 合成的 ELF 与 `ld.lld` 真实产出的 ELF 在这些字段上的差异，确认是不是这个差异触发的。
4. 找到具体的错误注入点（哪一行代码、哪个字段计算错误）,产出根因结论 + 建议的修复方向(不在本任务实现修复，只定位)。

## 约束

- **只读诊断，不改代码**（修复是 DG-007b 的范围）。
- 允许临时加调试打印/用 gdbstub，但排查完须说明加了什么、验证后是否已清理（若为了本任务分析方便暂留请注明，交给 DG-007b 一并清理）。
- 不改 `dadao.ld`/`crt0.s`/其它已提交源码（若怀疑这些文件的布局是根因来源，指出具体哪里、为什么，不要直接改）。

## 验收（架构师亲跑）

- 根因结论清晰、有实测证据支持（trace/dump/日志，不是猜测）。
- 明确指出问题出在 gem5 加载器 / gem5 执行阶段 / DADAO 侧文件（`dadao.ld`/`crt0.s`）三者中的哪一个，及具体代码位置。
- 若怀疑是 `dadao.ld`/`crt0.s` 一侧的问题，需要说明为什么 QEMU 端相同的文件不受影响（QEMU 走 trampoline bios，gem5 走 `argsInit`，两者对同一 ELF 的处理方式本身不同，需要讲清楚具体差异点）。

## 参考指针

- `~/DADAO-gem5/src/arch/dadao/process.cc`（`brk_point`/`argsInit`/`stack_base`——DG-006a 已修过 63-bit stack_base 越界这一类问题，本次故障地址 `0x80009000` 明显在 48-bit 空间内，大概率不是同一类问题，但值得对照）
- `~/DADAO-gem5/tests/dadao/gen_min_elf.py`（既有测试合成 ELF 的方式，与 `ld.lld` 真实产出对比的基准）
- `~/DADAO-gem5/tests/dadao/dadao_se.py`（SE 模式跑法）
- `tests/scripts/dadao.ld`、`tests/scripts/crt0.s`（DADAO-0628 侧的链接脚本/启动代码）
- `docs/issues.yaml` 的 `gem5-se-lld-elf-load-crash` 条目（背景，含架构师已 dump 的程序头数据）
- feedback `feedback_ds_gem5_semantic_unreliable.md`（gem5 内部工作的验收标准：ground-truth 复跑，不轻信完成区）
