# ML-003f: QEMU printf 挂起调试（cpu_io_recompile 循环不收敛，非寄存器数量问题）

**执行环境**: 本地 DS · DADAO-0628（QEMU TCG 调试，picolibc printf 双后端最后一步）

**状态**: 待执行

**前置**：ML-003e（MC 重定位缺口 G1/G2 已修，commit `b3bbe0418bee`/patch 0025）——picolibc `puts.o`/`stdout` 结构体链接正确（跨 section 调用 + 数据段函数指针都真解析对了）。链接后的完整 printf 程序**在 QEMU 上挂起**，这是 goal①（picolibc printf 双后端真跑）最后一个已知障碍。

---

## 背景 / 已排除的诊断
ML-003b 上一轮 DS 报告"QEMU printf 挂起，疑似寄存器范围 rd0-31 vs LLVM rd0-63"——**架构师已证伪此诊断**：
- spec `contracts/isa/spec.md` 明确定义 64 个 `rd0-rd63`
- QEMU `CPUDADAOState` 的 `rd[64]` 数组，decode 逻辑全文 grep **无任何 `&0x1f`/`&31` 类寄存器数量限制代码**
- **QEMU 完全支持 rd32+**，这不是真根因（别沿这条路排查）

## 真实现象（架构师已复现并定位到具体 PC）
用 `stdout_min.c` 风格的 tinystdio stdout 接线（`FDEV_SETUP_STREAM` + `_write` 回调）+ picolibc libc.a + crt0 + 标准链接，得到完整 `printf("hi\n")` 程序，QEMU 跑：**5 秒超时无输出无退出**（真挂起，非慢）。

`qemu-system-dadao ... -d exec -D trace.log` 抓到卡点：
```
Trace 0: 0x<host> [guest-regs.../00000000800001d0/.../...]
cpu_io_recompile: rewound execution of TB to 00000000800001d0
```
**同一 guest PC（`0x800001d0`）反复触发 `cpu_io_recompile`，不收敛**——trace log 在几秒内产生数百万行，是真死循环/卡死，不是简单变慢。

反汇编该 PC：
```
800001cc: rd2rb rb8, rd16, 1        ; rd16 之前从栈槽(rb1+400)加载
800001d0: ldo rd16, rb8, 8          ; ← 卡在这条：load [rb8+8]
```
`ldo rd16, rb8, 8` 大概率是加载 `stdout` 结构体的 `put` 函数指针字段（tinystdio `FDEV_SETUP_STREAM` 布局，供 vfprintf 间接调用字符输出回调）。

**推测方向（未证实，DS 需实测钉死）**：`cpu_io_recompile` 是 QEMU TCG 处理"翻译块内出现 MMIO 访问需要精确异常"的机制——通常应该是"一次性重编译+继续前进"，不该无限循环在同一 PC。反复触发意味着：
1. 该 `ldo` 的目标地址（`rb8+8`）**落进了 MMIO 映射区**（如 exit-port `0x10000000`，非预期的 `stdout` 结构体地址）——即 `rb8` 的运行时值算错了（可能是这段 `rd2rb`/栈 spill/reload 链路某处的地址计算 bug，或与 ML-002a 修过的 trap/pc 保存机制有交互）；
2. 或者 QEMU 的 `cpu_io_recompile` 实现本身在这个场景没有正确前进 PC/未能让重编译后的单指令 TB 真正完成执行（QEMU 侧 bug，非 DADAO 语义层）。

## 做什么
1. **钉死 `rb8` 的运行时值**：用 QEMU gdbstub（`-s -S` + `gdb-multiarch` 连接，或 QEMU monitor `info registers`，或加临时调试 print）在卡住的 PC 处读 `rb8` 实际值——确认它是不是落在 `0x10000000`(exit-port MMIO) 附近，还是别的意外地址。
2. **根据 #1 结果分流**：
   - 若 `rb8` 是**错误地址**（该是 `stdout` 结构体地址如 `0x80001xxx`，实际却是别的）→ 往回追这段代码生成的来源（是 DS 的 `stdout_min.c` 手写 asm/C 有 bug，还是 LLVM 后端把某个栈槽/寄存器搞错了）——**注意别急着怪 LLVM 后端，先看 C 源码和链接后的实际数据布局是否符合预期**（对照 `.data`/`.bss` 段实际内容，确认 `__stdout`/相关符号地址）。
   - 若 `rb8` **是对的**（真的是 `stdout` 结构体地址，`rb8+8` 是 `put` 字段该在的位置，值也该合法）→ 那就是 **QEMU TCG `cpu_io_recompile` 机制本身的 bug**（`accel/tcg/`），需要看 QEMU 侧代码为何这个特定访问模式导致无限重编译不前进（参考现有 feedback `feedback_qemu_escape_jmppc.md`/`feedback_dadao_smc_heisenbug.md` 里记录的同类 QEMU TCG 坑，可能是同一类"翻译块状态与实际执行不同步"问题）。
3. **验证修复**：`printf("hi\n")` 完整程序在 QEMU 真正跑出 "hi" + 正常退出（非挂起）。若涉及 gem5，同步验证双后端（本任务先聚焦 QEMU 单后端修好，gem5 若同样卡则一并看，若 gem5 OK 只 QEMU 有事则先记 issue 精确指出差异）。

## 约束
- **别沿"寄存器数量 rd32+"方向排查**——已证伪。
- 不回归：E2E 27/27、四方 200/0；ML-003e 的 G1/G2 修复不退步。
- 真机调试为主（gdbstub/寄存器读取），别靠猜测；`cpu_io_recompile` 反复触发本身就是强异常信号，说明进程状态没有真正前进。

## 验收（架构师亲跑）
```bash
cd ~/DADAO-0628 && ninja -C .work/build/llvm llc clang lld llvm-mc
# 完整链 printf 测试（同架构师复现步骤：crt0 + stdout wiring + libc.a + pico_stubs + dadao.ld）
# QEMU 应输出 "hi" + exit=0（而非 timeout 挂起）
timeout 10 <qemu跑上面链好的 elf/bin> ...
llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
```
**判别强调**：QEMU 真跑出 "hi" 且正常退出（非 timeout）；`-d exec` trace 不再出现同一 PC 反复 `cpu_io_recompile`；不回归。

## 参考指针
- ML-003b 完成区（DS 上一轮"寄存器范围"误诊记录，已证伪）；架构师复核记录（`-d exec` trace 定位方法、卡点 PC/指令）
- `feedback_qemu_escape_jmppc.md`/`feedback_dadao_smc_heisenbug.md`（历史同类 QEMU TCG MMIO/异常处理坑，参考排查思路）
- ML-002a（trap/pc 保存机制，`env->pc` 相关，若怀疑交互）
- `stdout_min.c` 风格 tinystdio 接线（`/tmp/stdout_min.c` 是 DS 上一轮手写的，非仓库文件——本任务若需要复现材料，DS 按 ML-003b 任务里的 `FDEV_SETUP_STREAM` 惯例重建）
- 后续：解锁后回 ML-003b 收 goal①（printf 双后端真跑，最后一步）

—— 自审见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录占位必填——**AC/零 finding 也写实质记录**）。**subagent 必须真跑 printf 看真输出+真退出**（非"看起来该收敛"）。归因必须有寄存器/内存实测证据，不接受"疑似"式猜测结论。

---

## 审阅记录（subagent）

> **[架构师预置占位 · DS 必填]** DS 返回前必须开 subagent 代码级 review，逐条 finding + 处置表 + 判决写入此区。**占位未替换成实质记录 = 未自审 = 直接打回（AC/零 finding 也写：判决行 + 逐条核验点附证据 + finding:无）。**
> 特别核：真跑出 "hi" + 正常退出（非猜测"应该行"）？根因有寄存器/内存实测证据支撑（非"疑似"）？E2E/四方不回归？
