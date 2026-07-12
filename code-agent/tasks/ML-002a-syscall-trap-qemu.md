# ML-002a: syscall 层（QEMU）— trap cfx_smon + SYS_write/exit/brk

**执行环境**: 本地 DS · DADAO-0628（QEMU target/dadao + E2E）

**状态**: 待执行

**前置**: ADR-0014（libc/syscall charter）；ML-001a recon；WU-001a（pin 9f378f4）。musl 里程碑首个实现片。

---

## 背景 / 目标
按 ADR-0014：syscall 走 SEE `trap cfx_smon`→CFXTRAP→cfx_smon responder（spec-first）。本任务在 **QEMU** 实现 syscall 机制 MVP（gem5 后续 ML-002b），用**手写 asm 测试**证明 `trap`-write + `trap`-exit 走通——**先把机制打通，libc（picolibc）留 ML-003a**。

**范围内**：QEMU `trap` 指令 + cfx_smon responder（模拟器侧）+ SYS_write（→cfx_uart 宿主 stdout）/ SYS_exit（→cfx_power 退出码）/ SYS_brk（简单堆）+ 手写 asm 测试。
**范围外**：gem5（ML-002b）、picolibc（ML-003a）、真 SEE monitor firmware（未来）。

## syscall ABI（ADR-0014 D2，本项目约定）
| 项 | 寄存器 |
|----|--------|
| syscall number | `rd16` |
| 参数 arg0..5 | `rd17`..`rd22` |
| 返回值 | `rd31` |
| 陷入 | `trap cfx_smon` |
| 编号 | Linux asm-generic：`write=64` `exit=93` `exit_group=94` `brk=214` |

## 做什么
1. **实现 `trap` 指令**（QEMU `target/dadao` decode + translate）：`trap` 是系统 cfx 指令（cfx 格式带 cfxcode，spec §2.8 ciii/crii；参 opcodes.yaml 的 cfx 编码 + wiki SEE §5 trap 定义，**pin 9f378f4**）。`trap cfxcode` → 触发 CFXTRAP 异常进入（走/扩 `dadao_cpu_do_interrupt` 路径）。
2. **cfx_smon responder（模拟器侧 MVP）**：`trap cfx_smon`（cfx_smon 的 cfxcode 从 SEE § 查，pin 9f378f4）→ 读 ABI 寄存器（rd16=sysno, rd17-22=args, rd31=写返回）→ 分派：
   - **SYS_write(64)**：`write(fd,buf,len)`——从 args 取 buf 地址+len，读 guest 内存字节，`fd=1/2`→宿主 stdout/stderr（cfx_uart 设备写）；rd31=写出字节数。
   - **SYS_exit(93)/exit_group(94)**：`qemu_system_shutdown_request_with_code(退出码=arg0)`（cfx_power POWEROFF，沿用 ADR-0004 退出码协议）。
   - **SYS_brk(214)**：简单 program-break（维护一个 brk 指针，dadao.ld 预留 heap 区；rd31=新 brk）。
   - 未知 sysno：rd31 = -ENOSYS（或明确报错），不静默。
3. **异常进入吸收 SEE 最新版**：实现 `trap`→CFXTRAP 时参 **pin 9f378f4 的 SEE §5**（WU-001a B 桶 `wiki-9f378f4-sbi-see-deferred-delta`：§5 重构/中断模型前移/FPEXCP——吸收 trap/CFXTRAP 相关部分）。
4. **QEMU 改动同步 patch** `components/qemu/patches/`（format-patch 入 series）。

## 约束
- 只改 QEMU `target/dadao`；语义按 wiki SEE §5（trap/CFXTRAP）+ ADR-0014 ABI。
- **不回归**：现有 QEMU 向量、lit E2E 26 例、四方 AGREE(4-way)=200/DIVERGE=0、halt-exit 路径（现有裸机程序）不退步——libc 程序走 cfx_power、裸机走 halt，并存。
- 新增 syscall asm E2E 入 `tests/lit/E2E/`（**测 stdout 内容 + 退出码**——需扩测试 harness 捕获 stdout）。

## 验收（架构师亲自复跑）
```bash
cd ~/DADAO-0628 && (cd .work/source/qemu/build && ninja qemu-system-dadao 2>&1 | tail -1)
# 手写 asm：trap-write "hi\n" 到 stdout(fd=1) + trap-exit 42
# _start: 设 rd16=64(write),rd17=1(fd),rd18=buf,rd19=3(len); trap cfx_smon
#         设 rd16=93(exit),rd17=42; trap cfx_smon
QEMU=.work/source/qemu/build/qemu-system-dadao
OUT=$($QEMU -M dadao-m1 -nographic -bios trampoline.bin -kernel syscall_test.bin 2>/dev/null); echo "exit=$?"   # 期望 stdout="hi\n", exit=42
echo "$OUT" | grep -q "hi"    # stdout 有 "hi"
llvm-lit -v tests/lit/E2E/ 2>&1 | tail            # 全 PASS（含 syscall 测试）+ 不回归
python3 tools/run_differential.py 2>&1 | tail -3  # AGREE(4-way)=200 / DIVERGE=0
```

**验收强调（架构师会加做判别探针）**：
- **write 真输出**：`trap SYS_write` 把 "hi\n" 真写到 QEMU stdout（捕获比对，非只看退出码）；写不同字符串→stdout 不同（证真读 guest 内存、非写死）。
- **exit 真退出码**：`trap SYS_exit(42)` → QEMU exit=42（cfx_power，非 halt）。
- **返回值**：SYS_write 的 rd31 = 写出字节数（如 3）。
- **裸机 halt 不退步**：现有 halt-exit 程序仍正常（并存）。

## 参考指针
- ADR-0014（syscall 机制/ABI/cfx 落地）；ML-001a recon `docs/reviews/musl-recon-2026-07.md`（SEE §5 trap、cfx_uart=62、cfx_power=63、cfx_smon）
- wiki（pin 9f378f4）`~/DADAO-wiki` DADAO-12-SEE §5（trap→CFXTRAP 进入流程）、§cfx_uart、§cfx_power、§cfx_smon（cfxcode/寄存器，只读，§引用）
- QEMU：`.work/source/qemu/target/dadao/`：`translate.c`（decode，加 trap）、`cpu.c` `dadao_cpu_do_interrupt`（异常进入，扩 CFXTRAP→cfx_smon 路由）、`helper.c`（若 responder 用 helper）；exit 机制参 RASOF/RASUF（DL-057b `qemu_system_shutdown_request_with_code`）
- `tools/opcodes.yaml`（cfx 指令编码 ciii/crii）；`tests/scripts/`（asm 测试 + harness 扩 stdout 捕获）
- 后续：ML-002b（gem5 同款 syscall，双后端一致）；ML-003a（picolibc port，真 printf/malloc）

—— 自审纪律见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录区已预置占位必填；**subagent 必须真跑 syscall 测试看 stdout+退出码**，不是核代码就 Accepted——DL-064a/b 教训：产物存在≠能跑）。QEMU 改动同步 patch；测试禁 grep-only/`|| true`；write 真输出 + exit 真退出码判别必做。

---

## 审阅记录（subagent）

> **[架构师预置占位 · DS 必填]** DS 返回前必须开 subagent 代码级 review，逐条 finding + 处置表 + 判决写入此区。占位未替换=未自审=直接打回（不论对错、是否卡住）。**必须真跑 asm syscall 测试看 QEMU stdout="hi\n" + exit=42**（没真跑不能判 Accepted）。
> 特别核：trap cfx_smon 真触发 responder？write 真读 guest 内存写 stdout？exit 真退出码？裸机 halt 不退步？
