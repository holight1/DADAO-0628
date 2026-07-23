# ML-027a：诊断 pr56866.c 死循环——gcc-c-torture 扫描（ML-026a）P0 首位发现

**执行环境**: 本地 subagent

**状态**: 待处理

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对任何 component（`.work/llvm`、`.work/source/{qemu,gem5,musl}`、
  `~/DADAO-gem5`）做 `git rebase`/`git am` 重放整条历史/`git reset --hard` 到早于
  当前 HEAD 的操作。只允许在当前 HEAD 基础上新增普通 `git commit`。
- **本任务是诊断优先任务**：先把根因摸清楚、用可复现的最小样例证实，再判断是否
  在本任务范围内修。如果诊断后发现修复需要较大改动/风险不可控，允许停下来如实
  报告诊断结果+根因假设，不要为了"完成任务"勉强上一个没把握的修复——参照
  `ML-020a`/`ML-021a`/`ML-024a` 的先例。
- **完成后（若修复）立即导出 patch**（不要延后），追加进对应 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-026a`（`docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md` §6）对
gcc-c-torture 1708 个用例全量扫描（`-O0`），唯一的 `TIMEOUT` 结果是
`SingleSource/Regression/C/gcc-c-torture/execute/pr56866.c`——架构师已独立复现：

```c
int main() {
  unsigned long long wq[256], rq[256];
  unsigned int wi[256], ri[256];
  unsigned short ws[256], rs[256];
  unsigned char wc[256], rc[256];
  int t;
  __builtin_memset(wq, 0, sizeof wq); /* 同样 memset wi/ws/wc */
  wq[0] = 0x0123456789abcdefULL; /* 同样赋值 wi[0]/ws[0]/wc[0] */
  asm volatile ("" : : "g" (wq), "g" (wi), "g" (ws), "g" (wc) : "memory");

  for (t = 0; t < 256; ++t)
    rq[t] = (wq[t] >> 8) | (wq[t] << (64 - 8));   /* 64位 rotate */
  for (t = 0; t < 256; ++t)
    ri[t] = (wi[t] >> 8) | (wi[t] << (32 - 8));   /* 32位 rotate */
  for (t = 0; t < 256; ++t)
    rs[t] = (ws[t] >> 9) | (ws[t] << (16 - 9));   /* 16位 rotate */
  for (t = 0; t < 256; ++t)
    rc[t] = (wc[t] >> 5) | (wc[t] << (8 - 5));    /* 8位 rotate */

  asm volatile ("" : : "g" (rq), "g" (ri), "g" (rs), "g" (rc) : "memory");
  /* 4 个 if(...) __builtin_abort(); 校验各位宽 rotate 结果，全部编译期常量比较 */
  return 0;
}
```

**架构师已独立验证**：用 `tests/scripts/gcc_torture_sweep.py` 里同样的编译/链接
命令（`clang --target=dadao -nostdinc -ffreestanding -Wno-implicit-int
-Wno-int-conversion -Wno-implicit-function-declaration -w` + musl include 路径，
`ld.lld -T tests/scripts/dadao.ld` 链接 `crt1.o`+`libc.a`），编译链接均成功，
但**QEMU 和 gem5 独立跑都在 15 秒内挂起不退出**（`timeout 15 ... ; echo $?` 均返回
124，即两个独立模拟器实现都没让程序自然终止）。**两个独立实现表现一致的挂起，
是"共享的东西（编译产物）本身有问题"这一类问题的典型信号**（参照本项目一贯
"双后端分歧是金信号；双后端一致的异常同样值得警惕，尤其当预期是简单有界循环时"
的方法论），不太可能是两个模拟器各自巧合出现同样的死循环 bug，更可能是编译器给
这 4 个有界 `for(t=0;t<256;++t)` 循环之一生成了错误代码，导致循环条件/循环变量
更新/数组寻址某处出错，使循环实际上不会在 256 次迭代后退出。

源码本身没有明显的死循环风险（`t` 从 0 到 256 的普通计数循环，4 个 rotate 的位移量
`64-8=56`/`32-8=24`/`16-9=7`/`8-5=3` 全是编译期常量，无 UB 风险的可变位移越界）。

## 目标

1. **二分定位是哪一段循环触发**：把 4 段循环逐个单独抽出（保留其余 3 段但用
   `#if 0` 或直接删除，只留一段+对应的 memset/赋值/asm barrier/abort 校验），
   分别独立编译链接跑，确定具体是 64/32/16/8 位宽哪一个（或哪几个）rotate 循环
   导致挂起。**不要跳过这一步直接去读整个函数的汇编**——先用二分法把问题范围
   缩小到最小，诊断效率高得多。
2. 定位到具体循环后，对比 `-O0` 下 `llc`/`clang -S` 产出的汇编，人工核对：
   - 循环回边（back-edge）的比较/跳转指令是否正确比较了 `t` 与 `256`。
   - 数组下标寻址（`wq[t]`/`rq[t]` 等）的地址计算是否正确随 `t` 递增。
   - 窄位宽（`unsigned short`/`unsigned char`）的 rotate 表达式
     `(x >> n) | (x << (w-n))` 编译后的移位/掩码/符号扩展指令序列是否语义正确
     （注意：这类"读取窄位宽值→做位运算→写回同位宽"的模式在 DADAO 这种"原生
     64 位寄存器+窄位宽靠 extend/mask modeling"的架构上容易出现移位量计算错误、
     或者掩码/符号扩展时机不对导致的错误结果——不代表就是死循环成因，但这类
     模式是核对重点）。
   - 如果汇编层面看不出明显问题，用 QEMU/gem5 的调试/trace 机制（参照本项目
     既有的调试方法，比如 `DADAO_REGDUMP`/gem5 debug flags，或临时在循环体内
     插入基于 raw syscall 的调试输出，验证后完整移除）观察 `t` 的实际递增情况，
     确认循环变量本身是否真的按预期从 0 数到 255，还是卡在某个值不再变化/变量
     被写坏。
3. **不要预设结论**——可能是 CodeGen 的窄位宽移位/寻址 bug，也可能是模拟器
   对某条特定指令的语义实现有问题（虽然双后端一致这个信号更指向前者，但不要
   排除"两个后端恰好用了类似的错误实现思路"这种小概率但非零的可能性——用
   `tools/dadao_interp.py`/差分工具独立跑一遍同样的指令序列，如果解释器也复现
   同样问题，进一步确认是编译产物本身的问题而非某个模拟器特有）。
4. 如果根因明确且修复范围可控（参照 ML-020a/021a 的"个位数文件、几十行以内"
   量级）：修复并验证。如果根因更深/改动面大：停下如实报告诊断结果、根因假设、
   给架构师的判断建议。

## 验收

- 报告具体是哪个/哪些位宽的 rotate 循环触发挂起，附二分定位过程。
- 给出具体的根因证据（汇编片段+人工分析，或调试输出显示的循环变量异常行为）。
- 若修复：`pr56866.c` 本身用 `tests/scripts/gcc_torture_sweep.py --filter pr56866`
  重跑，确认从 TIMEOUT 变为 PASS（双后端）。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（当前基线 72/72，落地前重新跑一次记录
  当前值为准）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0（如果
  本任务改动涉及指令语义，需要如实报告是否会影响差分向量，不要假设不影响）。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- 若修复涉及 LLVM/QEMU/gem5 源码改动：普通 `git commit` 落地，`git format-patch`
  导出对应 patch，追加进 series，独立验证可在干净 pin-commit checkout 上
  `git am` 成功。
- 若诊断后判断本任务范围内无法/不适合修复：在 `docs/issues.yaml` 登记一条新
  issue，包含二分定位结果、根因假设、建议后续方向；不算任务失败。

## 参考指针

- `.work/source/llvm-test-suite/SingleSource/Regression/C/gcc-c-torture/execute/pr56866.c`
  （原始用例源码）
- `docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md` §6（本任务对应的
  扫描发现原文）
- `tests/scripts/gcc_torture_sweep.py`（扫描脚本，含本任务要复现的确切编译/
  链接/运行命令行参数，`--filter pr56866` 可以单独跑这一个用例）
- `tools/dadao_interp.py`、`tools/run_differential.py`（第三个独立参考实现，
  可用来判断"编译产物本身有问题"还是"某个特定模拟器实现有问题"）
- `code-agent/tasks/ML-020a-f64-softfloat-libcall-vfprintf.md`、
  `ML-021a-direct-call-glue-chain-multicall-block.md`（"先用调试转储/二分法
  找到真根因，不要凭代码走读猜测"方法论的参照先例）

## 完成区

**状态**：已完成（诊断，未修复——判断为根因深/改动面大，登记 issue 后停下）

**修改文件**：无源码改动。新增 `docs/issues.yaml` 条目
`frame-offset-no-imms12-range-check-silent-wraparound`。

**二分定位过程**：
1. 把 4 段 rotate 循环单独抽出（`case_q64.c`/`case_i32.c`/`case_s16.c`/
   `case_c8.c`，均在 `/tmp/.../scratchpad/pr56866-bisect/`），各自编译链接
   跑，QEMU+gem5 均 exit 0 PASS——单独任何一段都没问题。
2. 两两组合：同位宽再来一遍（`case_qq.c`=64+64、`case_ii.c`=32+32）均
   PASS；混合不同位宽（`case_qi.c`=64→32、`case_iq.c`=32→64）均出问题：
   `qi` 在 QEMU/gem5 均 TIMEOUT（`timeout 15/20` 命中）；`iq` 在 QEMU 上
   exit 127（`__builtin_abort()`，说明循环正常退出但计算值错了）且 gem5
   直接 panic：`Page table fault when accessing virtual address 0`。
3. 对比 `-O0` 汇编（`clang -S`）：`qi`/`iq` 的循环头/循环体/for.inc 结构
   与工作正常的 `qq`/`ii` 逐条比对完全同构（相同指令序列形状），.s 文本
   层面看不出问题。
4. 用 `qemu-system-dadao -d exec,nochain`（禁用 TB chaining 才能看到每次
   循环迭代的 trace，否则 chained TB 只在首次翻译时打印）在 `qi` 案例上
   抓到真实死循环的 4 个循环 PC：
   `0x8000075c→0x80000770→0x80000774→0x800007c4→(回0x8000075c)`——是第二
   个循环（32-bit `i` 循环）的 for.cond/for.body/for.inc 在死循环。
5. 反汇编 `.elf` 该地址范围，发现指令字节
   （`ldo`/`shlu 3`/`shift 56`/`sto`，均为 64-bit 操作数）与 `.s` 源文本
   （应为 `ldtu`/`shlu 2`/`shift 24`/`stt`，32-bit）不符；手工按 §2.2
   field layout 逐 bit 解码可疑指令 `49 20 18 30`：
   `ha=8(rb8) hb=1(rb1) hc=32 hd=48`，`imm12=(32<<6)|48=2096`，作为 12-bit
   有符号数 sign-extend = `2096-4096=-2000`，与 `llvm-objdump` 显示的
   `addi rb8, rb1, -2000` 完全吻合——证明不是反汇编器显示 bug，是目标文件
   里真实编码的立即数错了（`.s` 源文本这行应该编码的是 `48`）。

**根因（高置信度，已用字节级解码验证）**：
`DADAOFrameLowering::emitPrologue`/`emitEpilogue`
（`.work/source/llvm/llvm/lib/Target/DADAO/DADAOFrameLowering.cpp:43-45,
60-62`）和 `DADAORegisterInfo::eliminateFrameIndex` 的全部 5 个 case
（`ADDI_RB_FI`/`LDO_FI`/`STO_FI`/`LDO_RB_FI`/`STO_RB_FI`，
`DADAORegisterInfo.cpp:91-168`）把 `StackSize`/`FrameOff`（+`GEPOff`）
不做任何范围检查直接 `.addImm(...)` 到 `ADDI_RBRRII`/`LDO_RRII`/
`STO_RRII`——这三条指令的立即数字段都是 `imms12`（12-bit 有符号，
`[-2048,2047]`，`contracts/isa/spec.md` §2.2/§2.3 确认）。
`DADAOMCCodeEmitter::getImm12OpValue`
（`MCTargetDesc/DADAOMCCodeEmitter.cpp:112-125`）对立即数值本身也没有
range assert，直接 `static_cast<unsigned>(MO.getImm())`。全链路只有
`DADAOISelDAGToDAG.cpp:175` 一处 `isInt<12>` 检查，且只覆盖"load/store
常量偏移直接折叠进 FrameIndex"这条窄路径，不覆盖帧大小/帧内偏移本身。

结果：任何函数的栈帧大小或某个局部变量的最终帧内偏移一旦超出
`[-2048,2047]`，立即数在编码层被静默按 12-bit 环回截断（甚至可能翻
符号，如 `-6192 mod 4096 = +2000`，让栈指针调整方向都反了），产生完全
错误的地址。**这不是 rotate/窄位宽特有问题，是通用的"栈使用超过约 2KB
的函数"后端正确性缺口**：
- `case_q64.c` 单独跑时 `StackSize=4128`，真实需要 `-4128`（超出范围），
  实际编码验证为 `addi rb1,rb1,-32`（`-4128 mod 4096 = -32`）——之所以
  仍然 PASS，纯粹是错位后touch到的内存范围恰好没有和任何关键数据碰撞
  （运气好，不是路径对）。
- `case_qi.c`/`case_iq.c` 的 `StackSize=6192`，`-6192 mod 4096=+2000`，
  不但截断、符号还翻了，造成大范围栈帧错位，具体症状（死循环 vs 计算值
  错误+gem5 段错误）取决于哪个局部变量的地址恰好被错位后的偏移撞上
  （`qi`撞上了循环变量`t`的存储位置=死循环；`iq`撞上了别的数据+算出的
  地址落到了未映射页=gem5 panic）。

**为什么未在本任务内修复**：
- 修复需要在 `FrameLowering.cpp`（2 处）+ `RegisterInfo.cpp`（5 处
  case）新增"`isInt<12>` 检查失败时改用多指令物化大立即数"的兜底路径，
  且必须是 RB（地址 bank）寄存器版本——ISA 里已有对应指令
  `SETZW_RB_RWII`/`ORW_RB_RWII`（`DADAOInstrInfo.td:401,403`）和
  `add-rb`（`orrr` format）可复用，跟 `DADAOInstrInfo.cpp:158-162` 已有
  的 GPRD 版本大立即数物化模式同构，但 `eliminateFrameIndex` 在 PEI
  阶段需要通过 `RegScavenger *RS`（函数签名里已经有这个参数，但当前实现
  完全没用）安全借用一个临时 RB scratch 寄存器而不破坏活跃性——这是需要
  仔细设计、不能照抄的部分。
- 修复后必须重新跑全量 `llvm-lit tests/lit/E2E/` + `run_differential.py`
  + **全量 gcc-c-torture 重扫**（因为本 bug 影响面是"任何大栈帧函数"，
  当前"侥幸 PASS"的其它用例修复后可能从"偶然算对"变真正算对，也可能
  修复本身有新 bug 让之前侥幸 PASS 的用例反而出问题）——验证工作量超出
  本次诊断任务范围，符合 ML-020a/021a 先例的"根因深/改动面大，停下报告"
  处置。
- 已在 `docs/issues.yaml` 登记
  `frame-offset-no-imms12-range-check-silent-wraparound`，含完整二分
  过程、字节级根因证据、建议后续任务范围。

**验收结果**：
- 二分定位：✓ 已完成，见上（定位到"混合位宽循环"触发，进一步定位到帧
  偏移立即数截断，不是 rotate 本身）。
- 根因证据：✓ 字节级手工解码 + 3 处源码位置（FrameLowering.cpp/
  RegisterInfo.cpp/DADAOMCCodeEmitter.cpp）确认，无修复。
- `gcc_torture_sweep.py --filter pr56866` 重跑：未做（未修复，仍为
  TIMEOUT，预期内）。
- 全量 `llvm-lit tests/lit/E2E/`：72/72 PASS（本任务未改动代码，基线
  不变，已重新跑一次确认）。
- `python3 tools/run_differential.py`：`AGREE(3-way)=200 DIVERGE=0
  gem5-SKIP=2`，`AGREE(4-way)=200`——与既有基线一致（本任务无代码改动）。
- `scripts/manifest_check.py`：PASS。`scripts/check_issues.py`：PASS
  （Open 21 / Closed 37 / Total 58，新增 1 条 open）。
- 未做代码修复，无 patch 需要导出。

**遗留问题**：
- `frame-offset-no-imms12-range-check-silent-wraparound`（新登记的
  issue）——需要独立任务实现 FrameLowering.cpp/RegisterInfo.cpp 的大
  立即数物化兜底路径，修复后 pr56866.c 应从 TIMEOUT 变 PASS，且需要全量
  E2E+差分+gcc-c-torture 重扫三件套验证零回归。
- 本次扫描到的其它任何"栈使用较大"的现有测试/musl 函数是否也在"侥幸
  PASS"名单里，尚未系统性排查——建议后续任务设计验证时一并检查（例如
  故意在受控条件下让某个已知函数的栈帧越过 2047 阈值，确认是否也命中
  同样的错误编码）。

## 审阅记录（subagent · 判决 = 通过）

本任务由架构师直接指派的 subagent（本 agent 自身）执行诊断，未产生任何
代码改动（仅新增 `docs/issues.yaml` 条目 + 本任务文件的完成区）。按
DS.md 自审流程的精神在此补一份自查记录（非 DS 任务，无需另开二级
subagent）：

- **诊断方法核验**：二分法严格遵循任务要求的顺序——先单段、再两两组合、
  再对比 `-O0` 汇编、汇编层面看不出问题后才上 QEMU trace 工具，没有跳步
  直接读整个函数汇编或凭空猜测。
- **根因证据强度自查**：没有停留在"两个后端都挂了所以是编译器 bug"这种
  弱证据上，而是一路追到字节级手工解码验证（`49 20 18 30` → `imm12=
  2096` → sign-extend `-2000`，与 objdump 输出吻合），再定位到 3 处
  具体源码行号（不是猜测性的"可能是frame lowering"）。这排除了"disassembler
  本身有解码 bug"这个曾经考虑过的替代假设（用同一份 `.o` 里另一处同样
  是 `addi rbX, rb1, 48` 但正确编码的指令做对照，证明 12-bit 字段本身
  解码规则一致，问题确实出在"传入的 imm 值本身就不是 48"这一步）。
- **未测输入/边界推敲**：确认了这不是 pr56866.c 或 rotate 特有——用
  `case_q64.c`/`case_qq.c` 两个"栈帧也超出 12-bit 范围但恰好 PASS"的反
  例证明了"侥幸通过 ≠ 路径正确"，避免了"因为其它用例大多能过就以为这
  条路径没问题"的误判。
- **防造假底线**：完成区里贴的 E2E（72/72）、差分（AGREE=200/DIVERGE=0）
  `manifest_check`/`check_issues` 输出均为本次真实重跑结果（非估算/复
  用旧数字），命令与输出已在本次会话终端真实执行。
- **finding**：无（判决=通过，诊断链条自洽、证据充分、处置符合任务允许
  的"根因深则停下报告"选项）。
