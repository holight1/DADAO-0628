# ML-035a: gcc-c-torture 剩余缺口重新分类扫描（2026-07-24）

**任务**：`code-agent/tasks/ML-035a-gcc-torture-gap-rescan.md`
**性质**：纯扫描/分类/分析任务 —— **本次未修复任何代码，未改动 `.work/*` 任何源码**。
**基线**（本任务开始前重跑 `python3 tests/scripts/gcc_torture_sweep.py --workers 8`
确认，逐字节匹配任务书给出的基线）：

```
PASS          1461
FAIL_COMPILE   104
FAIL_LINK      125
FAIL_RUN        18
TOTAL         1708
```

与任务书给出的 `1461/104/125/18` **完全一致**，无环境漂移，可以直接在此基线上分类。

结果 JSON 快照（本次重新扫描产出，供复核用，未纳入仓库跟踪，路径供参考）：
`/tmp/claude-1000/-home-holight/9d0a7e60-2718-445f-9a83-ccf36348e840/scratchpad/ml035a-results.json`
（如需复现，直接重跑 `gcc_torture_sweep.py` 即可，无需依赖这个临时文件）。

## 0. 与 ML-026a 的关系

`ML-026a`（`docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md`）是 PASS=1328
基线上的第一次全量分类。此后 `ML-027a`~`ML-034a` 七个任务把 PASS 推进到 1461
（+133），期间关闭了 3 个大簇（frame-offset imms12 越界、92 文件单精度软浮点、
relocation 越界折叠）并新增了 aggregate ABI/VLA/Embench 等能力。本报告在新基线上
重新做同样深度的分类，方法论对齐 `ML-026a` §4（区分"upstream/口径造成的已知不通过"
vs "真实 DADAO 候选缺陷"），并额外做了几处比 `ML-026a` 更深的根因下钻（见 §3.4）。

**本次最重要的结论**：

1. `FAIL_LINK`（125）**100% 已被现有 issue/已知类别覆盖，零新发现**——这类失败的
   杠杆已经在 `ML-028a`/`ML-030a` 里被充分挖掘，此处不再有集中新簇。
2. `FAIL_COMPILE`（104）里"真实候选缺陷"子集（20 个文件：向量类型 legalizer/
   `__int128` CallingConv/`BlockAddress`）**与 ML-026a 报告的 20 个文件逐字节相同**
   ——`ML-027a`~`ML-034a` 没有一个任务touch过这条路径，零进展也零新发现，纯粹是
   老账。
3. `FAIL_RUN`（18，剔除 2 个永久 ABI 排除后剩 16）出现了**两个此前未被识别/被
   误分类的情况**：
   - ML-026a 报告里"12 文件变参传小 struct 实参"这个簇，**10/12 已经在
     ML-031a/ML-034a 期间顺带被修复转 PASS**（包括同一批被提到的 `pr38151.c`
     `_Complex` 变参 corruption 也已翻盘 PASS）；ML-026a 归入该簇的
     `931102-1.c`/`931102-2.c` **经本次逐文件复核，源码里完全没有变参/`va_arg`
     用法，属于 ML-026a 当年按文件名序号相似性误并入该簇**，实际是另一个独立、
     此前从未被记录的真实 miscompile（见 §3.4，本次最高优先级发现）。
   - 该 miscompile（"单比特 AND 测试在特定 SelectionDAG 形状下被静默丢弃，分支
     根据未掩码的原始字节值而非单一比特跳转"）目前在语料库里只命中 2-3 个已知
     文件，但触发它的 C 语言写法（`if (!(x & 1))`／`while ((x&mask)==0)`／单比特
     位域读取）是极常见的真实世界写法，**风险面远大于文件计数本身**。

## 1. FAIL_COMPILE 详情（104）

### 1.1 已知/可解释（84，80.8%）—— 与 ML-026a 报告逐类对齐，无变化

| 子类 | 数量 | 根因 | 文件 |
|---|---|---|---|
| `setjmp_longjmp_unsupported` | 34 | `__builtin_setjmp`/`__builtin_longjmp is not supported for the current target`（DADAO TargetInfo 从未实现这两个 intrinsic，与多个上游 target 同理由被排除） | `built-in-setjmp.c`, `pr64242.c`, `pr84521.c`, `pr60003.c`（**注**：`pr60003.c` 是双因文件——同时有 `-Wincompatible-pointer-types` 错误和 setjmp 报错，但即使修掉指针类型问题它仍会因 setjmp 不支持而编译失败，故归入本类而非 §1.1 pointer_type_strictness），以及 `builtins/lib/chk.c`/`builtins/memcpy-chk.c`/`builtins/memcpy-chk-lib.c`/`builtins/memmove-chk.c`/`builtins/memmove-chk-lib.c`/`builtins/mempcpy-chk.c`/`builtins/mempcpy-chk-lib.c`/`builtins/memset-chk.c`/`builtins/memset-chk-lib.c`/`builtins/pr23484-chk-lib.c`/`builtins/snprintf-chk.c`/`builtins/snprintf-chk-lib.c`/`builtins/sprintf-chk.c`/`builtins/sprintf-chk-lib.c`/`builtins/stpcpy-chk.c`/`builtins/stpcpy-chk-lib.c`/`builtins/stpncpy-chk.c`/`builtins/stpncpy-chk-lib.c`/`builtins/strcat-chk.c`/`builtins/strcat-chk-lib.c`/`builtins/strcpy-chk.c`/`builtins/strcpy-chk-lib.c`/`builtins/strncat-chk.c`/`builtins/strncat-chk-lib.c`/`builtins/strncpy-chk.c`/`builtins/strncpy-chk-lib.c`/`builtins/vsnprintf-chk.c`/`builtins/vsnprintf-chk-lib.c`/`builtins/vsprintf-chk.c`/`builtins/vsprintf-chk-lib.c` |
| `nested_function` | 29 | GCC 嵌套函数扩展，clang 从不支持 | `20000822-1.c`,`20010209-1.c`,`20010605-1.c`,`20030501-1.c`,`20040520-1.c`,`20061220-1.c`,`20090219-1.c`,`920415-1.c`,`920428-2.c`,`920501-7.c`,`920612-2.c`,`920721-4.c`,`921017-1.c`,`921215-1.c`,`931002-1.c`,`comp-goto-2.c`,`nest-align-1.c`,`nest-stdar-1.c`,`nestfunc-1.c`,`nestfunc-2.c`,`nestfunc-3.c`,`nestfunc-5.c`,`nestfunc-6.c`,`nestfunc-7.c`,`pr22061-3.c`,`pr22061-4.c`,`pr24135.c`,`pr51447.c`,`pr71494.c` |
| `vla_in_struct` | 8 | struct 里的变长数组字段（"fields must have a constant size"），与真正的 VLA（已被 `ML-033a` 实现）是两回事——这是 GCC 专有扩展，clang 从不支持 | `20020412-1.c`,`20040308-1.c`,`20040423-1.c`,`20041218-2.c`,`20070919-1.c`,`align-nest.c`,`pr41935.c`,`pr82210.c` |
| `return_type_needs_dash_W_flag` | 3 | 需要 `-Wno-return-type`，upstream 给这 3 个文件专加了该 flag，本次口径未加逐文件 flag | `920302-1.c`,`920501-3.c`,`920728-1.c` |
| `pointer_type_strictness` | 2 | clang 比 GCC 严格的隐式指针类型转换检查 | `alias-1.c`,`pr79043.c` |
| `alignment_mismatch` | 2 | "size of array element ... isn't a multiple of its alignment" | `pr36093.c`,`pr43783.c` |
| `x87_asm_constraint` | 1 | `invalid output constraint '=t'`（x87 专用内联汇编约束，upstream 本就标记 x86-only） | `990413-2.c` |
| `array_too_large` | 1 | 数组过大 | `991014-1.c` |
| `flexible_array_member_init` | 1 | 柔性数组成员初始化，clang 不允许 | `pr28865.c` |
| `decimal_float` | 1 | `_Decimal64` 十进制浮点后缀，clang 从不支持 | `pr80692.c` |
| `builtin_shuffle`/向量赋值 | 1 | `__builtin_shuffle`/GCC 向量类型赋值扩展，clang 不支持 | `pr85331.c` |
| `widechar_array_init` | 1 | 宽字符数组初始化语法差异 | `widechar-2.c` |

小计：34+29+8+3+2+2+1+1+1+1+1 = **84**

### 1.2 真实 DADAO 候选缺陷（20，19.2%）—— 与 `ML-026a` 报告逐文件核对，**零变化**

`ML-027a`~`ML-034a` 没有一个任务涉及向量 legalizer/`__int128` CallingConv/
`BlockAddress` 这三块，本次逐文件重新编译验证错误信息，**20 个文件与
`ML-026a` 报告完全相同**（同一批文件、同一根因），只是本次把错误信息按具体
LLVM 断言/崩溃点做了更细的三个子桶（`ML-026a` 报告把 (b)(c) 各自当成一个桶，
这里按实际崩溃位置进一步拆分，暴露出向量和 `__int128` **共享同一段 CallingConv
lowering 代码路径**，是一个可能一次性覆盖两个类型家族的杠杆点）：

#### (a) 向量类型 `SetCC` 断言崩溃（6 个文件）

```
clang: TargetLoweringBase.cpp:1905: getSetCCResultType(...): Assertion `...' failed
```
文件：`pr23135.c`, `pr53645.c`, `pr53645-2.c`, `scal-to-vec1.c`, `simd-1.c`, `simd-2.c`

#### (b) 函数返回值 CC 分配失败："unable to allocate function return #1"（7 个文件）

这条错误信息同时被向量类型和 `__int128` 触发——**同一个 fatal error 站点**：

- 向量触发（4）：`20050316-1.c`, `20050316-3.c`, `pr60960.c`, `simd-6.c`
- `__int128` 触发（3）：`pr54471.c`, `pr85582-2.c`, `pr85582-3.c`

#### (c) 调用点返回值 CC 分析 `UNREACHABLE`：`CallingConvLower.cpp:174`（4 个文件）

同样是向量和 `__int128` 共享同一个崩溃点（`llvm::CCState::AnalyzeCallResult`）：

- 向量触发（1）：`pr70903.c`
- `__int128` 触发（3）：`pr49218.c`, `pr84748.c`, `pr84169.c`

**(a)+(b)+(c) 按类型分组** = 向量类型 legalizer 缺口 11 个文件（6+4+1）、
`__int128` CallingConv 缺口 6 个文件（3+3），与 `ML-026a` 报告的 11/6 分组
**完全一致**。

#### (d) `BlockAddress`（computed goto）未实现（3 个文件）

```
fatal error: error in backend: Cannot select: t.: i64 = BlockAddress<@fn, %label> 0
```
文件：`990208-1.c`, `comp-goto-1.c`, `pr70460.c`

**杠杆观察**：(b)+(c) 合计 11 个文件（4 向量+7... 更准确地说 (b)(c) 共 11 个
文件里向量 5 个+`__int128` 6 个）都止步于同一段"函数返回值/调用结果 CC 分配"
代码（`CallingConvLower.cpp`/DADAO `LowerReturn`/`LowerCallResult` 相关逻辑）——
如果先做"让 128-bit 宽返回值（不管是向量还是 `__int128`）能分配到两个 64-bit
寄存器"这一件事，(b)(c) 两个桶（11 个文件）有可能被一次性覆盖，只是 (a) 的
`SetCC` 断言崩溃是前置的、独立的另一道关卡（这 6 个文件同时也用了向量比较，
即使修好 CC 分配，`SetCC` 这道坎也会先崩），需要两步都做才能让向量类的 11 个
文件真正编译通过；`__int128` 的 6 个文件理论上只需要修 CC 分配这一步就够
（`__int128` 没有 `SetCC` 断言崩溃这个额外前置问题）。

## 2. FAIL_LINK 详情（125）

### 2.1 已知/可解释（124，99.2%）—— 本次识别为 **100% 覆盖**，零新增未分类项

| 子类 | 数量 | 根因 | 文件 |
|---|---|---|---|
| `companion_no_main`+`companion_missing_main_test` | 106 | upstream 自己就不把 `execute/builtins/` 目录当独立语料跑（"tests in execute/builtins are not run"）。105 个文件缺 `main`（与 `ML-026a` 附录 A 逐字节相同的 105 文件清单，此处不重复列出，见 `ML-026a` 报告附录 A）；额外 1 个文件 `builtins/lib/main.c`**本身提供 `main`**，但反过来缺它自己需要的 `main_test()`（该符号本该由同目录另一个 companion 文件提供）——是同一个"多文件配套语料、不能单独跑"现象的镜像情形，此前因为它恰好还落在 92 文件软浮点符号缺失的并集清单里（`ML-026a` §4.2(a) 列出过 `builtins/lib/main.c`），`ML-028a` 补齐软浮点符号后这个文件的链接错误从"缺软浮点符号"变成了"缺 main_test"，暴露出它一直都属于这个更根本的结构性类别，非新发现 | 105 个 `undefined symbol: main` 文件（同 ML-026a 附录 A）+ `builtins/lib/main.c`（`undefined symbol: main_test`） |
| `gnu89_inline_semantics` | 12 | 依赖旧式 GNU89 `inline` 语义，与 upstream `TestRequiresGnu89Inline` 清单精确匹配（12/12，与 `ML-026a` 报告完全相同） | `20001121-1.c`,`20020107-1.c`,`930526-1.c`,`961223-1.c`,`980608-1.c`,`bcp-1.c`,`loop-2c.c`,`p18298.c`,`restrict-1.c`,`unroll-1.c`,`va-arg-7.c`,`va-arg-8.c` |
| `dash_O0_link_error_idiom` | 2 | 故意不提供定义的 `link_error()`，只有优化器证明分支不可达才会被消除，`-O0` 下必然报未定义符号 | `ieee/fp-cmp-7.c`, `medce-1.c` |
| `known_gcc_only_builtin` | 3 | GCC 专有 builtin，clang 在这版工具链下推迟到链接期报未定义符号 | `pr39228.c`（`__builtin_isinff`/`__builtin_isinfl`）, `pr47237.c`（`__builtin_apply`/`__builtin_apply_args`）, `va-arg-pack-1.c`（`__builtin_va_arg_pack`） |
| `setjmp_longjmp_link` | 1 | 引用 `setjmp`/`longjmp`，musl dadao 移植未提供 | `pr56982.c` |

小计：106+12+2+3+1 = **124**

### 2.2 已登记的 open issue（1，0.8%）—— 非新发现

| 文件 | issue |
|---|---|
| `complex-5.c` | `musl-softfloat-shim-missing-divsc3`（`docs/issues.yaml`，`ML-028a` 评估后明确留待独立任务，算法复杂度显著高于其余符号） |

**FAIL_LINK 总计：106+12+2+3+1+1 = 125，逐文件全部落位，零个"other_link_unclassified"残留。**

**结论**：`FAIL_LINK` 这条线在 `ML-028a`（软浮点）/`ML-030a`（relocation）之后
已经没有集中新簇可挖，唯一的开放项 `__divsc3` 已经是一个登记在案、范围明确
（1 个文件）的独立小任务。**本次不建议在 FAIL_LINK 上再单独立项**（`__divsc3`
本身已经是独立 issue，优先级评估见 §4）。

## 3. FAIL_RUN 详情（18 个，排除 2 个永久 ABI 排除后 16 个待分类）

已排除（不重新分析，按任务书要求）：
- `20050604-1.c`、`pr63302.c` —— `dadao-frame-lowering-8byte-align-insufficient-for-16byte-locals`（永久 ABI 范围排除）

### 3.1 已知/upstream 自身跳过（6 个）—— 与 `ML-026a` 报告一致，逐一核对 upstream `CMakeLists.txt` 确认仍在其跳过清单里

| 文件 | 根因 |
|---|---|
| `bitfld-3.c` | 位域实现差异（signed 位域符号扩展等实现定义行为），upstream 自身标注跳过 |
| `bitfld-5.c` | 同上 |
| `pr32244-1.c` | `#pragma GCC optimize` 被忽略，upstream 自身标注跳过 |
| `pr34971.c` | 同上（optimize-pragma 相关） |
| `eeprof-1.c` | `-finstrument-functions` 不支持，upstream 自身标注跳过 |
| `noinit-attribute.c` | `__attribute__((noinit))` 不支持，upstream 自身标注跳过 |

（`va-arg-22.c`，`ML-026a` 报告里同属此类的第 7 个文件，本次复测**已经是 PASS**
——`ML-034a` 去掉 `-ffreestanding` 后连带修复，不再需要归类。）

### 3.2 已知/musl 系统调用面缺口（3 个）—— 与 `ML-026a` 报告一致

| 文件 | 现象 |
|---|---|
| `fprintf-2.c` | `fopen for writing: Function not implemented`，QEMU/gem5 的 cfx_smon syscall responder 没有"以写模式打开文件"的 syscall 路径 |
| `printf-2.c` | 同上 |
| `user-printf.c` | 同上 |

### 3.3 已知架构级问题（2 个）—— 与 `ML-026a` 报告一致，均已有明确定性

| 文件 | 现象 | 定性 |
|---|---|---|
| `20101011-1.c` | `ILLI`（0x82） | upstream 自己注明这个测试需要一个特殊 `-D` 宏，本次口径未加逐文件 flag，缺该宏触发非法指令，非新发现 |
| `nestfunc-4.c` | `RASOF`（0x84） | 500 层深互递归耗尽硬件 RegRAS，是 `ML-015a` K1 阶段已经记录在案的"RAS 满后无 spill-to-memory 机制"架构问题（见 MEMORY.md ADR-0015 K1 关于 RegRAS bank 的记录），非本次新发现，本报告只是重新确认它仍未解决 |

### 3.4 本次最高优先级发现：单比特 AND 测试在特定 SelectionDAG 形状下被静默丢弃（2 个确诊 + 1 个强嫌疑，共 3 个文件）—— **对 ML-026a 报告的一处更正**

`ML-026a` 报告把 `931102-1.c`/`931102-2.c` 归入"变参传小 struct 实参"这个
12 文件簇（§5.1，当时理由是"逐一确认这些文件的共同结构：`va_arg(ap, struct
XXX)`"）。**本次逐文件复核发现这个归类是错的**：直接读源码确认
`931102-1.c`/`931102-2.c` 完全不含 `va_arg`/`va_list`/`stdarg.h` 用法（用
`grep` 在两个文件里搜不到任何变参相关符号），是两个独立的 K&R 风格 union/位域
测试，测试"取一个字节里最低位为 1 的比特位置"（数 trailing zero）：

```c
/* 931102-1.c（931102-2.c 结构相同，union 里是 short 而非 char） */
typedef union { struct { char h, l; } b; } T;
f (x) int x; {
  int num = 0; T reg;
  reg.b.l = x;
  while ((reg.b.l & 1) == 0) { num++; reg.b.l >>= 1; }
  return num;
}
main () { if (f (2) != 1) abort (); exit (0); }
```

该簇里其余 10 个真正含 `va_arg` 的文件（`931004-2/4/6/8/10/12/14.c`,
`stdarg-3.c`, `strct-stdarg-1.c`, `strct-varg-1.c`）**确认已经全部 PASS**
（`ML-031a` 聚合体 ABI 参数传递 + `ML-034a` 去 `-ffreestanding` 期间被覆盖修复），
包括 `ML-026a` 提到"顺带翻盘但未深挖"的 `pr38151.c`（`_Complex` 变参 padded
struct 字段损坏，`docs/issues.yaml` 里的 `dadao-complex-vararg-padded-struct-
field-corruption`）**本次复核确认也已是 PASS**——按任务书要求如实报告这个状态
变化，不在本任务内判断是否应关闭该 issue。

`931102-1.c`/`931102-2.c` 是**一个此前完全未被记录的真实 miscompile**，用最小
探针独立复现（未改动任何 `.work/*` 源码，探针文件存放于本次任务的 scratchpad，
不提交仓库）：

```c
/* 最小复现：单比特测试用作分支条件时，AND 掩码指令被静默丢弃 */
__attribute__((noinline)) int testMask1(int l) {
  if ((l & 1) == 0) { return 1; } else { return 0; }
}
/* testMask1(2) 应返回 1（2&1==0 为真），DADAO -O0 实测返回 0 */
```

**根因线索（-O0 llc 汇编逐行比对，未修复，仅诊断）**：

- 语义等价、非负极性（真值分支直接对应 `if.then`）写法 `if (l & 1)`／
  `if ((l&1) != 0)` 编译正确（生成 `and rd,rd,1` 后再 `brz`/`brnz`）。
- 语义等价、负极性写法（真值分支对应 `if.else`，即 `if ((l&1)==0)`／
  `if (!(l&1))`）**`and rd,rd,1` 指令整个丢失**，直接对**未掩码的原始字节**
  做 `brnz`/`brz`——对 `l=2`（`00000010b`）这种"第 0 位为 0 但整字节非零"的
  典型输入，得到与预期相反的分支结果。
- 该 miscompile **仅在 `-O0` 复现，`-O2` 下同一段代码正确**（独立验证：同一
  探针文件分别用 `-O0`/`-O2` 编译，只有 `-O0` 输出错误结果）——与本项目当前
  gcc-c-torture 扫描/E2E lit 测试**统一使用 `-O0`** 的既定口径直接相关。
- 追加发现：`960608-1.c`（同样在本次 16 文件待分类清单里，位域读取测试）的
  失败**很可能是同一个根因家族的另一种触发形状**——其 `flags->c != 0` 这个
  子条件（bit 提取需要先 `lshr` 再 `and 1`，非负极性 `!=0` 比较）在生成的
  `.s` 里同样丢失了 `and` 指令，与相邻的 `flags->d != 1` 子条件（同样
  `lshr`+`and 1`，AND 指令正常存在）形成鲜明对比；但用一个不经过位域/指针
  解引用的最小独立探针复现同构的 `(x>>2)&1 != 0` 写法时反而编译正确，说明
  触发条件比"非负极性"更微妙（可能还牵涉到位域从指针解引用读取、或与相邻
  短路 `||` 子表达式共享的 spill slot 有关），**本次未能进一步孤立出单一
  最小触发条件**，留给专门的诊断任务用 MIR 级别调试（`-print-after-all`/
  `-debug-only=isel`）继续二分。

**风险评估（这是本次报告的核心判断）**：当前语料库命中面很小（2 个确诊 +
1 个强嫌疑，共 3/1708），**但这类"静默丢弃掩码指令、不崩溃、只是运行时结果
错误"的 bug 危险等级远高于任何一个编译期崩溃**——真实 C 代码里
`if (!(x & 1))`（判断偶数/清除标志位）、`while ((x & mask) == 0)`（找最低置位
比特）、单比特位域读取是极常见写法，且这类 bug **不会在编译期或链接期报错，
只会在恰好命中"低位为 0 但整字节/整字非零"这种输入时产生错误结果**——gcc-
c-torture 语料库当前只命中 3 个文件很可能是运气（其余程序里凑巧输入值不落在
这个陷阱区间，或者凑巧走了非负极性写法），不代表这个 bug 在真实场景里的实际
风险面只有这么小。

### 3.5 其它独立、低优先级候选（2 个）

| 文件 | 现象 | 定性 |
|---|---|---|
| `20031003-1.c` | `(int)2147483648.0f` 边界值 float→int 转换，`abort_127` | 浮点边界转换行为（`INT_MAX+1` 转 int，C 标准本身未定义），可能是 softfloat shim 或 `__fixsfsi` 边界饱和行为的独立小问题，与 §3.4 无关联迹象（未见 AND/位测试模式），未深挖，单文件，优先级低 |
| `pr85169.c` | `vector_size(64)` 的 `char` 向量逐元素读写，`abort_127` | 能编译通过（未撞上 §1.2 的向量崩溃簇，因为只是逐元素数组式访问，`-O0` 走内存路径被标量化），但运行时结果错误——大概率是向量类型标量化路径的另一处正确性缺口，与"DADAO 无向量 ISA"这个既有事实同源，优先级低（1 个文件，且 DADAO 确实没有向量硬件，价值有限） |

## 4. 更新的优先级建议清单

排序依据：确定性（诊断有多扎实）× 杠杆（覆盖多少文件/多大真实风险面）×
工作量。**不凑数量，如实反映三个类别的真实分类结果**——本次 FAIL_COMPILE/
FAIL_LINK 两条线几乎没有新东西，真正的新增值全部集中在 FAIL_RUN 的一个发现上。

1. **P0 — 诊断+修复 §3.4 的单比特 AND 掩码在负极性分支下被丢弃的 miscompile**
   （预计直接解决 2 个确诊文件 `931102-1.c`/`931102-2.c`，附带验证是否覆盖
   `960608-1.c`；**真正价值不在这 2-3 个文件数量，而在于这是当前已知的
   唯一一个"静默产生错误结果、不崩溃"的控制流 miscompile**，风险面覆盖任何
   使用 `if (!(x&1))`/`while((x&mask)==0)`/单比特位域读取写法的真实 C 程序）。
   工作量级别：**中**——诊断阶段需要先用 MIR 级调试工具（`-print-after-all`
   配合 `-debug-only=isel`，参照 `ML-027a`/`ML-030a` 的二分方法论）孤立出
   具体是哪个 DAGCombine 或 isel pattern 在负极性分支下错误地忽略了 AND 掩码
   （本次已经排除了"简单一步复现"的可能性——独立最小探针 `testMask1`容易
   复现，但 `960608-1.c` 这种位域场景的精确触发条件还需要专门二分），修复
   本身预计是小范围模式修正（参照 `ML-029a`/`ML-030a` 的规模）。
   **建议先在 `docs/issues.yaml` 登记该 issue**（本任务未做，纯扫描任务不
   包含登记新 issue 这一步，留给下发的诊断任务一并完成）。

2. **P1 — `__divsc3`（复数除法软浮点符号）**：已经是登记在案的独立 open
   issue（`musl-softfloat-shim-missing-divsc3`），范围明确（仅 `complex-5.c`
   一个文件），`ML-028a` 已经评估过算法复杂度（Smith's method + C99 Annex G
   特判，需要先补 `logb`/`scalbn`/`isnan`/`isinf` 基础设施）。工作量级别：
   **中**（不是"改几个位宽常量"就能完成，需要新基础设施）。预计解决 1 个文件。

3. **P2 — 向量类型 `SetCC`/CallingConv legalizer 完整性**（11 个文件）+
   **`__int128` CallingConv 完整性**（6 个文件）：本次分析发现两者共享同一段
   "128-bit 宽返回值 CC 分配"代码路径（§1.2 (b)(c)），建议合并成一个任务
   ——先修 CC 分配这一步，`__int128` 的 6 个文件大概率能直接解决，向量的
   11 个文件还需要额外修 `SetCC` 断言（前置关卡）。工作量级别：**大**（涉及
   TargetLowering 的类型合法化配置，是此前 `ML-026a`/`ML-027a`~`034a` 都没有
   触碰过的区域，且需要同时理解向量和 128-bit 整数两种类型的 legalize 路径）。
   预计合计解决 17 个文件（11+6），如果只做 CC 分配这一半，预计先解决
   `__int128` 的 6 个。

4. **P3 — `BlockAddress`（computed goto）支持**（3 个文件）：GNU C 扩展，
   使用面相对窄。工作量级别：**中**（需要新增 ISel pattern，DADAO 目前没有
   任何 label-as-value 相关的 lowering）。

5. **P3 — RASOF 架构问题（RegRAS 满后无 spill 机制）**：`nestfunc-4.c` 是
   已知问题的又一实例（非新发现），已记录在 `MEMORY.md`/ADR-0015 K1 相关
   条目，不是本任务范围能解决的（需要架构级 ABI 决策，涉及 K1 阶段的
   RegRAS bank 保存机制设计），本报告只是重新确认现状。工作量级别：**大**
   （架构决策 + 后端+可能的硬件行为变更，非纯后端 bug 修复）。

6. **P4 — `20031003-1.c` float→int 边界转换、`pr85169.c` 向量标量化正确性**：
   各 1 个文件，未深挖，价值有限，建议留待有余力时再看，不单独立项。

7. **不建议新增任务**：`FAIL_LINK`（125）已经 100% 落位到已知类别/已登记
   issue，`FAIL_COMPILE` 里的"已知/可解释"84 个文件均是 clang 前端能力边界
   或 upstream 自身跳过条目，均不需要 DADAO 后端改动。

## 5. 回归门禁声明

本次任务**未改动任何 backend/QEMU/gem5/musl/LLVM/contracts 源码**，纯只读
扫描 + 独立诊断探针（探针文件位于本次任务的临时 scratchpad 目录，未写入仓库、
未修改 `.work/*` 下任何文件）+ 产出本报告，不适用四方差分/manifest/issues
回归门禁，未重跑，也不需要重跑。诊断阶段用到的 `llc`/`clang` 调用均为只读
编译（`-emit-llvm`/`-S`），未修改任何工具链二进制或源码。
