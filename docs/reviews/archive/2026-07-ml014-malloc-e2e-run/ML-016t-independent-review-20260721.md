# ML-016t 独立 implementation review：i1 `SIGN_EXTEND_INREG`

日期：2026-07-21（Asia/Shanghai）  
结论：**Accepted-with-findings**

## 结论摘要

实现本身通过 review。当前 `.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`
相对 before snapshot 的精确 diff 只有 5 行：在 `ADD/SUB` legal action 后加入注释和

```cpp
setOperationAction(ISD::SIGN_EXTEND_INREG, MVT::i1, Expand);
```

当前文件与 `/tmp/ml-016t-fix-i1-sign-extend-20260721/after/DADAOISelLowering.cpp`
逐字相同；checkout diff 也只有该文件的 5 insertions。LLVM
`LegalizeDAG` 对 `SIGN_EXTEND_INREG` 按 operand 1 的 inner type 查询 action，因此该
注册精确命中 i1。generic `Expand` 对 scalar i1 生成 `and 1` 后 `sub 0, masked`，保证
false→0、true→-1；这不是对所有 integer sign extension 或所有 ABI 的承诺。

## Finding

F-1（低严重度，证据管理）：
`/tmp/ml-016t-fix-i1-sign-extend-20260721/evidence-sha256.txt` 共 2455 条记录，其中
最后一条是该 manifest 自身的 hash。直接执行 `sha256sum -c` 返回 rc=1，并报告唯一失败
项为 manifest 自身；排除自引用后，其余 2454 条记录逐项复算全部通过。建议后续生成
manifest 时排除自身，或把 manifest 的 hash 放到外部记录中，使完整校验命令能返回 0。
该 finding 不改变下述源码、工具和产物的逐项核验结果。

## 构建 provenance

- 修复前工具来自 `/home/holight/DADAO-0628/.work/build/llvm/bin/`，LLVM revision
  `10690fc4d40dd7d30757b344c2e259cd9c89a5c4`。
- 修复后实际使用同一 build tree 下的 `clang`/`llc`；当前交叉核验版本为 22.1.8，
  LLVM revision `40bc313742b00848d341e77e1a38441211971729`，且 source checkout
  `HEAD` 与该 revision 相同。
- 当前 clang SHA-256 为
  `d1c6e0026741e45f7ae98f13d4057a6838f9ef049d6b9d110152a2f90ce94bdc`，llc SHA-256
  为 `ac7a71404061254b68f7d43cd343f4b121952af77b0ef7cb2428a15231ad2f9c`，均与
  after metadata 一致。
- [`ninja-final-verify.argv`](/tmp/ml-016t-fix-i1-sign-extend-20260721/build/ninja-final-verify.argv)
  记录 `ninja -C .../.work/build/llvm clang llc`，最终 rc=0，stdout 为 `no work to do`。

## 回归核验

### IR singleton

18 个 singleton probes × O0/O3，按每个 backend 计 36 个结果：

| backend | before | after |
|---|---:|---:|
| clang | 28/36 | 36/36 |
| llc | 28/36 | 36/36 |
| finalize-isel MIR | 28/36 | 36/36 |

before 的 8 个失败只出现在 `sext_i1_i8`、`sext_i1_i32`、`sext_i1_i64` 和
`bool_neg_use` 的 O0/O3；stderr 是 `Cannot select ... sign_extend_inreg ...
ValueType:ch:i1`。after 无失败。

对照没有回归：zext i1 的 i8/i32/i64 三种宽度、branch、select、volatile i1、
i8/i32 sign extension 和 zero extension 均保持通过。before/after 的失败集合没有
出现新的簇；这只证明本次覆盖的簇，不外推到未测路径。

### C matrix

12 个 C probes × O0/O3，fresh IR 由 after clang 生成；frontend、clang、llc 和
finalize-isel MIR 各为 24/24，合计结果见
[`c-fresh-results.tsv`](/tmp/ml-016t-fix-i1-sign-extend-20260721/after/c-fresh-results.tsv)。
矩阵覆盖 bool negate/return/select、bool-to-i64、branch/select、volatile i1、
i8/i32 sext 和 zext。before 的 clang/llc 均为 20/24，失败为 `bool_neg` 与
`bool_select_neg` 的 O0/O3；after 全部为 rc=0。

### original `puts.c` 与 include 边界

隔离 include 命令使用 `-nostdinc` 及隔离 musl 的 arch、internal、include 路径；argv
和逐步 rc 在 `/tmp/ml-016t-fix-i1-sign-extend-20260721/after/logs/puts_source_*`
中。original `puts.c` 的 O0/O3 结果为：

| stage | before | after |
|---|---:|---:|
| frontend | 2/2 | 2/2 |
| clang source→asm | 0/2 | 2/2 |
| llc IR→asm | 0/2 | 2/2 |
| clang object | 0/2 | 2/2 |
| finalize-isel MIR | — | 2/2 |

在不提供 include 路径的 host-header probe 中，before/after 的 O0/O3 均 rc=1，错误
均为 `fatal error: 'stdio_impl.h' file not found`。这是 header 边界，不是 backend
失败。无 header 的 `puts-equivalent.c` 在 O0/O3 的 frontend、clang、llc、MIR
也均 rc=0；O0 IR 可见 `zext i1` 加 `sub`，与本修复的 generic lowering 形状一致。

## 验收边界

本次验证确认了 DADAO SelectionDAG lowering、fresh clang/llc、IR/MIR/asm 和隔离
source/object gate；没有进行 archive、完整 link、runtime、QEMU/gem5 或 ABI conformance
验收。因此 `Expand` 成功只能表述为“本 i1 `SIGN_EXTEND_INREG` lowering 在覆盖的
目标类型和 probe 上成功”，不能泛化为所有 ABI、calling convention、bool return
约定或其他未测 failure cluster 已被证明正确。

证据目录：
[`/tmp/ml-016t-fix-i1-sign-extend-20260721/`](/tmp/ml-016t-fix-i1-sign-extend-20260721/)。

