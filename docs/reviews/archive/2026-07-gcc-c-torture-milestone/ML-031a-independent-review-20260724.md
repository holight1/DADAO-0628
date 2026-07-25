# ML-031a 独立实现审查（2026-07-24）

**任务**：`code-agent/tasks/ML-031a-aggregate-struct-abi-parameter-passing.md`
**权威依据**：wiki pin `9f378f4426e131903d60a208766086ae74a53c89` 的
`DADAO-21-ABI-应用程序二进制接口.md` §聚合类型参数、§可变参数、§聚合类型返回值
**最终审查对象**：

- LLVM `9079603c93f3`：aggregate ABI 分类；
- LLVM `ac7c52aa6cd4`：`MaxStoresPerMem*` 从 `UINT_MAX` 改为 `16`；
- LLVM `53e5e16e829a`：严格区分 float/double HFA，并撤销未经 wiki 授权的数组 flatten；
- root 未提交的 0055/0056/0057 patch、series、ABI contract、issues/wiki questions、
  两个 E2E 及任务完成记录。

## 最终判决

**Needs changes**

0057 和最新 E2E 收口修正有效，当前常规回归数字及 patch provenance 也可信；但独立
探针仍确认 4 个 blocking finding：

1. 带内部 padding 的递归 HPA 会丢字段，双后端运行失败；
2. `>32B` 聚合变参被间接化为一个指针 slot，违反 wiki/任务要求的逐 8B slot 布局；
3. 带内部 call 的 sret callee 在 `-O2` 返回时不保持 RB16；
4. 0056 使普通 `-O2`、超过 16 个 byte-store 的尾位置 mem* intrinsic 稳定触发
   DADAO tail-call assertion。

因此目前不能把 HPA、全部聚合变参、sret 和 0056 的通用 libcall 路径标记为完成。

## Findings

### Blocking B1：`[N x ptr]` coercion 不能正确传递带 padding 的递归 HPA

wiki 的 HPA 判定只看递归展开后的叶字段：所有叶子均为指针且数量不超过 4；padding
并不是 disqualifier。当前 `flattenHomogeneous` 会把下面的 `PaddedHPA` 判为两个
pointer leaf，但 `classifyArgumentType` 随后直接 coercion 为 `[2 x ptr]`：

```c
typedef struct { void *p; } __attribute__((aligned(16))) Inner;
typedef struct { Inner i; void *q; } PaddedHPA;
```

真实 layout 中 `i.p` 位于 offset 0，`q` 位于 offset 16；`[2 x ptr]` coercion
却只加载 offset 0..15。独立 IR 证据为：

```llvm
%0 = load [2 x ptr], ptr %coerce.dive, align 16
%call = call i32 @check([2 x ptr] %0)
```

因此第二个“叶子”实际来自 padding，而 offset 16 的 `q` 没有进入 RB bank。使用
volatile/noinline 检查的 freestanding 探针期望退出 42，实际：

- QEMU：exit `17`
- gem5：exit `17`

这不是 caller/callee 同错后仍可自洽通过的理论风险，而是当前最终 clang
`53e5e16e829a` 内容上的真实运行失败。

**要求**：HPA lowering 必须按叶字段的真实 AST layout 提取/重建值，不能假定叶子
在内存中无 padding 地连续排列；增加 nested/padded HPA 的 IR 寄存器映射和双后端
运行回归。

### Blocking B2：`>32B` 聚合变参只占一个指针 slot，不符合 wiki

wiki §可变参数明确要求“聚合体 >8 字节按自然对齐拆分为多个 8 字节单元，按字节序
依次占用连续 slot”；任务目标 3 同样要求按实参实际大小占用多个 slot。当前代码先
对所有参数统一执行 `classifyArgumentType`，所以 `Big40` 命中普通参数的
`>32B indirect` 分支。变参调用的独立 IR 为：

```llvm
%byval-temp = alloca %struct.Big40, align 8
call void @llvm.memcpy.p0.p0.i64(..., i64 40, ...)
%call = call i32 (i32, ...) @probe(
    i32 1, ptr %byval-temp, i32 777)
```

对应汇编保存区只有：

- `sp+0`：命名参数 `1`
- `sp+8`：`Big40` 临时对象的指针
- `sp+16`：尾随 `777`

而不是 wiki 要求的 `Big40` 五个连续数据 slot 加尾随标量。`EmitVAArg` 的
`IsIndirect=true` 让同一编译器的 callee 从该指针读取，所以普通 C E2E 可以
caller/callee 同错后通过；它不具备跨工具链 ABI 一致性。

**要求**：把聚合变参保存区序列化与普通 named `>32B indirect` 分类区分开，按原始
聚合体大小写入 `ceil(size/8)` 个连续 slot；增加至少一个 40B 聚合体加尾随标量的
布局检查和双后端测试。若架构实际希望 `>32B` 变参例外地间接传递，必须先修改 wiki/
任务契约，当前原文不支持这一例外。

### Blocking B3：sret callee 返回时没有保证 RB16 仍为 sret 地址

wiki 明确要求：hidden sret 地址由 RB16 传入，callee 返回时 RB16 仍保存该地址。
当前实现只依赖 sret pointer 作为第一个 pointer argument 自动进入 RB16，没有在
return lowering 中把该地址建模为 RB16 live-out。

独立探针让 sret 函数内部调用另一个 pointer-argument 函数：

```c
typedef struct { long a,b,c,d,e; } Big;
__attribute__((noinline)) void sink(long *);
__attribute__((noinline)) Big make(long *p) {
  Big b;
  sink(p);
  b.a=1; b.b=2; b.c=3; b.d=4; b.e=5;
  return b;
}
```

最终 `-O2` 汇编关键序列：

```asm
sto  rb16, rb1, 0      # 保存 sret 地址
addi rb16, rb17, 0     # RB16 改为 sink(p) 的参数
call sink
ldo  rb8, rb1, 0       # 只恢复到 rb8
...                    # 通过 rb8 写返回对象
ret  rd0, 0            # RB16 未恢复
```

返回时 RB16 仍是 `sink` 的参数/被调用者可破坏值，不是 sret 地址。现有 `make_big`
没有内部 call，只验证了 caller 能从自己持有的地址读取返回对象，未检查 RB16
返回契约。

**要求**：在 calling-convention/lowering 层显式保证 sret 地址通过 RB16 live-out
返回，并增加“sret callee 内部发生 pointer call”的 MIR/汇编回归；测试必须检查
返回前 RB16，而不只是检查返回对象内容。

### Blocking B4：0056 引入常见 `-O2` mem* tail-call 编译崩溃

把 `MaxStoresPerMemset/Memcpy/Memmove` 从 `UINT_MAX` 降为 `16`，确实避免了
256KB copy 被无限内联展开；`pr28982b.c` 也独立复验为 PASS。但 DADAO 的 tail-call
lowering 仍未完成，0056 使此前可内联的小/中型 mem intrinsic 新进入 libcall 路径。

对尾位置 17-byte 操作的独立结果：

| Probe | `-O2` 结果 |
|---|---|
| `__builtin_memcpy(d,s,17)` | rc=1，tail-call assertion |
| `__builtin_memmove(d,s,17)` | rc=1，tail-call assertion |
| `__builtin_memset(d,0,17)` | rc=1，tail-call assertion |

三者均命中：

```text
Assertion `(!CLI.IsTailCall || InVals.empty()) &&
          "LowerCall emitted a return value for a tail call!"' failed.
```

边界验证：8B/16B memcpy 仍内联并编译成功；17B 起触发。使用
`-mllvm -max-store-memcpy=4294967295` 模拟 0056 之前的阈值时，17B 和 136B
均编译成功；在 mem* 后增加副作用使其不处于 tail position 时，也能正常生成
`call memcpy`。因此这是 0056 扩大可达面的真实回归，不可由全量 torture 默认
非 `-O2` 的绿色结果排除。

**要求**：在启用有限阈值前完成/禁用这类 libcall 的 tail-call 转换，或采用不会
进入未支持 tail-call 路径的保守方案；为 memcpy/memmove/memset 分别增加 tail
position 与 non-tail、阈值边界和超大 copy 回归。

### Major M1：合同和完成记录对能力范围存在过度声明

`contracts/abi/spec.md` 当前写为 HPA、ordinary aggregate、全部 `>8B` aggregate
vararg 和 sret 已实现；任务完成区也称“全套分类逻辑”和通用 0056 已修复。B1-B4
证明这些表述尚不成立。技术修复后应同步收窄或恢复这些声明，并把新增回归数字写入
任务 MD；不能仅把上述失败登记为不阻塞的新 issue 后继续判定完成。

### Major M2：最新 E2E 对已覆盖路径有判别力，但缺失阻断边界

架构师追加的 E2E 收口是有效改进：

- 输入已改为 volatile 来源；
- named 测试的负控制位于所有主路径之后，QEMU/gem5 均得到预期 93；
- vararg 测试有独立负控制，QEMU/gem5 均得到预期 9；
- O0/O2 的正例均真实执行。

但现有 E2E 只覆盖紧密排列 HPA、12/16B 变参、无内部 call 的 sret，以及不会生成
mem* libcall 的 nostdlib 规模；因此 76/76 与 B1-B4 并不矛盾。修复时必须把上述
四个边界纳入回归，而不是只复跑当前 76 项。

### Informational I1：0057 的两项 spec 收口正确

`53e5e16e829a` 已正确修复原 9079603 中的两项分类偏差：

- HFA 要求同一浮点类型，`float + double` 不再误判为 HFA；
- wiki 只授权递归展开 nested struct，数组字段不再被擅自展开为 HPA/HFA。

新增 Clang IR/诊断测试锁定 mixed-float、pointer-array 和真实 HFA warning/fallback，
独立 `llvm-lit` 1/1 PASS。该提交本身无新增 blocking finding。

### Informational I2：两个 wiki 边界歧义已诚实记录

RD-split “高位块先入高寄存器”和非整 8B 聚合变参最后一个 slot 的左右对齐，确实
缺少可独立判定的 worked example。`docs/wiki-questions.md` #6/#7 明确记录了当前
选择及 caller/callee 同实现测试的局限，没有把自洽结果冒充独立 spec oracle。
在 wiki 回答前，不应扩大跨工具链互操作声明。

### Minor N1：最终构建标识仍显示前一提交

用于本轮测试的 clang 已包含 0057 行为（新增 Clang 测试通过），但
`clang --version` 仍显示 `ac7c52aa6cd4`，原因是该 binary 在 0057 内容提交前完成
链接。最终修复落地后应从最终 HEAD 再构建一次，使产物 revision 与源码 HEAD 一致。

## 独立验证结果

| 验证 | 结果 |
|---|---|
| Clang aggregate ABI 定向 lit | 1/1 PASS |
| ML-031a 两个 E2E（含正/负控制全部 RUN） | 2/2 PASS |
| 全量 E2E | 76/76 PASS |
| 目标 torture filter | 21 PASS / 1 FAIL_RUN（`pr38151.c`） |
| 全量 gcc-c-torture | PASS 1429 / FAIL_COMPILE 113 / FAIL_LINK 131 / FAIL_RUN 35 |
| 新鲜全量 JSON vs 接手时 `gcc-torture-results.json` | 1708 项，status mismatch=0 |
| differential | AGREE(3-way)=200，DIVERGE=0；gem5-SKIP=2 |
| Sail | AGREE(4-way)=200，SAIL-DIVERGE=0；Sail-SKIP=2 |
| manifest/issues/wiki refs/wiki drift | 全部 PASS |
| CodeGen ABI checker | MISMATCH=0（3 个既有 OPEN-COMMIT） |
| lit byte checker | 69 patterns OK |
| `pr28982b.c` | PASS |

以上数字可信，但不能覆盖或抵消 B1-B4 的定向失败。

## Patch / provenance

- 0055/0056/0057 的 `From` commit 与三笔普通 LLVM commit 一致；
- 三个 patch 的 stable patch-id 分别与对应 commit 精确一致；
- 从 manifest LLVM pin `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1`
  在独立临时 clone 中 plain `git am` 顺序重放 **57/57** 成功；
- replay tree 与 `.work/llvm` `53e5e16e829a` tree 均为
  `ee6f26d13babca1285b2491b45b2dd2ae843d714`；
- `.work/llvm` 审查结束时干净。

因此 provenance 本身通过；判决 `Needs changes` 来自实现语义和测试覆盖，而不是
patch 导出问题。

## 关键验证命令

```bash
.work/build/llvm/bin/llvm-lit -sv \
  .work/llvm/clang/test/CodeGen/DADAO/aggregate-abi.c

.work/build/llvm/bin/llvm-lit -sv \
  tests/lit/E2E/agg_args_named.test \
  tests/lit/E2E/agg_vararg_multislot.test

.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/

python3 tests/scripts/gcc_torture_sweep.py \
  --filter 'stdarg-3|strct-stdarg-1|strct-varg-1|va-arg-22|pr38151|920625-1|920908-1|931004-|pr44575' \
  --out /tmp/ml031a-review-filter.json

python3 tests/scripts/gcc_torture_sweep.py \
  --out /tmp/ml031a-review-full.json

python3 tools/run_differential.py
python3 scripts/manifest_check.py
python3 scripts/check_issues.py
python3 scripts/check_wiki_refs.py --profile abi
python3 scripts/check_wiki_drift.py
python3 scripts/check_codegen_abi.py
python3 scripts/check_lit_bytes.py
```

独立 probe 均通过 stdin 送给最终 clang，产物仅放在 `/tmp`；未修改实现源码、任务
MD、contract、issues、测试或 patch series。
