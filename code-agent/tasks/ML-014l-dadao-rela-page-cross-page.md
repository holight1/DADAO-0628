# ML-014l：定位 mallocng 触发的 DADAO RELA_PAGE 跨页错误

**执行环境**：本地 subagent worker；承接 ML-014j/ML-014k

**状态**：Completed（2026-07-18；根因已确认，修复另行下发）

## 背景

ML-014i 的候选 `4741d4d1` 让 mallocng `malloc.o` 被静态链接。ML-014j 已确认：
lite-only 和 mallocng-linked 的 `return42`/真实 `mmap` 都双后端 42，但真实
mallocng ELF 在进入 `main` 前双后端 `MALIGN=129`。

本轮架构师分析发现，问题可进一步收敛到 `R_DADAO_RELA_PAGE` 的页差形成：

- lite-only ELF：`.rodata=0x80002000`、`.bss=0x80003008`、`main_tls=0x80003018`；
- mallocng ELF：`.rodata=0x80005000`、`.bss=0x80006008`、`main_tls=0x80006018`；
- `__init_tls` 的 `static_init_tls` 对 `main_tls+0x18` 的 rela/low 配对，在
  mallocng ELF 中链接成 `rela rb8,5; addi rb8,rb8,48`，运行时形成
  `0x80005030`，而真实目标应为 `0x80006030`；
- mallocng ELF 的 `0x80005030` 正好是 `.rodata` 中的非零字节
  `00 01 00 02 00 03 00 04`，按大端装载为 `0x1000200030004`，与 gem5
  `__init_tls` trace 在 `0x80000a24` 观察到的畸变值一致；
- lite-only 的对应错误地址落在 `0x80002030`，超出有效 rodata 内容且由装载初值
  视作零，因此错误被零值布局掩盖。

当前 lld `components/llvm` 对 `R_DADAO_RELA_PAGE` 的实现是对 PC-relative
`val=S-P` 做 `(val+0x800)>>12`。但 ISA/ELF contract 要求的是
`((S+A)>>12)-((P+4)>>12)`，即目标页号减去 `rela` 下一条指令所在页号；不能
把字节差先按 0x800 四舍五入后当成页差。`R_DADAO_RELA_LO` 则使用目标的低 12
位，二者必须组合到真实目标地址。

## Ownership

- 允许修改：本任务 MD、临时 `.work/ML-014l-rela-page-cross-page/` 报告和
  dump；可阅读 `.work` 中已有 ELF、LLVM/lld 源码和 ABI 文档。
- 不允许修改 LLVM、QEMU、gem5、musl 源码、patch series、contracts、manifests、
  `docs/issues.yaml`、ML-014a；本任务只验证根因，不导出候选 patch。
- 不得把 `~/toolchain` 或 `~/knowledge-graph` 传给 subagent；架构师可自行参考。
- 不处理 `-O`、`puts`、mallocng allocator 逻辑或 mmap backend。

## 执行阶梯

1. 独立核对两个 ELF 的 section/symbol 地址、`__init_tls` relocation 配对和原始
   `.rodata` 字节，确认第一个异常字段是 `main_tls.size`（或给出反证）。
2. 独立从 `rela` ISA 语义和 lld `getRelExpr/relocate` 推导应有公式，区分
   `P` 与 `P+4`，检查页边界和 low12 组合。
3. 用一个最小数值/ELF 证据说明为什么 lite-only 会假通过、mallocng 会暴露。
4. 只给出最小实现边界与回归建议；不得修改实现或宣称 mallocng 基本链路已通过。

## 验收

- 报告包含具体 PC、S/P、实际 imm、实际/期望地址及原始字节证据；
- 能解释 QEMU/gem5 相同失败为何支持 linker/ELF image 根因；
- 有 subagent 自审；随后由独立 reviewer 复核；
- 本任务完成不等于 ML-014f/ML-014a 完成。

## 完成区

**Finding：Confirmed。** 当前失败是 DADAO `R_DADAO_RELA_PAGE` 链接时页差
计算错误，首先污染 `main_tls.size`，随后传播到相邻的 `align`、
`libc.tls_size`、raw
`SYS_mmap` 参数和 TLS 指针；不是 musl TLS 算法、mmap 返回桥或 mallocng 元数据
本身。

### 证据

- `__init_tls` 的目标引用位于 `P=0x80000a1c`，下一条指令地址为
  `P+4=0x80000a20`；对象重定位对应 `.bss.main_tls+0x18`，即
  `main_tls.size`。当前 64-bit `struct tls_module` 布局为
  `next@0x0, image@0x8, len@0x10, size@0x18, align@0x20,
  offset@0x28`。
- lite-only ELF 的 `main_tls=0x80003018`，目标应为 `0x80003030`，实际编码
  `rela rb8,2; addi +48` 形成 `0x80002030`；mallocng-linked ELF 的
  `main_tls=0x80006018`，目标应为 `0x80006030`，同样编码页差 `5` 形成
  `0x80005030`。
- mallocng ELF 的 `0x80005030` 原始字节为
  `00 01 00 02 00 03 00 04`，大端读取为 `0x1000200030004`，与 gem5 在
  `0x80000a24` 观察到的第一个异常字段一致。后续 `0xa000...` 是该错误字段
  参与 TLS 算术后的传播值。
- contract §4.8/ADR 规定 rela 页立即数为
  `((S+A)>>12) - ((P+4)>>12)`，low12 为 `(S+A)&0xfff`。当前 lld 对
  `R_PC` 的 `val=S+A-P` 使用 `(val+0x800)>>12`，在本例页内偏移跨越边界
  时少一页。
- 独立 subagent Hilbert 复核 Finding=Confirmed，并写入
  `.work/ML-014l-rela-page-cross-page/report.md`；未修改实现或受限文件。

### 本任务边界

- 仅完成根因诊断，不修改 LLVM/lld、QEMU、gem5、musl 或 patch series。
- 下一任务应只修正 `R_DADAO_RELA_PAGE` 的最终页号差，并保留 `RELA_LO` 的
  目标绝对 low12；先用最小跨页 ELF 和真实 musl mallocng startup 回归，暂不
  处理 `-O`、`puts`、free 或 ML-014a 的整体验收。
- mallocng 基本链路仍未通过；ML-014f/ML-014a 仍保持未完成。

## 审阅记录

### Subagent 自审（Hilbert，2026-07-18）

- Finding=Confirmed；报告包含具体 `P/P+4`、符号地址、实际/期望地址和
  rodata 原始字节。初稿将 `main_tls+0x18` 误写为 `align`，已按 reviewer
  对 `struct tls_module` 的核对更正为 `size`。
- 仅新增 `.work/ML-014l-rela-page-cross-page/report.md`，没有改实现、patch
  series、docs/issues.yaml 或 ML-014a。

### 独立 reviewer

（Codex，2026-07-18）

- **Finding=Blocked**：RELA_PAGE 根因本身被证据支持，但任务/报告把
  `.bss.main_tls + 0x18` 称为 `main_tls.align`，这是一个实质性字段偏移错误，
  需要在后续修订中纠正后才能按现文案 Accepted。
- **P/P+4 与指令位置**：独立查看
  `.work/build/musl/obj/src/env/dadao/__init_tls.o` 的
  `.text.static_init_tls`，目标 relocation 位于函数偏移 `0x16c`；已链接
  lite-only 和 mallocng-linked 两个 ELF 的 `static_init_tls` 均为
  `0x800008b0`，故 `P=0x80000a1c`，下一条 `RELA_LO` 为
  `0x80000a20`，后续 load 为 `0x80000a24`。该项成立。
- **符号地址和错误地址**：独立读取
  `.work/ML-014h-mmap-return-bridge/malloc_pointer.elf` 与
  `.work/ML-014i-musl-malloc-archive/malloc_pointer_after.elf`：
  `main_tls` 分别为 `0x80003018`、`0x80006018`；两者在 `0x80000a1c`
  均编码 `rela rb8, 2`、`rela rb8, 5`，配合 `addi +48` 形成
  `0x80002030`、`0x80005030`。目标 `main_tls+0x18` 分别为
  `0x80003030`、`0x80006030`，该项成立。
- **字段身份遗漏/反证**：`struct tls_module` 在
  `.work/source/musl/src/internal/libc.h:14-18` 的 64-bit 布局是
  `next@0x0, image@0x8, len@0x10, size@0x18, align@0x20,
  offset@0x28`；ELF 也报告 `main_tls` 大小为 48。故 `main_tls+0x18`
  首先读取的是 `main_tls.size`，不是 `main_tls.align`。现有证据支持“错误
  地址先污染 main_tls 的 TLS 元数据并继续传播”，但不能支持“首先污染
  main_tls.align”这一更具体表述；报告没有给出该字段映射的校验，属于遗漏。
- **rodata 字节**：独立从 mallocng-linked ELF 的 rodata 文件偏移
  `0x6030` 读取到 `00 01 00 02 00 03 00 04 ...`；大端 64-bit load 为
  `0x0001000200030004`，与报告记录的 `0x1000200030004` 数值一致。
  lite-only 对应 `0x3030` 全零，因此“布局掩盖错误”的解释成立。
- **RELA 公式**：`contracts/isa/spec.md §4.8` 明确 `rela` 基址为下一条
  指令 `P+4` 的页；因此配对语义应为
  `((S+A)>>12)-((P+4)>>12)`，low12 为 `(S+A)&0xfff`。当前
  `.work/source/llvm/lld/ELF/InputSection.cpp` 的 `R_PC` 路径形成
  `val=S+A-P`，而 `.work/source/llvm/lld/ELF/Arch/DADAO.cpp:120-122`
  再执行 `(val+0x800)>>12`。本例 `0x2614`/`0x5614` 分别得到 2/5，
  而目标页差应为 3/6；该项成立。报告建议覆盖 `P=page_end-4` 的
  `P+4` 跨页情形也是必要的。
- **范围检查**：报告明确 mallocng 仍为 startup `MALIGN=129`，且 ML-014f、
  ML-014a 未完成；没有越界宣称完成。除上述字段名/“首先异常字段”的错误
  外，未发现把实现修复或 ML-014a 验收写成已完成的遗漏。
- **审阅范围与变更**：本次只读检查上述既有 ELF、目标文件、源码和规范；未
  修改 LLVM、QEMU、gem5、musl、patch series、contracts、manifests、
  `docs/issues.yaml`、ML-014a，也未参考或传递 `~/toolchain`、
  `~/knowledge-graph`。

### 修订后的 reviewer 结论

字段映射已修正为 `main_tls.size`，并保留 reviewer 已确认的
`P/P+4`、页差、rodata 和范围证据。修订后的 ML-014l 诊断记录可接受；
实现修复仍需另行验证。

### 独立 reviewer 最终复核（Codex，2026-07-18）

- **Finding=Accepted**：执行阶梯、完成区和修订结论均已将
  `main_tls+0x18` 统一为 `size`，并补全 64-bit `struct tls_module` 布局；
  初次审阅指出的字段映射问题已充分修正。
- 既有 `P=0x80000a1c` / `P+4=0x80000a20`、lite-only 与 mallocng-linked
  的实际/期望地址、rodata 原始字节、大端解释，以及
  `((S+A)>>12)-((P+4)>>12)` 对比当前 lld 公式的证据均被保留，未发现新的
  逻辑矛盾或遗漏。
- 修订仍严格限定为 RELA_PAGE 根因诊断；没有把 mallocng、ML-014f 或
  ML-014a 宣称完成。实现修复和回归验证仍需后续任务完成。
