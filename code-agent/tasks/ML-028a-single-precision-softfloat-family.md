# ML-028a：补齐单精度软浮点符号家族——gcc-c-torture 扫描（ML-026a）杠杆最大的发现

**执行环境**: 本地 subagent

**状态**: 待处理

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
