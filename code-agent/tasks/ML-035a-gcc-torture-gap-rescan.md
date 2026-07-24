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
