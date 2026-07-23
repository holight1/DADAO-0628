# ML-026a：gcc-c-torture 全量扫描——产出分类失败清单（不修复，只扫描+分类）

**执行环境**: 本地 subagent

**状态**: 待处理

## 硬约束（务必遵守，违反视为任务失败）

- **本任务是纯扫描/分类任务，不修复任何发现的问题**——不改 LLVM/QEMU/gem5/musl 任何
  源码，不改 backend，不改 contracts。任务的唯一交付物是一份**如实分类的失败清单**，
  给架构师/用户决定后续怎么处理。发现代码缺陷也不要顺手修，记下来就行。
- **禁止**对任何 component 做 `git rebase`/`git am` 重放整条历史/`git reset --hard`。
  本任务预期不需要对任何 component 做任何 git commit（纯只读扫描 + 产出报告文件）。
- 报告必须如实——不能为了让"通过率"好看而放宽判定标准（比如把 abort/崩溃当成
  "跳过"而不计入失败），也不能因为失败数量大就笼统地"归为一类了事"，参照下面
  「分类方法论」逐项归类。

## 背景

`docs/adr/0012-test-tiering-strategy.md` D5：项目终极目标是 gcc-c-torture 全量通过
（不通过项必须有明确理由）。已归档的旧工具链 `~/toolchain/llvm-unicore` 用 CMake
集成方式跑通 1617/1708（94.7%），且深挖证实剩余 91 个失败里 **DADAO ISel/backend
bug = 0**（全部是 clang 前端不支持的 GCC 扩展、测试自身的 no-main() companion 文件、
或模拟器超时）——这个先例只继承**失败分类方法论**，不继承代码。

`varargs-pointer-args-lost-rb-bank-save-area` 已在 `DL-072a`（2026-07-23）修复关闭
——按 ADR-0012 D5 第4条排期决策，这是本次大规模扫描前的前置阻断项，现已解除，
本任务现在可以开始。

DADAO-0628 目前用"薄 lit 封装"路线（`ADR-0012 D4`，非旧工具链的 CMake 集成方式），
`tests/lit/E2E/llvm-test-suite/` 下只手写了 23 个精选测试。gcc-c-torture 语料本身有
**1708 个 `.c` 文件**（`.work/source/llvm-test-suite/SingleSource/Regression/C/
gcc-c-torture/execute/`，含 `builtins/`、`ieee/` 两个子目录），手写 1708 个 lit 测试
不现实——本任务需要写一个**批量扫描脚本**，不是继续手写单个 lit 文件。

## 目标

1. 写一个批量扫描脚本（放 `tools/` 或 `tests/scripts/` 下，参照项目既有脚本风格），
   对 gcc-c-torture 语料的每个 `.c` 文件依次：
   - 用当前项目工具链（`clang --target=dadao`，musl `arch/dadao`/`include` 头文件路径，
     参照 `tests/lit/E2E/musl_printf_int.test`/`musl_malloc_printf.test` 等既有测试
     的真实编译/链接命令行范式，不要凭空发明新的编译参数）编译。
   - 链接 `.work/build/musl/lib/{crt1.o,libc.a}`（`tests/scripts/dadao.ld` 链接脚本）。
   - 用 QEMU 跑（参照 D2 决策"QEMU 主跑、gem5 抽检"，大规模非里程碑扫描不需要每个
     用例都双后端——但对**最终归入"真实 DADAO 缺陷"这一类**的用例，应该额外跑一次
     gem5 交叉确认，帮助判断是编译器/ABI 层面的通用缺陷还是某个后端模拟器特有问题）。
   - 记录每个用例的结果：编译成功/失败、链接成功/失败、运行退出码、是否超时。
   - gcc-c-torture 的成功/失败判定约定（务必先读几个样例文件确认，不要凭空假设）：
     测试程序内部逻辑失败会调用 `abort()`（通常导致进程收到 SIGABRT 类信号退出，
     不是正常 exit code）；成功路径是 `exit(0)` 或 `main` 正常 `return 0`——这与本
     项目其它 E2E 测试"约定一个特定非零退出码代表成功"的惯例不同，扫描脚本要按
     这个语料自己的约定判定 PASS/FAIL，不要套用其它测试的退出码假设。
   - 设置合理的单用例超时（模拟器速度慢，1708 个用例全跑可能耗时很长，脚本要能
     并行/分批跑，且单个用例卡死不能拖垮整个扫描——参照旧工具链遇到过 8 个
     TIMEOUT 用例的经验）。
2. 把结果按下面「分类方法论」分类，产出一份 markdown 报告（放
   `docs/reviews/ML-026a-gcc-c-torture-sweep-<日期>.md`），包含：
   - 总数、各分类计数、通过率。
   - 每个失败分类下的具体文件名清单（不是只给数字）。
   - 对每个失败分类，给出**根因判断**（不是"失败了"就完事）：是 clang 前端不支持
     的 GCC 扩展（具体是哪种扩展，比如嵌套函数/VLA-in-struct/未知 builtin/asm 约束等，
     参照旧工具链找到的分类）、companion 文件本身没有 `main()`（正常现象，非缺陷）、
     模拟器超时、还是**真实的 DADAO 后端/ABI/musl 缺陷**（这一类要具体到失败现象、
     初步怀疑的层级，不需要深挖到底层根因——那是后续任务的事）。
3. **不要修复任何发现的问题**——本任务是纯扫描分类，交付物是报告，不是补丁。

## 分类方法论（参照 `~/toolchain/llvm-unicore` 已验证过的先例，只继承方法不抄代码）

- **FAIL_COMPILE**：clang 编译期失败。逐一核实是否是 clang 前端本身不支持的 GCC
  扩展（换任何 clang target 都会同样失败，与 DADAO 后端无关）——常见类型：嵌套函数、
  VLA-in-struct、未知 GCC builtin、asm 约束扩展、十进制浮点等。如果失败原因看起来
  是 DADAO 后端特有的（比如某个 CodeGen crash/assert，只在 dadao target 出现，其它
  target 不会），单独标出来，这才是需要关注的"真实缺陷"候选。
- **FAIL_LINK**：链接失败。核实是否是测试集自身设计成多文件配套的 companion 文件
  （该文件本身没有 `main()`，需要和另一个同名前缀文件一起编译才构成完整程序——
  这是 gcc-c-torture 语料的已知正常现象，不是缺陷）。如果是有 `main()` 的文件但链接
  失败，需要具体分析缺什么符号。
- **TIMEOUT**：编译链接都成功，但运行阶段在合理时间内没有退出（区分"死循环/真的
  跑不完"还是"模拟器单纯速度慢，再等等能出结果"——如果时间允许可以对 TIMEOUT 类
  单独跑一次更长的超时验证是否只是慢）。
- **FAIL_RUN（重点）**：编译链接都成功，运行了，但退出方式不是"正常成功路径"
  （即触发了程序内部的 `abort()`，或者是模拟器/后端层面的异常退出如 MALIGN/RASOF/
  非预期信号）——这是最可能包含真实 DADAO 缺陷的一类，需要逐一列出文件名+具体的
  退出现象（退出码/abort 还是硬件异常）。
- **PASS**：编译、链接、运行、退出方式都符合成功语义。

## 验收

- 产出报告文件，包含总数、PASS 数、各失败分类计数+文件清单+根因判断。
- 批量扫描脚本本身要能重复运行（不是一次性手工跑的记录，脚本要作为交付物之一
  提交，供以后复用/迭代）。
- 报告需要明确说明：这次扫描是否重跑了差分/manifest/issues 等既有回归门禁（本任务
  预期不改动任何 backend/musl 代码，不需要重跑这些门禁，但需要在报告里如实声明
  "本次未改动生产代码，不适用回归门禁"，不要假装跑了）。
- 如果扫描本身需要新增任何"胶水"文件（比如给某些 torture 用例提供缺失的
  musl 头文件桩、或者一个统一的编译 flags 集合脚本），这些属于扫描脚本的一部分，
  可以提交，但不能是针对具体某个 torture 用例的特殊 workaround（那属于"修复"，
  不在本任务范围内）。
- 报告最后要有一份"建议后续任务"清单（哪些失败簇看起来值得单独立项修复，按你
  的判断给优先级建议，不需要真的创建任务文件，只是报告里的建议章节）。

## 参考指针

- `docs/adr/0012-test-tiering-strategy.md` D4（薄 lit 封装路线）、D5（gcc-c-torture
  终极目标、旧工具链 1617/1708 先例的分类方法论）
- `.work/source/llvm-test-suite/SingleSource/Regression/C/gcc-c-torture/execute/`
  （1708 个 `.c` 文件语料，含 `builtins/`、`ieee/` 子目录）
- `tests/lit/E2E/musl_printf_int.test`、`tests/lit/E2E/musl_malloc_printf.test`
  （既有真实 clang→ld.lld→QEMU/gem5 编译链接运行管线范式，扫描脚本的编译/链接
  命令行应该照抄这个既有范式，不要发明新参数）
- `tests/scripts/dadao.ld`（链接脚本）
- `.work/build/musl/lib/{crt1.o,libc.a}`（`make build-musl` 生成）
- `tests/lit/E2E/llvm-test-suite/`（现有 23 个手写精选测试，可以参考但本任务是
  批量脚本路线，不是继续手写）
- 若发现的某个 GCC 扩展分类需要具体分类名，可以参照 llvm-unicore 旧工具链归档的
  91 个失败样本分类（嵌套函数29/VLA-in-struct 8/未知builtin 8/asm约束+十进制浮点2/
  其它前端严格性4/no-main companion 32/TIMEOUT 8）作为分类命名参考，但**本项目的
  实际分布大概率不同**（前端支持程度、musl 完整度都不一样），不要假设数字会一致，
  必须实测。

## 完成区

**状态**：已完成
**修改文件**：
- 新增 `tests/scripts/gcc_torture_sweep.py`（可重复运行的批量扫描/分类/报告生成脚本，
  支持 `--retest-timeouts`、`--gem5-crosscheck`、`--report` 子模式）
- 新增 `docs/reviews/ML-026a-gcc-c-torture-sweep-2026-07-24.md`（分类报告）
- **未改动任何 backend/musl/LLVM/QEMU/gem5/contracts 源码**（符合硬约束）

**验收结果**：
- 全量 1708 个 `.c` 文件真实跑通 clang→ld.lld→objcopy→QEMU 管线（~16s，8 并发）；
  1 个 TIMEOUT 用 60s 复测仍未结束，额外独立跑 gem5 SE 复现同样挂起（两个独立实现
  一致）；49 个 FAIL_RUN 全部按 D2 决策额外做了 gem5 交叉确认。
- PASS=1328(77.8%) / FAIL_COMPILE=113(6.6%) / FAIL_LINK=217(12.7%) / FAIL_RUN=49(2.9%)
  / TIMEOUT=1。
- 逐一核实：FAIL_COMPILE 113 个里 84 个（74.3%）与 upstream `execute/CMakeLists.txt`
  自带的分类清单**逐文件精确匹配**（nested_function 29/29、vla_in_struct 8/8、
  return_type 3/3、gnu89-inline 12/12 等），29 个是真实 DADAO 后端候选缺陷
  （VLA dynamic_stackalloc 9、无向量类型 legalize 11、`__int128` CallingConv 6、
  BlockAddress 3）。FAIL_LINK 217 个里 123 个可解释（companion-no-main 105、
  gnu89-inline 12、GCC 专有 builtin 3、-O0 下 `link_error` 死代码消除失效 2、
  setjmp/longjmp 1），94 个是候选缺陷（单精度/双精度顺序比较软浮点符号缺失 92
  个文件——本次最大单一可行动发现；大常量地址计算被错误编码进短范围 relocation
  2 个文件）。FAIL_RUN 49 个里发现一个高价值方法论问题：`-ffreestanding` 会关闭
  clang 对"main 隐式 return 0"的插入（C11 hosted-only 保证），实测确认至少 12
  个 `unexpected_exit_1` 用例纯粹是这个 flag 副作用（去掉 `-ffreestanding` 全部
  变为真实 PASS），非 DADAO 缺陷；另发现变参传小 struct 实参（12 个文件，与
  DL-072a 同一 ABI 区域但不同子问题）、`nestfunc-4.c` 深递归触发真实 RASOF
  硬件异常（架构级发现：当前无 RAS-spill-to-stack 机制）等候选。
- 报告含完整文件名清单（每个分类）、根因判断、9 条按优先级排序的建议后续任务、
  §8 回归门禁声明（未跑，因未改动生产代码，不适用）。

**遗留问题**：
- 本次全程 `-O0`，未做 `-O2` 复扫（见报告 §6 建议 11），gcc-c-torture 里部分
  用例专门检验优化器正确性，`-O0` 下这类检验的意义有限，是最大的已知覆盖缺口。
- 报告列出的候选缺陷（软浮点符号缺失/relocation 范围/VLA/`__int128`/向量
  legalize/RASOF 架构问题/变参 struct 实参）均未修复，按任务定位等待架构师/
  用户决定下一步立项顺序。
