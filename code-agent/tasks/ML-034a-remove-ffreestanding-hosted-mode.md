# ML-034a：移除测试编译链路的 `-ffreestanding`，改用 hosted 模式

**执行环境**: 本地 subagent

## 硬约束（务必遵守，违反视为任务失败）

- **只改测试/扫描脚本编译用户程序时传给 clang 的 flags，不改 musl 自身构建**。
  `.work/source/musl/Makefile:47` 的 `CFLAGS_C99FSE = -std=c99 -ffreestanding
  -nostdinc` 是 musl 上游构建自身 libc 实现的标准做法（musl 编译自己的源码时
  一直是 freestanding，这是正确且不该动的），**不在本任务范围内**，不要碰。
  本任务只改"测试程序/torture 用例本身"被编译时用的 flags。
- **禁止**对 `.work/llvm`/`.work/source/musl`/`.work/source/qemu` 做
  `git rebase`/`git am` 重放整条历史/`git reset --hard`。本任务预期不需要改
  任何 `.work/*` 源码（纯粹是调用方传的编译选项变化），如果诊断后发现确实需要
  动 LLVM/musl/QEMU 源码才能保证零回归，先停下来报告，不要在没有把握的情况下
  硬改核心组件。
- 已知会用到 `-ffreestanding` 的文件（本任务范围内，需要逐一处理）：
  - `tests/scripts/gcc_torture_sweep.py`（`CFLAGS` 列表）
  - `tests/scripts/embench_sweep.py`（同名 `CFLAGS` 机制，`ML-032a` 刚新增）
  - 以下 10 个 E2E lit 测试文件里 `%clang` 调用的选项：
    `musl_malloc_printf.test`、`malloc_hello.test`、`musl_e2e_exit.test`、
    `musl_printf_ptrs.test`、`musl_stdin_getchar.test`、
    `musl_malloc_sizeclass.test`、`printf_hello.test`、
    `musl_malloc_sizeclass_liteonly.test`、`musl_printf_int.test`、
    `musl_scanf_int.test`、`musl_puts_writev.test`
  （用 `grep -rl -- '-ffreestanding' tests/` 复核这份清单是否完整，不要假设
  上面列的就是全部——脚本可能还有别的调用路径遗漏没抓到。）
- 完成后必须在任务文件里写「完成区」+ subagent 自审「审阅记录」（含逐条 finding
  + 判决）。

## 背景

`ML-026a`（`docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md` §方法论
发现）识别出：编译 gcc-c-torture 用例时用 `-ffreestanding` 会关闭 C11 对
`hosted` 环境下 `main()` 落到函数末尾隐式 `return 0` 的保证——在 freestanding
模式下 clang 不做这个特殊处理，`main` 落到末尾时返回值是未定义的寄存器残留值，
导致至少 ~12-15 个原本逻辑正确的用例被误判为 `FAIL_RUN`。这是一个方法论层面
的假失败来源，不是后端 bug。

项目当年选 `-ffreestanding` 是因为最初 bare-metal + 手写 crt0、没有真实 libc
时，需要告诉 clang 不要假设 hosted 环境的运行时组件存在。但现在（`ML-007a`~
`ML-012a` 之后）项目已经有一个真实、完整链接的 musl（`crt1.o`+`libc.a`），
`main()` 由 musl 的 `_start` 按标准 hosted 约定调用——不再需要 `-ffreestanding`
这层假设。用户已于本 session 决定：**去掉 `-ffreestanding`，改用 hosted 模式**，
但要求验证"去掉后 crt0/musl 集成不会因为 clang 假设了某些 hosted 环境组件
（如 `__libc_start_main` 之类的语义联动）而出现新问题，需要全量 E2E 回归验证"。

## 目标

1. 逐一确认上面列出的每个文件里 `-ffreestanding` 的确切作用范围，改成不传
   `-ffreestanding`（即默认 hosted 模式）。同时评估是否需要保留/调整
   `-nostdinc`、`-nostdlib` 等其它 freestanding 相关 flag——这些和
   `-ffreestanding` 不是一回事，`-nostdinc`/`-nostdlib` 只影响头文件/link
   阶段的默认搜索路径，与"是否假设 hosted 运行时语义"无关，**默认保留不动**，
   除非诊断中发现有实际冲突再调整并说明理由。
2. **风险排查（用户明确要求的验证项）**：hosted 模式下 clang 可能对
   `main` 的签名、`__attribute__((used))`、内建函数识别（如 freestanding 关闭
   了一些内建 `memcpy`/`memset` 之类的假设，hosted 会重新打开）等产生不同的
   codegen 假设。需要在切换前后各跑一次全量套件，确认没有因为这类假设差异
   引入新的编译失败/运行时错误——如果发现有，如实诊断根因（是测试本身依赖
   freestanding 特有行为，还是后端对 hosted 模式下产生的某些 IR pattern
   缺乏支持），不要为了"看起来全绿"而回退到某个文件继续用 `-ffreestanding`
   而不说明理由。
3. 重新运行全量 gcc-c-torture 扫描（`python3 tests/scripts/gcc_torture_sweep.py`），
   报告修正后的真实 PASS 数、以及具体是哪些文件从 FAIL_RUN 翻转为 PASS（预期
   在 ML-026a 报告提到的 ~12-15 个附近，但以实测为准，不要假设一定是这个数字）。
   同时确认没有任何原 PASS 的文件退化（逐文件 diff，不只看聚合数字）。
4. 重新运行 Embench sweep（`python3 tests/scripts/embench_sweep.py`），确认
   O0/O2 结果不因为这个 flag 变化而改变（除非诊断后发现确有关联，如实报告）。
5. 全量 `llvm-lit tests/lit/E2E/`：确认零回归（这批测试原来就是靠
   `-ffreestanding` 编译的，现在改 hosted 模式后功能语义不能变，包括新增的
   聚合体/VLA/varargs 相关测试）。

## 验收

- `grep -rl -- '-ffreestanding' tests/` 在本任务改动范围内的文件里应为空
  （musl 自身 Makefile 除外，那不属于本任务范围）。
- 全量 gcc-c-torture 重扫：报告新分布，和当前基线 `1438/104/131/35`
  （`ML-033a` 完成后的基线）逐文件对比，明确列出所有状态变化的文件；
  **不允许任何原 PASS 文件退化**，FAIL_RUN→PASS 的文件数量和具体文件名如实
  报告。
- Embench sweep：O0/O2 各 19 项结果与当前基线（O0 19/19、O2 18/19 仅
  `qrduino` FAIL）对比，如实报告是否有变化。
- 全量 `llvm-lit tests/lit/E2E/`：零回归（落地前重新跑一次记录当前基线为准，
  当前应为 77/77）。
- `python3 tools/run_differential.py`：AGREE 数与当前基线一致、DIVERGE=0
  （本任务不改指令语义，理论上不应变化）。
- `python3 scripts/manifest_check.py`/`check_issues.py` 通过。
- 若诊断中发现任何一个文件因为 hosted 模式引入了新的、非假失败的真实失败，
  如实登记为独立 issue，不要为了保留统一 flag 集合而放弃摘除
  `-ffreestanding`——除非发现摘除会导致大范围真实回归，此时应停下来报告
  给架构师而不是自行决定折中方案。

## 参考指针

- `docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md`（`-ffreestanding`
  发现的原始出处、~12-15 个假失败文件的方法论讨论）
- `tests/scripts/gcc_torture_sweep.py`（`CFLAGS` 列表，约第 90 行附近）
- `tests/scripts/embench_sweep.py`（同类 `CFLAGS` 机制，`ML-032a` 新增）
- `tests/lit/E2E/*.test`（上面列出的 10 个文件，`%clang` 调用里的 flags）
- `.work/source/musl/Makefile:47`（`CFLAGS_C99FSE`——**不要动**，仅作为
  "musl 自身构建仍应保持 freestanding"的对照参考）
- `contracts/abi/spec.md`（如果发现 hosted/freestanding 切换涉及 ABI 假设，
  这里是权威依据）
