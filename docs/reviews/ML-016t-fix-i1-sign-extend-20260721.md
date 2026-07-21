# ML-016t：DADAO i1 sign_extend 修复 review

日期：2026-07-21（Asia/Shanghai）  
结论：**Worker complete；待独立 review**

## 范围与修改

本轮只处理 `SIGN_EXTEND_INREG` 的 i1 legalize。读取了 ML-016t 任务以及 ML-016l、
ML-016s 原始证据；没有回滚协作者改动。唯一的 DADAO source diff 是
`.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp` 增加：

```cpp
setOperationAction(ISD::SIGN_EXTEND_INREG, MVT::i1, Expand);
```

原因是 SelectionDAG legalizer 对该 opcode 按 inner type 查询 action。原默认 action
为 `Legal`，而 DADAO 没有 i1 sign-extension selector pattern；`Expand` 走 LLVM 通用
boolean lowering，生成 `and 1` 与 `sub 0`。精确 diff 为
[`DADAOISelLowering.before-after.diff`](/tmp/ml-016t-fix-i1-sign-extend-20260721/build/DADAOISelLowering.before-after.diff)，
只有该五行注释/一行 action 的增量。

## 工具与证据完整性

实际重编命令为 `ninja -C .work/build/llvm clang llc`。修复后 clang/llc 均来自
`/home/holight/DADAO-0628/.work/build/llvm/bin/`，版本 22.1.8、LLVM revision
`40bc313742b00848d341e77e1a38441211971729`；修复前后路径和 hash 在
`before/metadata.txt`、`after/metadata.txt`。最终 ninja verification rc=0。

临时目录
[`/tmp/ml-016t-fix-i1-sign-extend-20260721/`](/tmp/ml-016t-fix-i1-sign-extend-20260721/)
保留 before/after source snapshot、每条命令 argv/rc/stdout/stderr、IR、MIR、asm、
`puts` source/IR probe、standalone puts-equivalent probe、归一化 C 结果和 hash manifest。

## 结果核对

| 矩阵 | 修复前 | 修复后 |
|---|---:|---:|
| IR singleton clang | 28/36 | 36/36 |
| IR singleton llc | 28/36（失败 rc=134） | 36/36 |
| IR singleton finalize-isel MIR | 28/36（失败 rc=134） | 36/36 |
| C matrix clang | 20/24 | fresh 24/24 |
| C matrix llc | 20/24（失败 rc=134） | fresh 24/24 |
| C matrix fresh MIR | — | 24/24 |
| original puts source clang/object | 0/2 | 2/2 |
| original puts source llc | 0/2（rc=134） | 2/2 |

修复前 IR 失败只出现在 `sext_i1_i8/i32/i64` 与 `bool_neg_use` 的 O0/O3；stderr
均为 `Cannot select: ... sign_extend_inreg ... ValueType:ch:i1`。zext i1、bool
return、branch/select、volatile load/store、i8/i32 sext/zext 对照均成功。修复后
i1 sext 的 asm 出现 `and` 后 `sub`，而 zext/select/i8 对照仍保留各自原有 lowering。

新 clang 重新生成 C IR 后，12 个 probe 在 O0/O3 的 frontend、clang、llc、MIR 全部
rc=0，包括 `bool_neg`、`bool_select_neg`、branch/select、bool return、volatile
路径和 i8/i32 对照。

## puts 边界

使用隔离 include/config 的 original `puts.c`，修复前 frontend O0/O3 为 rc=0，但
source clang/object 为 rc=1、llc 为 rc=134；修复后 source clang、llc、object 和
MIR O0/O3 全部 rc=0。独立的无 include host-header 命令仍为 O0/O3 rc=1，stderr 是
`fatal error: 'stdio_impl.h' file not found`；该阻塞已单列，不能与 backend 结果混合。

`puts-equivalent.c`（无 host header，返回 `-((lhs < 0) || (rhs < 0))`）在新 clang
下 O0/O3 的 frontend、clang、llc、MIR 全部 rc=0。O0 的 IR 保留 `zext i1`+`sub`，
O3 优化为等价整数逻辑，说明可用 source probe 已越过 backend gate。

## 验收边界

本轮未修改 TableGen、AsmPrinter、inline asm hook、calling convention、musl、主
archive、contracts、vectors、issues、wiki、QEMU/gem5 或 ML-014a；未进行 archive、
完整 link/runtime 验收。仓库内修改文件仅为 task 完成区、本文档和上述 DADAO lowering
文件。
