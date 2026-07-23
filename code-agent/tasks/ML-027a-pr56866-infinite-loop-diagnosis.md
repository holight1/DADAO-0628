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
