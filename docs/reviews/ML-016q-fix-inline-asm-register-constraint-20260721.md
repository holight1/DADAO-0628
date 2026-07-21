# ML-016q：inline asm `r` register constraint 修复 review

日期：2026-07-21（Asia/Shanghai）  
状态：完成；保留 host-header 直编阻塞证据

## 结论

已在 DADAO target lowering 增加最小 `r` mapping。LLVM 22 的 generic
[`TargetLowering::getRegForInlineAsmConstraint`](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/CodeGen/SelectionDAG/TargetLowering.cpp:5872)
对非 `{register}` 约束返回空 register class；SelectionDAG 随后在
[`getRegistersForValue`](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/CodeGen/SelectionDAG/SelectionDAGBuilder.cpp:9935)
无法为 `r` 分配寄存器。本修复在
[`DADAOISelLowering.cpp`](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp:83)
对 `r`、非向量整数 `MVT`、宽度 ≤64 bit 返回现有 `DADAO::GPRDRegClass`，其余约束
继续 generic fallback。

DADAO 的 pointer/address bank `GPRB` 与 data bank `GPRD` 在 hook 中无法由原始
pointer flag 区分；因此 generic `r` 采用可分配的 GPRD。pointer operand 的值由
既有 cross-bank copy 传入，后端没有新增 calling-convention 或寄存器类定义。
`GPRF` 当前不可分配，故没有虚构 `f` mapping。

## 前后结果

修复前引用 ML-016o 原始记录：
[`matrix.tsv`](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/metadata/matrix.tsv)、
[`backend logs`](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/backend)、
[`MIR logs`](/tmp/ml-016o-inline-asm-constraint-repro-20260721/logs/mir)。

| 形状 | 修复前 O0/O3 backend | 修复后 O0/O3 backend | 修复后 MIR/asm |
|---|---:|---:|---|
| `explicit_bzero` pointer `r` input | 1 / 1 | 0 / 0 | 均生成 |
| pointer `r` input | 1 / 1 | 0 / 0 | 均生成 |
| i64 `r` input | 1 / 1 | 0 / 0 | 均生成 |
| i64 `=r` output | 1 / 1 | 0 / 0 | 均生成 |
| i64 `=r,r` output+input | 1 / 1 | 0 / 0 | 均生成 |
| i64 `+r` inout | 1 / 1 | 0 / 0 | 均生成 |
| u8/u16/u32/u64 input/output/inout | 全部 1 / 1 | 全部 0 / 0 | 均生成 |
| `m`/`=m`/`+m` memory | 0 / 0 | 0 / 0 | 均生成 |
| `memory`/`cc` clobber | 0 / 0 | 0 / 0 | 均生成 |
| 无操作数 asm / `trap 2, 0` | 0 / 0 | 0 / 0 | 均生成 |

修复后完整逐命令记录在
[`post-matrix.tsv`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/logs/metadata/post-matrix.tsv)，
每条命令的 argv/rc/stdout/stderr 分别在
[`frontend`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/logs/frontend)、
[`backend`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/logs/backend) 和
[`mir`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/logs/mir)。asm 与
finalize-isel MIR 在
[`probes/asm`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/probes/asm) 和
[`probes/mir`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/probes/mir)。

代表性后修复 MIR：

- pointer input 为 `INLINEASM ... reguse:GPRD`，前置指针 bridge 为 `rb2rd`；见
  [`input_pointer.O0.mir`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/probes/mir/input_pointer.O0.mir)。
- i64 output/inout 分别为 `regdef:GPRD` 和 tied `reguse`；见
  [`inout_scalar_u64.O0.mir`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/probes/mir/inout_scalar_u64.O0.mir)。
- memory 仍为 `mem:m`，无 operand/clobber 仍没有寄存器 operand；见
  [`memory_inout.O0.mir`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/probes/mir/memory_inout.O0.mir)
  和 [`no_operand.O0.mir`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/probes/mir/no_operand.O0.mir)。

## explicit_bzero 与阻塞边界

新的 `llc` 使用 ML-016o 已核对的 fresh frontend IR 重新运行
`explicit_bzero`：O0/O3 backend 和 finalize-isel MIR 均 rc=0，asm 均实际生成；
记录为 [`from-ml016o backend`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/logs/backend)
下的 `explicit_bzero.from-ml016o.*` 文件。

本轮用新 clang 直接从 dated probe source 重新生成 explicit_bzero IR 的命令也已
执行，但主机 `/usr/include/string.h` 找不到 `bits/libc-header-start.h`，O0/O3
均 rc=1；重试增加 `/usr/include/x86_64-linux-gnu` 后仍保留同一 raw stderr。对应
原始记录是 [`explicit_bzero frontend logs`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/logs/frontend)。
该 host-header 失败没有被计入 target hook 修复结果，也没有以旧 asm 替代修复后
产物；修复后结果只采用新 `llc` 对 fresh IR 的新输出。

## Build 与范围

`ninja -C /home/holight/DADAO-0628/.work/build/llvm llc` 和 `clang` 均 rc=0，
命令/rc/stdout/stderr 保存在
[`build logs`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/logs/build)，
新工具版本保存在 [`tool`](/tmp/ml-016q-fix-inline-asm-register-constraint-20260721/tool)。

因 override 声明需要，额外修改同一 ownership 的
[`DADAOISelLowering.h`](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.h:52)。
除此之外只更新本 task 完成区和本 review 文档；未修改 AsmPrinter、其他 target、
TableGen、musl、主 build/archive、QEMU/gem5、contracts、vectors、issues、wiki
或 ML-014a。该验证仍是 backend 单对象/CodeGen 回归边界，不是 archive、runtime 或
QEMU/gem5 验收。
