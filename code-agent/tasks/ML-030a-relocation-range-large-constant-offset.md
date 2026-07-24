# ML-030a：修复大常量折入地址/relocation 计算时的越界——gcc-c-torture P1 项

**执行环境**: 本地 subagent

**状态**: 待处理

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/llvm` 做 `git rebase`/`git am` 重放整条历史/`git reset --hard`。
  只允许在当前 HEAD 基础上新增普通 `git commit`。
- **本任务是诊断优先**：先定位到具体是哪个 CodeGen 阶段/哪条 DAG 合并规则把大常量
  折进了受限范围的 relocation/立即数字段，再判断修复范围。如果范围比预期大，允许
  停下如实报告，参照 `ML-020a`/`ML-021a`/`ML-024a`/`ML-027a` 的一贯先例。
- **完成后（若修复）立即导出 patch**（不要延后），追加进对应 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-026a`（`docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md` §4.2(b)）
gcc-c-torture 扫描发现两个具体、可复现的链接失败：

```
960321-1.c:
  ld.lld: error: relocation Unknown (4) out of range: -488278 is not in
  [-131072, 131071]; references 'a'
pr79286.c:
  ld.lld: error: relocation Unknown (4) out of range: 2343750000000010 is
  not in [-131072, 131071]; references section '.bss'
```

`960321-1.c` 的真实源码（架构师已核实，`ML-029a` 落地后重新扫描确认这两个
用例状态未变，仍然 FAIL_LINK，跟刚修复的帧偏移 bug 是不同的代码路径）：

```c
char a[10] = "deadbeef";
char acc_a(long i) { return a[i - 2000000000L]; }
main() {
  if (acc_a(2000000000L) != 'd') abort();
  exit(0);
}
```

`acc_a` 运行时实际访问的是 `a[0]`（`i=2000000000L` 时 `i-2000000000L=0`，
合法访问），但编译期 `a` 的基址 + 常量偏移 `-2000000000` 这个地址计算被
编码进了一个只有 18 位有效范围（`imms18`，`[-131072,131071]`，`contracts/
isa/spec.md` §2.2）的字段/relocation，本该改用寄存器算术（先把大常量物化到
寄存器，再和基址相加）而不是直接把常量塞进窄范围的 relocation addend。

这和刚刚由 `ML-029a` 修复的"栈帧偏移不做范围检查直接塞进 `imms12`"是**同一类
问题、不同的代码位置**——`ML-029a` 修的是 `DADAOFrameLowering`/
`DADAORegisterInfo::eliminateFrameIndex`（栈帧/局部变量地址计算），本任务要修的
是**全局变量/静态数据地址 + 大常量偏移**这条路径（很可能是 `DADAOISelLowering.cpp`
对 `GlobalAddress` 的自定义 lowering，或 DAG 合并把 `GlobalAddress + 大常量`
折成了 `rela`/`addi` 对时，`addi` 那步的 `imms18`/`imms12` 立即数没做范围检查——
具体是哪一步、哪个 relocation 类型，需要你自己诊断定位，不要凭空假设）。

## 目标

1. **定位具体的 CodeGen 路径**：编译 `960321-1.c`（或更简单的独立最小复现，
   比如 `char a[10]; char f(long i) { return a[i-2000000000L]; }`），用
   `llc -print-after-all` 或类似手段找到"大常量+全局地址"被折进受限范围
   relocation/立即数的具体 pass 和具体指令序列。核对相关 relocation 类型
   （`RELA`/`fixup_dadao_*` 之类，参照 `DADAOMCTargetDesc`/`DADAOAsmBackend`
   定义）的实际编码范围。
2. **判断修复方向**：可能是（a）DAG 合并阶段不应该把"全局地址 + 大常量偏移"
   折叠成一个单一的窄范围立即数操作，应该拆成"全局地址物化 + 大常量单独物化
   （参照 `ML-029a` 已经建立的 `materializeImm64`/`CONST_WYDE` 模式）+ 寄存器
   加法"；也可能是（b）某条具体指令的 lowering 本身缺少大立即数检查，类似
   `ML-029a` 修的 `eliminateFrameIndex` 那种模式。不要预设是哪一种，诊断后
   如实报告。
3. 如果根因和 `ML-029a` 高度同构（大立即数没做范围检查、需要物化+寄存器加法
   兜底），**直接复用 `ML-029a` 已经建立的物化模式**（`DADAOInstrInfo::
   materializeImm64`，`ML-029a` commit `245d4f42a5d8` 里新增，参照
   `DADAORegisterInfo.cpp` 里 `materializeFrameAddress` lambda 的写法），
   不要重新发明一套不同的物化机制。
4. 验证修复不局限于这两个 torture 用例——构造额外的判别性测试（不同大小的
   大常量偏移、正负都要覆盖），确认这是一个通用修复而不是只对这两个具体
   用例打补丁。

## 验收

- 报告具体的根因定位（是哪个 CodeGen 阶段/哪条 lowering 规则）。
- `960321-1.c`/`pr79286.c`：`tests/scripts/gcc_torture_sweep.py --filter
  "960321-1|pr79286"` 重跑，确认从 `FAIL_LINK` 变为 `PASS`（双后端，
  `pr79286.c` 注意其访问路径实际运行时不可达`while(a&&c++)`里`a`恒为0，
  但 `-O0` 仍需要为其生成代码——参照 `ML-026a` 报告原文，确认这一点后
  编译链接正常是本任务的成功标准，不要求这条不可达路径本身被执行到）。
- 新增判别性测试覆盖正负大常量偏移，双后端验证正确性。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（落地前重新跑一次记录当前值为准）。
- **全量 gcc-c-torture 重扫**（`tests/scripts/gcc_torture_sweep.py`，全量约16秒）：
  报告新的分布，和当前基线（`1412/113/133/50/0`）对比，确认零回归（无此前
  PASS 的用例变成非 PASS）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- LLVM 侧改动用**普通** `git commit` 落地，`git format-patch` 导出对应 patch，
  追加进 `series`；独立验证可在干净 pin-commit checkout 上 `git am` 成功。
- 若诊断后判断范围超出预期：在 `docs/issues.yaml` 登记新 issue，如实说明，
  不算任务失败。

## 参考指针

- `docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md` §4.2(b)（本任务对应
  的扫描发现原文）
- `docs/issues.yaml`/`docs/issues-archive.yaml` `frame-offset-no-imms12-range-
  check-silent-wraparound`（`ML-027a`/`ML-029a` 对同类问题在栈帧偏移路径上的
  完整诊断+修复记录，本任务的直接方法论参照——诊断方法、物化模式都应该借鉴）
- `llvm/lib/Target/DADAO/DADAOInstrInfo.cpp`（`ML-029a` 新增的
  `materializeImm64`，本任务如果根因同构应该直接复用）
- `llvm/lib/Target/DADAO/DADAOISelLowering.cpp`（`GlobalAddress`/常量折叠相关
  lowering，本任务大概率要改的地方，具体位置需要自己诊断确认）
- `llvm/lib/Target/DADAO/DADAOInstrInfo.td`（`RELA_RIII`/`ADDI_RBRRII` 等相关
  指令定义，`imms18`/`imms12` 立即数范围）
- `contracts/isa/spec.md` §2.2（立即数字段范围定义）
- `tests/scripts/gcc_torture_sweep.py`（`--filter` 可选受影响用例子集）
- `.work/source/llvm-test-suite/SingleSource/Regression/C/gcc-c-torture/execute/{960321-1,pr79286}.c`
  （原始复现源码）
