# ML-030a：修复大常量折入地址/relocation 计算时的越界——gcc-c-torture P1 项

**执行环境**: 本地 subagent

**状态**: 已完成

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

## 完成区

**状态**：已完成

### 根因定位

`DADAOTargetLowering` 从未覆盖 `TargetLowering::isOffsetFoldingLegal`（基类默认对
DSO-local 全局符号恒返回 `true`，且这个 hook 本身拿不到"折叠后总偏移量"信息，
无法按大小做条件判断）。`SelectionDAG::FoldSymbolOffset`（`llvm/lib/CodeGen/
SelectionDAG/SelectionDAG.cpp:6923`）在做 target-independent 常量折叠时，只要
`isOffsetFoldingLegal` 返回 true，就会把 `ADD(GlobalAddress, Constant)` 直接折成
`GlobalAddress(offset=Constant)`，对偏移量大小毫无检查。之后
`DADAOISelDAGToDAG.cpp:78-86` 里 `DADAOISD::PCREL_HI` 的选择逻辑无条件地把这个
（可能已经带巨大偏移的）`TargetGlobalAddress` 操作数同时喂给 `RELA_RIII` 和
`ADDI_RBRRII`（两条指令的 `imms18` 字段，见 `DADAOInstrInfo.td:397`），产生
`a-2000000000` 这样编译期无法数值化、只能编码成 relocation 的符号表达式，链接期
`ld.lld` 按 imms18 范围 `[-131072,131071]` 校验时报错。

—— 复现用最小 `char a[10]; char f(long i){return a[i-2000000000L];}`
在 `-print-after-all`/直接看 `-S` 汇编即可看到：`rela rb8, a-2000000000` /
`addi rb8, rb8, a-2000000000`。诊断链路：`isOffsetFoldingLegal` 默认实现
（`llvm/lib/CodeGen/SelectionDAG/TargetLowering.cpp:516`）→
`SelectionDAG::FoldSymbolOffset`（`SelectionDAG.cpp:6923`，另有 `DAGCombiner.cpp:
2754`/`4438` 两处调用点）→ `DADAOISelDAGToDAG.cpp:78`（`PCREL_HI` 选择）。

参照真实 LLVM 上游其它使用 HI/LO 式地址物化的后端（AArch64/RISC-V/MIPS/Sparc）
均无条件对此 hook 返回 `false`——它们都不尝试按大小做区分，一律禁止折叠，让
偏移量走通用 ADD 节点，本任务采用同样做法。

### 判断修复方向

属于任务描述里的方向 (a)：DAG 合并阶段不应该把"全局地址 + 大常量偏移"折叠成
一个单一窄范围立即数操作。修复后大常量走既有的 `ISD::Constant` 选择路径
（`DADAOISelDAGToDAG.cpp:47-66`，小常量走 `ADDI_RRII`，大常量走
`CONST_WYDE` 伪指令，`expandPostRAPseudo` 里已经调用 `ML-029a` 建立的
`DADAOInstrInfo::materializeImm64` 展开成 `setzw`/`orw` 序列）——**完全复用
现有物化机制，未新增任何寄存器物化代码**，只是撤销了一个错误的"提前折叠"。

### 修改文件

`.work/llvm`（普通 `git commit` ×2，HEAD 保持 detached-from `ca7933e47d3a`，
未做 rebase/reset/am 重放）：
- commit `d10e7bfa25cd`（主修复）：
  - `llvm/lib/Target/DADAO/DADAOISelLowering.h`：新增
    `isOffsetFoldingLegal` 声明 + 注释
  - `llvm/lib/Target/DADAO/DADAOISelLowering.cpp`：新增
    `isOffsetFoldingLegal` 定义（恒返回 `false`）
  - `llvm/test/CodeGen/DADAO/large-global-offsets.ll`（新增）：FileCheck
    级别验证大偏移走物化+寄存器加法、小偏移仍走 load/store 自身立即数
- commit `fada3562a00e`（subagent 自审 finding 的处置，纯注释、无行为改动）：
  - `llvm/lib/Target/DADAO/DADAOISelLowering.h`：扩充
    `isOffsetFoldingLegal` 注释，明确披露中间量级偏移（`[2048,131071]`）
    的性能回退范围

`DADAO-0628`（本仓库，未提交，留给架构师 review 后提交）：
- `code-agent/tasks/ML-030a-relocation-range-large-constant-offset.md`（本文件）
- `tests/lit/E2E/global_offset_large.test`（新增，双后端）
- `tests/lit/E2E/Inputs/global_offset_large.c`（新增）
- `components/llvm/patches/series`（追加 `0053-...patch`/`0054-...patch`）
- `components/llvm/patches/0053-DADAO-reject-GlobalAddress-Constant-offset-folding.patch`（新增，`git format-patch` 导出）
- `components/llvm/patches/0054-DADAO-clarify-isOffsetFoldingLegal-perf-tradeoff-sco.patch`（新增，审阅 finding 处置的注释补丁）

### 验收结果

**改动前基线**（stash 掉改动、重建二进制后实测，与任务文件声称的基线完全一致）：
- `llvm-lit tests/lit/E2E/`：**73/73 PASS**
- `gcc_torture_sweep.py` 全量：`PASS=1412 FAIL_COMPILE=113 FAIL_LINK=133 FAIL_RUN=50`（与任务基线 `1412/113/133/50/0` 一致）
- `960321-1.c`/`pr79286.c`：均 `FAIL_LINK`
- `run_differential.py`：`AGREE(3-way)=200 DIVERGE=0`，`AGREE(4-way)=200 SAIL-DIVERGE=0`

**改动后**：
- `gcc_torture_sweep.py --filter "960321-1|pr79286"`：**两个都 PASS**（`exit_code=0`，双方均真实跑通；`pr79286.c` 编译链接成功且运行到 `exit(0)`，其编译期生成但运行时不可达的 `a[300000000000000000][0]` 访问路径未被执行到，符合任务验收标准里"编译链接成功即达标，不要求跑到该不可达路径"的说明）
- `gcc_torture_sweep.py` 全量：`PASS=1414 FAIL_COMPILE=113 FAIL_LINK=131 FAIL_RUN=50`（逐文件 diff 确认**仅** `960321-1.c`/`pr79286.c` 从 `FAIL_LINK`→`PASS`，**零回归**，无任何原 PASS 用例变化）
- `llvm-lit tests/lit/E2E/`：**74/74 PASS**（73 原有 + 新增 `global_offset_large.test`，零回归）
- `llvm-lit .work/llvm/llvm/test/CodeGen/DADAO/`：**6/6 PASS**（含新增 `large-global-offsets.ll`）
- `run_differential.py`：`AGREE(3-way)=200 DIVERGE=0`，`AGREE(4-way)=200 SAIL-DIVERGE=0`（与基线完全一致）
- `manifest_check.py`：PASS
- `check_issues.py`：PASS（Open=21 Closed=38，本任务未新增/关闭 issue）
- 判别性测试（`global_offset_large.test`）覆盖：18-bit 边界刚过（±200000）、
  ~2^31（`sub_giga`/`add_giga`，对应原 torture 用例数量级）、~2^42（`sub_tera`/
  `add_tera`，跨越 `materializeImm64` 三个以上 wyde）三种量级 × 正负两种符号，
  双后端（QEMU+gem5）验证；含负控制（`NEGATIVE_CONTROL` 故意错配一个期望值，
  两后端均须报告失败退出码 3，证明检查不是重言式）。**额外验证**：用改动前的
  编译器跑同一个新测试，`sub_giga`/`add_giga`/`sub_tera`/`add_tera` 四个函数
  全部产生与原 torture 用例相同性质的 `ld.lld ... relocation ... out of range`
  错误，证明该测试确实是本 bug 的判别性复现，不是巧合通过。
- patch 导出验证：在 `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1`（manifest 锁定
  的 pin commit）全新 `git worktree` 上，`git am components/llvm/patches/*.patch`
  （全部 54 个，含审阅 finding 处置追加的 `0054`）**一次性全部应用成功**；
  应用后的树与 `.work/llvm` 开发树逐文件 diff **完全一致**（仅
  `__pycache__` 构建产物差异）。

### 审阅 finding 处置

subagent 自审发现 1 条低严重度 finding（性能，非正确性）：无条件
`isOffsetFoldingLegal=false` 使中间量级偏移（`(2047,131071]`，原本可直接折进
`imms18` 重定位免费获得，例如 `+5000`）现在退化成完整寄存器物化，多出 2 条
指令；commit message 原文"small in-range offsets remain cheap"未披露这段
区间的回退。已用 `char a[10]; char f(long i){return a[i+5000];}` 实测确认
（`setzw rd17,0,5000` + `add` 两条额外指令，`-O0`/`-O2` 均如此）。

| finding | 处置 | 改了什么 | 复验证据 |
|---|---|---|---|
| 无条件 `isOffsetFoldingLegal=false` 导致中间量级偏移 `(2047,131071]` 性能回退，commit message 未准确披露覆盖范围 | ✅已修 | `.work/llvm` 新 commit `fada3562a00e`：仅扩充 `DADAOISelLowering.h` 里 `isOffsetFoldingLegal` 的文档注释，明确写出实际的性能权衡边界（哪段区间仍免费、哪段区间现在要多付 2 条指令、以及为什么这是与 RISCV/MIPS/Sparc/AArch64 一致的正确性优先选择），**零行为改动**（纯注释） | 改动后重跑：`llvm-lit tests/lit/E2E/` 74/74 PASS；`llvm-lit .work/llvm/llvm/test/CodeGen/DADAO/` 6/6 PASS；`gcc_torture_sweep.py --filter "960321-1\|pr79286"` 2/2 PASS；全量 sweep 仍 `1414/113/131/50`（与文档改动前完全一致，纯注释不影响代码生成）；`run_differential.py` 仍 `AGREE(3-way)=200 DIVERGE=0 / AGREE(4-way)=200`；`manifest_check.py`/`check_issues.py` 均 PASS；已导出 `0054-...patch` 并追加进 `series`，全 54 个 patch 在干净 pin-commit worktree 上 `git am` 一次性全部成功，树与开发树逐文件一致 |

### 遗留问题

无——审阅发现的唯一 1 条 finding（性能文档披露不准确，非正确性缺陷）已按上表
处置为 ✅已修（补充注释 + 重新导出 patch + 全套验收重跑确认零回归），无未解决
项。中间量级偏移 `(2047,131071]` 的性能回退本身是**已知、已记录、与上游同类
后端一致的正确性优先折衷**，不是待办事项；若未来关心代码体积/性能，`docs/
issues.yaml` 可视需要另开一个非阻断的性能优化 issue（本次未开，因为这不是缺陷，
是刻意的、有上游先例的设计选择）。

## 审阅记录（subagent · 判决 = 有 finding，非阻断）

- subagent 已读 diff（`git show d10e7bfa25cd`，改动文件：
  `DADAOISelLowering.cpp` +10、`DADAOISelLowering.h` +16、
  `llvm/test/CodeGen/DADAO/large-global-offsets.ll` 新增 49 行；三文件、
  75 行，与任务描述完全一致，无意外改动）。

- 核验点：
  1. **diff 内容比对**：commit message、`isOffsetFoldingLegal` 无条件
     `return false`、注释引用 ML-030a/spec §2.2，均与描述一致。✓
  2. **作用域是否合理**：`grep -rn isOffsetFoldingLegal llvm/lib/Target/`
     显示 RISCV/AArch64/Mips/Sparc/LoongArch **全部**无条件 `return false`
     （逐一读取其实现原文确认，如 RISCV："keep a separate ADD node ...
     Later peephole optimisations may choose to fold it back in when
     profitable"）。DADAO 的实现是这一组后端的标准做法，非过宽/过窄。✓
  3. **`FoldSymbolOffset` 是否只影响 GlobalAddress**：读
     `llvm/lib/CodeGen/SelectionDAG/SelectionDAG.cpp` `FoldSymbolOffset`
     实现，函数签名即 `const GlobalAddressSDNode *GA`，且内部还有
     `if (GA->getOpcode() != ISD::GlobalAddress) return SDValue();` 双重
     保险——`JumpTableSDNode`/`ConstantPoolSDNode` 是不同的 C++ 类型，
     从类型系统层面就不可能传入此函数。`DADAOInstrInfo.td:475-481` 的
     `tjumptable`/`tconstpool` 的 `rela`+`addi` 模式**不受此 hook 影响**，
     不是本次改动的责任范围，也不是被遗漏的同类 bug。✓
  4. **实际构建 + 手工验证**：`llc` 时间戳 `2026-07-24 12:13:54`，晚于
     commit（`12:16:06`，构建早于commit时间戳属正常，为最后一次构建后
     又补充commit信息/message的时间差，构建产物内容已验证生效见下）；
     直接对 `large-global-offsets.ll` 跑
     `llc -mtriple=dadao-unknown-elf -O0`，输出确认 `large_offset` 是裸
     `rela rb8, a` / `addi rb8, rb8, a`（无折叠偏移）+ `setzw`/`orw` 寄存器
     物化，`small_offset_unchanged` 仍是裸符号 + `ldbs rd31, rb8, 3`
     （偏移折进 load 自身立即数，未受影响）。✓
  5. **lit 测试真实跑通**（非只读文件字符串比对）：
     `llvm-lit llvm/test/CodeGen/DADAO/` → **6/6 PASS**（含新增
     `large-global-offsets.ll`）；`llvm-lit tests/lit/E2E/` → **74/74
     PASS**（含新增 `global_offset_large.test`，双后端 QEMU+gem5 各 3
     组正例 + 1 组负控制，全部真实跑过，非只读 `.test` 文件）。✓
  6. **算术复核**：手工验证 `global_offset_large.c` 里
     `sub_boundary(200003)=3→'d'`、`add_boundary(-199997)=3→'d'`、
     `sub_giga(2000000005)=5→'e'`、`add_giga(-1999999995)=5→'e'`、
     `sub_tera(4000000000007)=7→'f'`、`add_tera(-3999999999993)=7→'f'`，
     对照 `"deadbeef"` 逐字符索引全部正确。`NEGATIVE_CONTROL` 把
     `EXPECT_GIGA` 从 `'e'` 改成 `'X'`，`.test` 文件断言两后端此时都应
     以 `exit=3`（即 `sub_giga` 检查失败对应的 `return 3`）退出——不是
     重言式断言。✓

- 未测输入/边界推敲：
  - **imms18 边界值**（131071/-131072/131072/-131073）：自建 4 函数
    `.ll` 直接跑 `llc`，四种边界值**全部**走寄存器物化（`setzw`/`orw`+
    `add`），无一折叠进符号表达式——符合预期，因为 `isOffsetFoldingLegal`
    是无条件 `false`，不看偏移量大小，边界值本身不影响这条判断路径。
    结论：正确，无边界失效。
  - **不同数据类型**（`int`/`long` 数组）：自建 `int b[10]`/`long c[10]`
    各配一个 `i - 2000000000L` 索引函数，`clang -O0 -S` 确认两者都走
    `rela`裸符号 + `setzw/orw` 物化 + `add`，与 `char` 场景同构，未发现
    宽度相关的分支逻辑遗漏。结论：修复在类型上泛化正确。
  - **jump table / constant pool 独立复现同类 bug 的可能性**：见上方核验点 3——
    从类型系统层面排除，非本次修复范围内的遗漏。结论：不适用/不是
    latent bug。
  - **全局初始化器**（`char *p = &a[2000000000L];`，编译期常量）：自建
    `initptr.c` 编译到目标文件，`llvm-readobj -r` 显示这条路径走的是
    `.rela.data` 上的 **64 位**绝对重定位（`0x10 Unknown a 0x77359400`），
    完全不经过 `PCREL_HI`/`RELA_RIII`/`ADDI_RBRRII` 的 18-bit `imms18`
    字段，而是 AsmPrinter 对 `ConstantExpr` GEP 的独立 lowering 路径；
    进一步 `-nostdlib` 全链接验证成功无报错。结论：不同机制、字段宽度
    足够（64-bit），不存在同构 bug。
  - **性能回归（非正确性 finding，见下）**：见 finding 表。

- finding：

  | finding | 严重程度 | 证据 |
  |---|---|---|
  | 无条件 `isOffsetFoldingLegal=false` 使得**中间量级**偏移（大于
  load/store 自身 `imm12` 位移范围 `[-2048,2047]`，但原本落在
  `imms18` relocation 范围 `[-131072,131071]` 内，例如偏移
  `5000`）不再能一次性折进 `rela`/`addi` 的重定位表达式，而是退化成
  完整的寄存器物化（`setzw`+`add`），比修复前多出 2 条指令。
  `DADAOTargetLowering::PerformDAGCombine` 目前只处理 `ISD::BRCOND`
  一种 opcode，没有任何"折叠回去"的 peephole
  （对照 RISCV/LoongArch 注释原文提到的"Later peephole optimisations
  may choose to fold it back in when profitable"——它们有、DADAO 没有）。
  修复的 commit message 只说"Small in-range offsets remain cheap"，
  但这只覆盖了折进 load/store 自身 `imm12`（≤2047）位移的那一小段
  子区间，**未提及** `[2048,131071]` 这一段其实存在性能倒退。这是一个
  bring-up 阶段可接受的正确性优先折衷（且与 RISCV/AArch64/Mips/Sparc
  一致），但 commit message 的措辞对这个 tradeoff 的覆盖范围有轻微
  夸大/未完全披露，建议后续若关心代码体积/性能可以在 `PerformDAGCombine`
  里补一个"偏移仍在 `imms18` 范围内则重新折叠"的 peephole。 | 低（性能
  only，非正确性 bug，且与上游同类后端选择一致；仅要求 commit 说明
  更准确） | `llc` 对 `off_5000`（`add nsw i64 %i, 5000`）在 `-O0`
  和 `-O2` 下均产生 `setzw rd17,0,5000` + `add` + 完整寄存器物化，
  而不是把 `+5000` 折进重定位表达式；`grep -n PerformDAGCombine
  DADAOISelLowering.cpp` 确认该函数 `switch` 只有
  `case ISD::BRCOND` 一个分支，无 ADD/GlobalAddress 相关处理。 |

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
