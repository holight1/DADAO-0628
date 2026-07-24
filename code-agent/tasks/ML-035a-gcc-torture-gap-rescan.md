# ML-035a：gcc-c-torture 剩余缺口重新分类扫描（更新优先级清单）

**执行环境**: 本地 subagent

## 硬约束（务必遵守，违反视为任务失败）

- **本任务纯扫描/分类/分析，不修复任何代码，不改 `.work/*` 任何源码**。
  产出是一份更新的分类报告 + 优先级建议清单，不是补丁。
- 不启动嵌套 subagent。
- 完成后必须在任务文件里写「完成区」（含真实分类数字和逐类文件清单），不需要
  自审 review 区（纯扫描任务，`ML-026a` 当年也没要求 review 区）。

## 背景

`ML-026a`（`docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md`）是本项目
第一次全量 1708 文件扫描，产出的分类和优先级清单已经指导了后续 `ML-027a`~
`ML-034a` 七个任务的修复顺序。但那份报告的分类数据是在 **PASS=1328** 的基线上
做的，此后 `ML-027a`~`ML-034a` 已经把 PASS 推进到 **1461**（详见
`docs/development-roadmap.md` 对应章节），FAIL_COMPILE/FAIL_LINK/FAIL_RUN
里具体是哪些文件、真实根因分布，早已和 ML-026a 报告不一致——继续沿用老报告的
优先级判断会做无用功或错过真正的高杠杆项。

当前基线（`gcc-torture-results.json`，本任务开始前跑一次
`python3 tests/scripts/gcc_torture_sweep.py` 确认）：
`PASS=1461 FAIL_COMPILE=104 FAIL_LINK=125 FAIL_RUN=18`。

已知的、不需要重新分类的部分（不要重复劳动）：
- `FAIL_RUN` 里有 2 个文件（`20050604-1.c`、`pr63302.c`）已经登记为永久性
  ABI 范围排除（`docs/issues.yaml`
  `dadao-frame-lowering-8byte-align-insufficient-for-16byte-locals`，
  128 位类型无 DADAO ABI 对齐契约），不需要再分析，直接从"待处理"里排除。
- `pr38151.c` 已知是 `dadao-complex-vararg-padded-struct-field-corruption`
  （已登记 open issue），不需要重新诊断，但如果本次扫描发现它已经变成
  PASS（`ML-034a` 完成区提到它"顺带"翻盘但没深挖），如实报告这个状态变化，
  不需要判断是否应该关闭该 issue（留给后续任务判断）。

## 目标

1. 对当前 `FAIL_COMPILE`（104个）、`FAIL_LINK`（125个）、`FAIL_RUN`（剩余16个，
   排除上面 2 个已排除文件）逐一分类，参照 `ML-026a` 报告 §4 的方法论
   （区分"upstream denylist 原因"如依赖 GCC/glibc 扩展、目标特定行为等 vs
   "真实 DADAO 后端候选缺陷"）：
   - `FAIL_COMPILE`：编译期报错的具体错误信息分类（哪些是同一类错误反复出现，
     哪些是一次性）。
   - `FAIL_LINK`：具体缺失符号/relocation 错误分类，识别是否有集中的符号簇
     （类似当年 92 个文件集中在同一软浮点符号缺失簇的情形）。
   - `FAIL_RUN`：具体退出码/信号分类（区分 abort()=127、硬件异常 fault code、
     timeout、其它非 0/42 exit code），初步判断是否为已知 ABI 范围排除类别
     （如 HFA/128位类型）的同类新实例，还是独立新缺陷。
2. 对每个分类估计"杠杆"（一个根因能同时解决多少文件），参照 `ML-026a`/
   `ML-028a`（92 文件软浮点符号簇）/`ML-031a`（15 文件聚合体变参簇）的方法论
   ——找同类聚集，不要逐文件孤立分析。
3. 产出更新的、按杠杆和确定性排序的优先级建议清单（不需要凑够 11 条，多少条
   如实反映真实分类结果）。

## 验收

- `python3 tests/scripts/gcc_torture_sweep.py` 全量重跑一次作为本任务基线，
  确认与当前 `1461/104/125/18` 一致（如果不一致，如实报告差异，可能是环境
  漂移，需要先弄清楚再分类）。
- 产出 `docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md`，包含：
  - 三个失败分类各自的详细子分类 + 每个子分类的文件清单（不能只给聚合数字）。
  - 识别出的集中簇（如果有）及其估计杠杆。
  - 按优先级排序的后续建议列表，每条注明"预计解决多少文件"+"预计工作量级别"
    （小/中/大，参照本项目已完成任务的量级做类比，例如"类似 ML-028a 量级"）。
- 任务文件「完成区」总结关键数字和结论（详细内容留在 review 报告里，完成区
  不需要重复整份清单）。

## 参考指针

- `docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md`（方法论范本，
  分类维度和报告格式参照这份）
- `tests/scripts/gcc_torture_sweep.py`（扫描工具，`--filter` 可用于定向复跑
  验证某个分类猜想）
- `docs/issues.yaml`/`docs/issues-archive.yaml`（已登记的所有 open/closed
  issue，避免把已知问题重新当成"新发现"）
- `docs/development-roadmap.md`（`ML-027a`~`ML-034a` 各任务的详细修复历史，
  帮助判断某类失败是否已经是某个已知机制的残留边界情况）

## 完成区

**基线确认**：重跑 `python3 tests/scripts/gcc_torture_sweep.py --workers 8` 得到
`PASS=1461 FAIL_COMPILE=104 FAIL_LINK=125 FAIL_RUN=18`，与任务书给出的基线逐字节
一致，无环境漂移。

**产出**：`docs/reviews/ML-035a-gcc-torture-gap-rescan-2026-07-24.md`（详细子分类+
文件清单+优先级建议，见该报告）。未改动任何 `.work/*`/backend/QEMU/gem5/musl/LLVM
源码，纯扫描+独立诊断探针（探针文件在临时 scratchpad，未提交仓库）。

**FAIL_COMPILE（104）**：84 个已知/可解释（clang 前端能力边界或 upstream 自身
跳过条目：`setjmp_longjmp_unsupported` 34、`nested_function` 29、`vla_in_struct`
8、`return_type_needs_dash_W_flag` 3、`pointer_type_strictness` 2、
`alignment_mismatch` 2、其余 6 类各 1）+ 20 个真实候选缺陷（向量类型 legalizer
11 个 + `__int128` CallingConv 6 个 + `BlockAddress` 3 个）——**这 20 个文件与
`ML-026a` 报告逐字节相同，`ML-027a`~`ML-034a` 均未触碰这条路径，零进展也零新
发现**；本次新发现向量和 `__int128` 共享同一段"128-bit 宽返回值 CC 分配"崩溃
站点（`CallingConvLower.cpp:174`/"unable to allocate function return #1"），是
可能一次覆盖两个类型家族的杠杆点。

**FAIL_LINK（125）**：100% 落位到已知类别（`companion_no_main`+镜像情形 106、
`gnu89_inline_semantics` 12、`dash_O0_link_error_idiom` 2、`known_gcc_only_builtin`
3、`setjmp_longjmp_link` 1）+ 已登记 open issue（`__divsc3`，1 个文件）——**零新
发现，`ML-028a`/`ML-030a` 已经把这条线上的集中簇挖完**，不建议在此再单独立项。

**FAIL_RUN（18，剔除 2 个永久 ABI 排除后 16 个）**：6 个已知 upstream 自身跳过、
3 个 fopen-for-write 已知系统调用面缺口、2 个已知架构级问题（`20101011-1.c`
缺 `-D` 宏 / `nestfunc-4.c` RASOF）、2 个低优先级独立候选（float→int 边界转换、
向量标量化正确性），以及**本次最重要的发现**：

- **对 `ML-026a` 报告的一处更正**：`ML-026a` 把 `931102-1.c`/`931102-2.c` 误并入
  "12 文件变参传小 struct 实参"簇（源码里完全没有 `va_arg` 用法，逐文件复核
  证伪）。该簇其余 10 个真正含 `va_arg` 的文件**已经全部 PASS**（`ML-031a`/
  `ML-034a` 期间修复），包括此前"顺带翻盘未深挖"的 `pr38151.c`（`_Complex`
  变参 corruption issue）**本次确认也已 PASS**（是否关闭该 issue 留给后续
  任务判断）。
- `931102-1.c`/`931102-2.c` 实际是一个**此前完全未被记录的真实 miscompile**：
  单比特 AND 掩码测试（`if ((x&1)==0)`/`if (!(x&1))` 这类负极性写法）在 `-O0`
  下会把 `and rd,rd,1` 指令静默丢弃，直接对未掩码的原始字节做条件分支，导致
  "低位为 0 但整字节非零"的输入得到错误的分支结果；`-O2` 下不复现；
  `960608-1.c`（位域读取）疑似同一根因家族的另一触发形状，但未能孤立出统一
  的最小触发条件。**这是本次扫描识别出的最高优先级后续项**——文件命中数少
  （2 确诊+1 强嫌疑），但这类"不崩溃、只是运行时结果错误"的静默 miscompile
  风险面（`if(!(x&1))`/`while((x&mask)==0)`/单比特位域读取都是常见真实 C
  写法）远大于文件计数本身，建议登记 issue 并作为 P0 下发诊断+修复任务。

**优先级建议**（详见报告 §4）：P0 单比特 AND 掩码丢弃 miscompile（中等工作量，
真正价值在风险面非文件数）；P1 `__divsc3`（已登记 issue，中等工作量，1 文件）；
P2 向量+`__int128` CC 分配共享杠杆点（大工作量，合计 17 文件）；P3
`BlockAddress`（中等工作量，3 文件）/RASOF 架构问题（大工作量，架构决策）；
P4 两个低优先级单文件项，不单独立项。
