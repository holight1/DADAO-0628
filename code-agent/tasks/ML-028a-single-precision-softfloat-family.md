# ML-028a：补齐单精度软浮点符号家族——gcc-c-torture 扫描（ML-026a）杠杆最大的发现

**执行环境**: 本地 subagent

**状态**: 已完成

## 硬约束（务必遵守，违反视为任务失败）

- **禁止**对 `.work/source/musl` 做 `git rebase`/`git am` 重放整条历史/
  `git reset --hard`。只允许在当前 HEAD 基础上新增普通 `git commit`。
- 本任务**只写 musl 侧的软浮点符号实现**，不改 LLVM、不接入 compiler-rt 组件——
  延续 `ML-022a`/`ML-025a` 已经走通的路线，追加到同一个
  `.work/source/musl/src/internal/dadao/softfloat_shim.c` 文件，同一套方法论
  （自包含实现、不引入 compiler-rt 的 `int_lib.h`/`fp_lib.h` 基础设施、只用位模式
  整数运算避免自递归 libcall、fuzz 对拍原生硬件运算、注意 `-fno-optimize-sibling-
  calls` 尾调用陷阱）。
- **完成后立即导出 patch**（不要延后）：`components/musl/patches/0013-...patch`，
  追加进 `series`。
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-026a`（`docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md` §4.2(a)）
gcc-c-torture 扫描发现：92 个 FAIL_LINK 文件（占全部 FAIL_LINK 的 42%，是本次扫描
单一影响面最大的可行动发现）全部卡在同一批未定义符号上——`ML-022a` 当时只做了
IEEE-754 **双精度**软浮点 shim 的一部分（`__adddf3`/`__subdf3`/`__muldf3`/
`__nedf2`/`__eqdf2`/`__unorddf2`/`__fixdfdi`/`__fixunsdfdi`/`__floatsidf`/
`__floatunsidf`），**单精度（`sf`）家族几乎完全没做**，双精度的**有序比较**
（`__gedf2` 已在 `ML-025a` 补上，但 `__gtdf2`/`__ltdf2`/`__ledf2` 仍缺）也没补齐。

实测缺失符号集合（92 个文件的未定义符号并集）：

```
__addsf3, __subsf3, __divsf3,
__eqsf2, __nesf2, __gesf2, __gtsf2, __lesf2, __ltsf2,
__fixsfdi, __fixunssfdi,
__floatdidf, __floatundidf, __floatundisf, __floatunsisf,
__gtdf2, __ltdf2, __ledf2,
__divsc3
```

（`__floatunsidf` 已在 `ML-022a` 实现，报告里重复列出是统计口径问题，不是真的缺）。

**`__alloca`（6 个文件）不在本任务范围**——那是 `-ffreestanding` 关闭了 clang 对
`alloca()` 的 builtin 识别（退化成对外部符号的真实调用），根因和本项目 P2 清单里
"VLA `dynamic_stackalloc`/`stackrestore` ISel 未实现"是**同一个底层缺口**（`alloca`
和 VLA 编译期都会走 `ISD::DYNAMIC_STACKALLOC`），跟软浮点符号完全是两码事，不要
在本任务里顺手处理。

## 目标

1. 在 `softfloat_shim.c` 追加以下符号（沿用 `ML-022a`/`ML-025a` 已经建立的
   `rep_t`/`toRep`/`fromRep` 风格，单精度用 32 位 `uint32_t` 位模式，参照现有
   `__floatsidf`/`__muldf3` 等双精度实现改写成单精度版本）：
   - `__addsf3`/`__subsf3`/`__divsf3`：`float` 加/减/除。
   - `__eqsf2`/`__nesf2`/`__gesf2`/`__gtsf2`/`__lesf2`/`__ltsf2`：`float` 比较家族
     （参照 `ML-025a` 已经实现 `__gedf2` 时确认过的 GNU/libgcc 返回值约定——
     `eq`/`ne` 是"返回0表示相等"，`ge`/`gt`/`le`/`lt` 是"返回值符号表示大小关系"，
     两组约定不同，注意区分，不要对单精度想当然复用错误的约定）。
   - `__fixsfdi`/`__fixunssfdi`：`float` → `int64_t`/`uint64_t`。
   - `__floatdidf`/`__floatundidf`：`int64_t`/`uint64_t` → `double`（注意这两个
     虽然名字有 `di`，但目标类型是 **double**，不是 float——之前 ML-022a 只做了
     `__floatsidf`/`__floatunsidf`，是 **32位整数**→double，这次是 **64位整数**
     →double，进制/尾数处理逻辑不同，不要直接照抄）。
   - `__floatundisf`/`__floatunsisf`：`uint64_t`/`uint32_t` → `float`。
   - `__gtdf2`/`__ltdf2`/`__ledf2`：补齐双精度有序比较家族剩余的 3 个（`__gedf2`
     已存在，可以直接参考其实现改写）。
2. `__divsc3`（单精度复数除法，C99 Annex G 复数除法算法）**视复杂度自行判断是否
   纳入本任务**：如果这 92 个文件里实际用到 `__divsc3` 的只有个位数（大概率是
   `complex-*.c`/`ieee/` 目录下的少数几个复数运算测试），且实现复杂度明显超出
   其它符号（需要额外处理复数除法的数值稳定性算法，不是简单的位模式运算），
   允许作为独立后续任务留待以后处理，在完成区如实说明涉及的具体文件数和你的
   判断依据，不要因为这一个符号卡住整个任务。
3. **自递归陷阱核查**（同 `ML-022a`/`ML-025a` 强调过的坑）：反汇编全文核查
   （不是只看 `nm -u`），确认新增的这批函数内部绝不能对 `float`/`double` 操作数
   使用原生 `+ - * / == != < >` 运算符，没有任何自递归/间接递归调用。
4. Fuzz 测试对拍原生硬件运算（参照 `ML-022a`/`ML-025a` 的方法论，改名避免与
   libgcc 符号冲突，覆盖边界值：±0、次正规数、`FLT_MAX`/`FLT_MIN`、±inf、NaN、
   `INT64_MIN`/`INT64_MAX`/`UINT64_MAX` 等），并构造真实负控制（故意改错一处
   实现细节，确认 fuzz 工具真的会抓到，不是形同虚设）。

## 验收

- 用 `tests/scripts/gcc_torture_sweep.py --filter <受影响文件的正则>` （或直接
  重跑全量，1708 个用例只需约 16 秒）验证：92 个受影响文件里，之前因为这批符号
  缺失而 FAIL_LINK 的用例现在应该都能过链接（**不要求全部变成 PASS**——报告里
  已经说明部分文件还需要 `-lm` 数学库函数或有其它独立问题，本任务只对"因为软
  浮点符号缺失而链接失败"这个具体原因负责，如实报告链接通过后这些文件各自的
  实际运行结果，不要夸大成"92个全部PASS"）。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（当前基线 72/72，落地前重新跑一次记录
  当前值为准）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- musl 侧改动用**普通** `git commit` 落地，`git format-patch` 导出为
  `components/musl/patches/0013-....patch`，追加进 `series`；独立验证可在干净
  pin-commit checkout 上 `git am` 成功。
- 重新跑一次 gcc-c-torture 全量扫描（`tests/scripts/gcc_torture_sweep.py`），
  报告新的 PASS/FAIL_COMPILE/FAIL_LINK/FAIL_RUN/TIMEOUT 分布，和 `ML-026a`
  的基线（1328/113/217/49/1）对比，说明具体提升了多少、还剩多少与本任务无关
  的失败。
- 若 `__divsc3` 被判断为超出本任务范围：在 `docs/issues.yaml` 登记一条新 issue，
  说明涉及文件数和复杂度评估，不算任务失败。

## 参考指针

- `docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md` §4.2(a)（本任务对应的
  扫描发现原文，含完整的92个受影响文件清单）
- `.work/source/musl/src/internal/dadao/softfloat_shim.c`（`ML-022a`/`ML-025a`
  已实现的16个符号，本任务追加函数到同一文件，同一方法论）
- `code-agent/tasks/ML-022a-softfloat-shim-vfprintf-link.md`、
  `code-agent/tasks/ML-025a-scanf-softfloat-symbols.md` 完成区（完整的方法论
  范式：fuzz测试、负控制、反汇编核查自递归、`-fno-optimize-sibling-calls`、
  GNU比较返回值约定的两种不同约定）
- `.work/source/llvm/compiler-rt/lib/builtins/{addsf3,subsf3,divsf3,comparesf2,
  fixsfdi,fixunssfdi,floatdidf,floatundidf,floatundisf,floatunsisf,
  comparedf2}.c`（算法参考，不是要移植的对象）
- `tests/scripts/gcc_torture_sweep.py`（`--filter` 参数可以只跑受影响的子集，
  全量约16秒也可以直接跑）
- `.work/build/musl/lib/{crt1.o,libc.a}`（`make build-musl` 重新生成）

## 完成区

**状态**：已完成

**修改文件**：
- `.work/source/musl/src/internal/dadao/softfloat_shim.c`（追加 20 个符号，
  普通 `git commit` 落地在 `.work/source/musl` 仓库，commit `f6ba5f43`，
  parent `0b28784a`）
- `components/musl/patches/0013-dadao-add-single-precision-softfloat-family-double-o.patch`（新增，`git format-patch` 导出）
- `components/musl/patches/series`（追加一行）
- `docs/issues.yaml`（新增 1 条 open issue：
  `musl-softfloat-shim-missing-divsc3`）
- `code-agent/tasks/ML-028a-single-precision-softfloat-family.md`（本文件，
  状态/完成区/审阅记录）

**实现的符号（20 个，追加到 ML-022a/ML-025a 已建立的同一文件、同一自包含
位模式运算风格）**：
- `__addsf3`/`__subsf3`/`__divsf3`：float 加/减/除（`__subsf3` 沿用
  `__subdf3` 的"翻转符号位再调用加法"模式，同样依赖 tree-wide
  `-fno-optimize-sibling-calls`）。
- `__eqsf2`/`__nesf2`：float 相等/不等比较（"0 表示相等"约定，共享
  `cmp_nonequal_f32` 辅助函数）。
- `__gesf2`/`__gtsf2`/`__lesf2`/`__ltsf2`：float 有序比较家族（"-1/0/+1
  表示大小，符号即结果"约定；`ge`/`gt` 对 NaN 返回 -1，`le`/`lt` 返回
  +1，共享新的 `cmp_ordered_sf` 辅助函数）。
- `__gtdf2`/`__ltdf2`/`__ledf2`：补齐 double 有序比较家族剩余 3 个
  （`__gedf2` 是 ML-025a 已有实现，完全未改动；新 3 个共享新的
  `cmp_ordered_df` 辅助函数，与 `__gedf2` 行为等价但不共享代码，避免
  改动已验证过的既有函数）。
- `__fixsfdi`/`__fixunssfdi`：float → int64_t/uint64_t。
- `__floatdidf`/`__floatundidf`：int64_t/uint64_t → double（非 ML-022a
  已有的 32 位整数→double，此处输入可达 64 位，需要真正的
  guard/round/sticky 舍入）。
- `__floatundisf`/`__floatunsisf`/`__floatdisf`：uint64_t/uint32_t/
  int64_t → float。

**`__divsc3`（单精度复数除法）处置决定**：**判断为超出本任务范围，已登记
`docs/issues.yaml` `musl-softfloat-shim-missing-divsc3`**。独立 grep +
探针编译核实：92 个受影响文件里实际引用 `__divsc3` 的只有 **1 个**
（`complex-5.c`：`y = p(x, 1.0f / z)`，`z` 是 `float __complex__`，"实数
除以复数"触发 C99 复数除法；`complex-6.c`/`complex-7.c` 分别只用到取共轭/
构造和 `!=` 比较，均不需要 `__divsc3`——已独立编译验证二者在补齐本任务
其余符号后转 PASS）。`__divsc3` 的算法（Smith's method：`logb`/`scalbn`
重新定标 + C99 Annex G 对 NaN/inf/0 组合的多路特判，参照
`.work/source/llvm/compiler-rt/lib/builtins/divsc3.c`）在复杂度上明显
超出本文件其余全部符号（均为闭式位模式运算，无需额外的超越函数层或
多步骤特判表），按任务书应急条款独立登记，不阻塞本次 81/92 收尾。

**验收结果（真实输出，非估算）**：

1. **独立标准编译 + 反汇编 + undefined symbol 核查**：`clang --target=dadao
   -ffreestanding -O2 -fno-optimize-sibling-calls -c softfloat_shim.c`
   编译干净（exit 0）；`llvm-nm -u`：**0 个未定义符号**，36 个 `T`
   符号（既有 16 + 新增 20）；`llvm-objdump -dr --triple=dadao` 反汇编
   全文件只有 **2 处 `call` 指令**：既有的
   `__subdf3`→`__adddf3`（地址 0x5e8）+ 新增的
   `__subsf3`→`__addsf3`（地址 0x30a0）——本任务新增的其余 19 个函数
   **零** `call` 指令，排除任何自递归/间接递归。
2. **Fuzz 对拍原生硬件运算（本任务自建 harness，改名 `my___*` 避免与
   libgcc 符号冲突）**：边界值（±0、次正规数、`FLT_MAX`/`FLT_MIN`、
   ±inf、NaN、`INT64_MIN`/`INT64_MAX`/`UINT64_MAX`、2^52/2^53/2^23/
   2^24 舍入边界）交叉积 + 随机向量（float 算术/比较各 40 万次、
   int64↔double 各 30 万次、uint32/uint64→float 各 20-30 万次、
   double 有序比较 30 万次），**共 4,871,106 次检查，0 处不一致**。
3. **5 个独立负控制**（证明 fuzz 工具真的会抓错，非形同虚设）：
   `__gtsf2` unordered 符号 -1→1（抓到 84 处不一致）、`__divsf3` 长除法
   迭代次数 `F32_SIG_BITS+4`→`+2`（抓到 313630 处）、`__floatdidf` 窗口
   常量 `significandBits+3`→`significandBits-2`（抓到 300017 处）、
   `__floatdisf` 零值分支故意返回非零（抓到 1 处）、`__unordsf2`
   比较运算符 `>`→`>=`（抓到 76 处）——全部**立即被抓到**，fuzz harness
   非摆设。
4. **`__fixsfdi`/`__fixunssfdi` 已知边界局限核实为继承性质、非新增
   回归**：独立复现确认既有（ML-022a 已验证过）`__fixdfdi` 在量级
   `[2^63,2^64)` 的边界上同样不做理想饱和（`__fixdfdi(2^63)` 返回
   `-9223372036854775808` 而非饱和到 `INT64_MAX`）——这是继承自
   compiler-rt 自身 `fp_fixint_impl.inc` 的 `(unsigned)exponent>=64`
   判断结构（该量级恰好 exponent==63，判断不触发），本任务新增的
   `__fixsfdi` 在类比边界复现**完全相同**的行为类别（同一根因，非新
   增/不同的缺陷）；`__fixunssfdi`（无符号）因无符号->有符号重解释
   步骤，独立跑 20 万个落在 `[2^63,2^64)` 的构造向量确认**无此局限**
   （0 处不一致）。fuzz harness 对此边界的"预期值"模型也相应调整为
   只断言无歧义区间（`< 2^63` 精确值 / `>= 2^64` 饱和），不对该
   C-标准-UB 相邻的窄区间做强断言。
5. **`make build-musl` 全量重建**（`rm -rf obj lib/libc.a lib/crt1.o`
   后重跑）：`libc.a` 打包 **1337** 个对象（与 ML-022a/ML-025a 基线
   完全一致——只追加函数到既有文件，未新增源文件），失败对象仍是同一批
   **10 个**已知失败（`daemon.o`/`dcngettext.o`/`res_msend.o`/
   `exec{le,l,lp,vp}.o`/`glob.o`/`regcomp.o`/`getcwd.o`，逐一 `find`
   核对文件名完全一致），**零新增失败、零回归**。
6. **全量 `lit -v tests/lit/E2E/`**：**72/72 PASS（100.00%）**，与
   落地前重新确认的基线完全一致，零回归。
7. **`python3 tools/run_differential.py`**：`AGREE(3-way)=200
   gem5-SKIP=2 DIVERGE=0` / `AGREE(4-way)=200 Sail-SKIP=2
   SAIL-DIVERGE=0`——与基线完全一致（本任务不改任何指令语义，只加
   musl 侧 C 库符号）。
8. **`python3 scripts/manifest_check.py`**：`manifest validation: PASS`。
   **`python3 scripts/check_issues.py`**：`Open: 22 / Closed: 37 /
   Total: 59 / ISSUE REGISTRY: PASS`（Open 从 20 变 22——新增本任务的
   `musl-softfloat-shim-missing-divsc3`，另 +1 与主仓库一次并发提交
   有关，见下方"遗留问题"说明，与本任务代码无关）。
   **`check_lit_bytes.py`**：`69 patterns OK`。**`check_codegen_abi.py`**：
   `MATCH=23 OPEN-COMMIT=3 INFO=2 MISMATCH=0`，`RESULT: PASS`。
9. **gcc-c-torture 全量重扫（`tests/scripts/gcc_torture_sweep.py
   --workers 8`，1708 个用例）与 ML-026a 基线对比**：

   | 状态 | ML-026a 基线 | 本任务落地后 | 差值 |
   |---|---|---|---|
   | PASS | 1328 | 1409 | **+81** |
   | FAIL_LINK | 217 | 133 | **-84** |
   | FAIL_RUN | 49 | 52 | +3 |
   | FAIL_COMPILE | 113 | 113 | 0 |
   | TIMEOUT | 1 | 1 | 0 |
   | TOTAL | 1708 | 1708 | 0 |

   **92 个原始受影响文件的逐一去向**（独立按文件名对拍 before/after
   两份完整 JSON 结果）：**81 个转 PASS**（74 个直接因本任务列出的
   符号转 PASS + 7 个因本任务在验证过程中发现的、原清单未列出的
   `__unordsf2`(6 个文件)/`__floatdisf`(1 个文件) 缺口一并补齐后转
   PASS——详见下方"与任务原文的出入"）；**3 个转 FAIL_RUN**
   （`pr15262-1.c`/`pr44575.c` exit=127，即 ML-026a §5.1 已归类的
   `abort_127`；`pr28982b.c` exit=1，即 ML-026a §5.2 已归类的
   `unexpected_exit_1`——均是"链接问题解决后暴露出的、已有独立分类、
   与本任务软浮点符号无关"的既有类别，不算本任务范围内的新缺陷）；
   **6 个仍 FAIL_LINK**（`__alloca`，任务背景已声明超出本任务范围）；
   **1 个仍 FAIL_LINK**（`complex-5.c`，`__divsc3`，本任务判断延后，
   见上方处置决定）；**1 个仍 FAIL_LINK**（`builtins/lib/main.c`，
   缺 `main_test` 符号——独立核实这是 llvm-test-suite 自身的公共测试
   基础设施文件，不是一个独立的 torture 用例，本身设计上就需要跟另一个
   提供 `main_test` 的文件一起链接，与软浮点符号无关，不在本任务范围）。
   **全量 1708 个用例零回归**（独立 before/after 全量对拍：0 个从
   PASS 退化，恰好 81 个从非-PASS 转 PASS，与上表 PASS 差值完全对账）。

**与任务原文的出入（均已如实核实，非隐瞒）**：

1. **实际实现 20 个符号，而非任务原文列出的 18 个**：验证过程中独立
   编译链接发现 2 个任务原文未列出的符号缺口：`__unordsf2`
   （`ieee/compare-fp-{1,3,4}.c`/`ieee/fp-cmp-{2,4f,8f}.c` 共 6 个文件，
   `isunordered()`/`islessgreater()` 宏展开成的直接调用，区别于
   `==`/`!=`/`<` 等触发的 `__eqsf2` 等符号）和 `__floatdisf`
   （`conversion.c` 的 `sll2f`，`long long`→`float`）。两者都是同一
   符号家族里模式完全成熟、可直接照抄既有函数（`__unorddf2`/
   `__floatundisf`）改写的低风险扩展，按 ML-022a/ML-025a 已有先例
   （"如果验证中发现新的小缺口，在本任务范围内继续补，不要因为一个
   意外符号就中断"）在本任务内直接补齐，未回头找架构师，也未缩水
   到只做原文列出的 18 个再谎报"完成"。
2. **`__floatunsidf` 未重复实现**：任务原文脚注已明确"`__floatunsidf`
   已在 ML-022a 实现，报告里重复列出是统计口径问题，不是真的缺"——
   核实无误，未重复添加。

## 审阅记录（subagent）

### 判决：Accepted

subagent（general-purpose agent）已读 `reviewer.md`，独立执行以下核验
（非仅采信完成区转述，逐条真实命令重跑，用 `/usr/bin/git diff` 绕过本
仓库 `git` 别名/hook 对 `git diff` 输出的截断后读了全部约 650 行 diff）：

1. **完整 diff 通读**：`/usr/bin/git diff 0b28784a..f6ba5f43 --
   src/internal/dadao/softfloat_shim.c` 全文读完，逐一核对新增的每个
   函数（`cmp_ordered_df`→`__gtdf2/__ledf2/__ltdf2`、
   `__floatdidf/__floatundidf`、
   `__floatunsisf/__floatundisf/__floatdisf`、
   `__addsf3/__subsf3/__divsf3`、`cmp_nonequal_f32`→`__eqsf2/__nesf2`、
   `__unordsf2`、`cmp_ordered_sf`→`__gesf2/__gtsf2/__lesf2/__ltsf2`、
   `__fixunssfdi/__fixsfdi`）与其对应的既有 f64 版本
   （`__gedf2`/`__fixdfdi`/`__fixunsdfdi`/`__floatsidf`/`__floatunsidf`/
   `__adddf3`/`__divdf3`）逐一比对 ✓。
2. **独立重新编译/反汇编/undefined symbol 核查**（未信任完成区数字，
   自己重跑）：`clang --target=dadao -ffreestanding -O2
   -fno-optimize-sibling-calls -c` exit 0；`llvm-objdump -dr
   --triple=dadao | grep -c call` = **2**（与完成区一致）；`llvm-nm -u`
   = 空（0 未定义符号）；独立确认 2 处 `call` 分别位于
   `<__subdf3>`（既有，调 `__adddf3`）和 `<__subsf3>`（新增，调
   `__addsf3`），文件内 33 个已定义符号中其余全部**零** `call` ✓。
3. **独立原生 fuzz（未采信 4,871,106 这个数字，自己重写了一份 harness
   直接 `#include` 实际提交的源文件，改名避免符号冲突）**：`__divsf3`
   20 万随机 + 225 特殊值对 vs 原生 `/`，0 不一致；
   `__gesf2/__gtsf2/__lesf2/__ltsf2` + `__gtdf2/__ledf2/__ltdf2` +
   `__eqsf2/__nesf2/__unordsf2` 121 特殊值对 + 20 万随机 double，专门
   断言 NaN 时 `ge`/`gt` 必须 `<0`、`le`/`lt` 必须 `>0`，含
   `+0.0`/`-0.0` 相等显式核验，0 不一致；`__floatdidf/__floatundidf`
   50 万随机（含偏向舍入边界的构造）+ `INT64_MIN`/`2^53±1`/
   `2^54..2^54+3` 进位点/`2^62` 等显式边界 vs 原生 `(double)` cast，
   0 不一致；`__fixsfdi/__fixunssfdi` 20 万随机 vs 原生 cast，0 不
   一致；`__floatdisf`/`__floatunsisf`/`__floatundisf`/
   `__addsf3`/`__subsf3` 附加抽查 1,500,031 次，0 失败——**独立合计
   约 372 万次核对，0 失败** ✓。
4. **边界/未测输入推敲**：`+0.0`/`-0.0` 在 `cmp_ordered_df`/
   `cmp_ordered_sf`/`cmp_nonequal_f32` 里均通过 fuzz 验证正确判等；
   `__unordsf2` 对 `(NaN,finite)`/`(finite,NaN)`/`(NaN,NaN)` 均正确
   非零、两个有限值正确为零，逐一对照原生 `isnan()` 组合验证；
   `__floatdisf`/`__floatundisf` 的 `INT64_MIN`/0/小值/跨 f32 24-bit
   尾数舍入边界的值均通过 fuzz+显式边界验证正确 ✓。
5. **`__fixsfdi`/`__fixunssfdi` 边界局限独立复现，超出完成区自述范围**：
   自建 20 万个落在 `[2^63,2^64)` 精确区间的浮点位模式，对拍
   `__fixunssfdi` vs 原生 `(uint64_t)` cast，**0 不一致**（独立确认
   无符号路径在该区间确无对应缺口）；并独立验证 `__fixsfdi` 与既有
   `__fixdfdi` 在同一量级产出**完全相同**的环回值
   （`-6101064678203457536`），坐实"同一继承行为类别、非新的/不同的
   回归"这一判断 ✓。
6. **`docs/issues.yaml` `musl-softfloat-shim-missing-divsc3` 条目**：
   `check_issues.py` PASS（22/37/59）；独立读取
   `.work/source/llvm-test-suite/.../{complex-5,6,7}.c` 源码原文，
   确认 `complex-5.c` 的 `1.0f / z`（`z` 为 `float __complex__`）
   真实触发复数除法、`complex-6.c`/`complex-7.c` 分别只用到取共轭/
   构造和 `!=`，均不需要 `__divsc3`——核实条目对这三个文件的具体
   论证成立（未逐一重新推导全部 92 个文件，但登记条目本身的论证与
   schema 均健全）✓。
7. **额外发现（非阻断，工具环境提示）**：本仓库 `git`（rtk 包装）
   会静默把 `git diff` 输出截断成压缩摘要，必须用 `/usr/bin/git`
   直接调用才能看到完整 diff——不是代码缺陷，但提醒未来 reviewer
   注意，避免误信只看到约 1/6 内容的摘要输出。

**finding**：无（判决=Accepted，零阻断 finding，故无处置表）。

## 遗留问题

- `musl-softfloat-shim-missing-divsc3`（新登记 open issue）：`__divsc3`
  单精度复数除法未实现，`complex-5.c` 仍 FAIL_LINK，需要独立后续任务
  （引入 `logb`/`scalbn` 层 + C99 Annex G 特判表）。
- `codegen-tailcall-lowercall-assert`/
  `musl-backend-dynamic-stackalloc-unimplemented`（既有 open issue，
  本任务未触碰）：10 个 musl 源文件仍编译失败，本任务逐一核对确认
  与本任务改动无关。
- `frame-offset-no-imms12-range-check-silent-wraparound`（ML-027a 新
  登记的既有 open issue，本任务未触碰）：gcc-c-torture 里
  `FAIL_COMPILE`/部分 `TIMEOUT`/大栈帧相关的失败与本任务软浮点符号
  无关，留给该 issue 对应的独立任务处理。
- **主仓库（`~/DADAO-0628`，非 `.work/source/musl` 子仓库）git 历史
  异常**：本任务对 `docs/issues.yaml` 的编辑，在会话过程中被一次
  时间上重合的、内容为"ML-027a: diagnose pr56866.c hang"的并发提交
  （commit `babc758`，author `suiyan`）意外一并纳入——本任务从未在
  主仓库执行任何 `git commit`（只在 `.work/source/musl` 子仓库按
  任务要求提交），但 `git status`/`git blame` 核实该提交的 diff 里
  确实包含本任务撰写的 `musl-softfloat-shim-missing-divsc3` 条目全文。
  内容本身经核实完整、正确、无损坏，但提交归属（commit message 未
  提及 ML-028a）与本任务不符，如实记录供架构师核实主仓库当时是否有
  其它并发会话在同一工作目录操作、以及是否需要在后续提交里补充归属
  说明——本任务未尝试改写/修正该段 git 历史（避免破坏性操作）。

## 架构师追加 review（2026-07-24）

### 结论

**Accepted，无 blocking finding。**

本次追加 review 不只采信实现者和前序 subagent 的完成区，独立核对了当前
musl 提交、0013 patch、目标对象、问题登记以及落地后的全局回归结果。ML-028a
可以按当前边界收口；`__divsc3` 保持独立 open issue 是符合任务书授权的范围
控制，不应为追求“92/92”而在本任务中仓促扩张。

### 独立复核证据

1. `.work/source/musl` 的普通提交为
   `f6ba5f43b337ae9df767417086eed59711551f23`，单一 parent
   `0b28784a191b0de3451b0c15bd498c9f57e0c32f`；子仓库 clean。
2. `components/musl/patches/0013-...patch` 与对该提交重新执行
   `git format-patch -1 --stdout` 的 SHA-256 均为
   `39f0bbab3474b27234e02f31a053547a8582365012ca19c0305029fb1b342c1a`；
   在当前提交上 `git apply --check --reverse` 通过，`series` 共 13 项且
   0013 为末项。
3. 当前 DADAO `softfloat_shim.o` 中 20 个新增符号全部存在；
   `llvm-nm -u` 为空。`llvm-objdump -dr --triple=dadao` 全对象仅有两处
   `call`，对应既有 `__subdf3→__adddf3` 和新增
   `__subsf3→__addsf3`，未发现新增函数自递归或额外 undefined libcall。
4. 独立重跑 `llvm-lit -sv tests/lit/E2E/`：72/72 PASS。
5. 独立重跑 `tools/run_differential.py`：
   `AGREE(4-way)=200`、`DIVERGE=0`、`SAIL-DIVERGE=0`，与基线一致。
6. 独立重跑 1708 项 `gcc_torture_sweep.py`：
   PASS 1409 / FAIL_COMPILE 113 / FAIL_LINK 133 / FAIL_RUN 52 /
   TIMEOUT 1；与完成区记录完全一致。相对 ML-026a，PASS +81、
   FAIL_LINK -84，未出现总数或分类对账漂移。
7. `manifest_check.py` 与 `check_issues.py` 均 PASS；独立 deferred issue
   `musl-softfloat-shim-missing-divsc3` 明确限定为 `complex-5.c`，没有把
   “软浮点符号家族已补齐”夸大为“复数软浮点已完成”。

### 非阻断观察

- `__fixsfdi` 在 `[2^63,2^64)` 邻近区间的行为继承既有
  `__fixdfdi`/compiler-rt 模式，任务完成区已明确披露且未把该区间纳入强
  正确性声明；本次没有发现由 ML-028a 新增的不同缺陷。
- 大规模 host fuzz 与负控制目前以任务证据记录为主，并未形成常驻仓库测试。
  这不阻断本任务（全 corpus、E2E、目标反汇编和两轮独立 fuzz 已形成充分
  证据），但后续若继续扩展 softfloat，宜把代表性边界向量沉淀成可重复的
  小型回归，避免未来只依赖历史文字证据。

**架构师最终 review 判决：Accepted。**
