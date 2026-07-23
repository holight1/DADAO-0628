# DL-071a：DADAO MC 立即数越界拒绝与边界测试

日期：2026-07-23

## 状态

已完成；独立 review 判决 **Accepted**。

## 背景

ML-024a 发现 `addi rd8, rd0, 4096` 的 `imms12` 超出
`[-2048, 2047]`，但当前汇编器静默截断为 0，造成
`AT_PAGESZ` 与测试期望同时错误却长期通过。修正调用点只能消除实例，不能消除
汇编器继续接受非法源码的系统性风险。

## Ownership 与约束

- 允许修改 `.work/llvm` 中 DADAO MC/AsmParser 立即数校验相关的最小文件、
  DADAO MC tests、`components/llvm/patches/` 新增下一号 patch 与 series、本
  task 完成区及对应 worker report。
- 不修改 ISA/ABI contract、QEMU、gem5、musl、kernel、wiki。
- 在 `.work/llvm` 当前 HEAD 上新增普通 commit；禁止 rebase、reset、am 重放
  历史或 amend 既有 commit。
- 先测试全部立即数字段的当前行为，不能只给 `addi 4096` 打特例。

## 目标

1. 建立立即数类型清单，至少覆盖 `imms12`、`immu12`、`immu16`、wyde position
   以及 branch/call 等复用 `imms12` 的指令。
2. 汇编器对常量越界给出明确 diagnostic 和非零退出；合法边界仍可汇编。
3. 符号/重定位表达式不得被错误当作立即常量拒绝。
4. 新增 MC 正/负测试，至少含：
   - `imms12`: -2048、2047 成功，-2049、2048、4096 失败；
   - `immu16`: 0、65535 成功，-1、65536 失败；
   - ML-024a 原始 `addi ...,4096` 失败。
5. 重建相关 LLVM 工具，运行新增测试、DADAO MC tests、E2E、differential、
   manifest/issues。
6. 导出普通 patch；从裸 pin 全量重放 LLVM series 并比较最终 tree。

## 验收

不能用编码后反汇编“看起来对”代替汇编期拒绝。worker 完成后必须由独立 reviewer
复核 diagnostic、边界、符号表达式、patch replay 和回归门禁。

## Worker 完成区（2026-07-23）

状态：**Worker complete，等待独立 review**。

### 实现

- LLVM commit：
  `72cb112b4c1eb4f00cb8e8facc78e5185edb1244`
  (`DADAO: diagnose out-of-range MC immediates`)。
- 为 DADAO 的全部显式 MC 立即数 operand 增加 TableGen
  `ParserMatchClass`：`imms12`、`immu12`、`imms18`、`immu16`、
  `immu6`、`imms24`、`wydepos`、`cfxcode6`，以及复用相同范围的
  `brtarget12/18/24`。
- matcher 对可绝对求值的常量表达式先求值再检查范围；不能绝对求值的符号表达式
  保持进入既有 fixup 路径。
- 越界时在源 operand 位置产生明确的范围 diagnostic 并非零退出，不再到 emitter
  静默截断。
- 新增 LLVM MC 正/负测试：
  `llvm/test/MC/DADAO/immediate-range-{valid,invalid}.s`。

审计确认修复前以下所有类型均会静默接受越界常量：有符号/无符号 12 位、
有符号 18/24 位、无符号 16/6 位、wyde position、CFX code，以及
branch/call 的 12/18/24 位复用字段。

### 测试

- 增量构建 `llvm-mc FileCheck`：PASS。
- 新增 MC 两项按文件内 RUN 命令直接执行：2/2 PASS；负测试确认
  `llvm-mc rc=1`、`FileCheck rc=0`。
- 项目 DADAO MC：14/14 PASS。
- LLVM 原生 `llvm-lit llvm/test/MC/DADAO` 仍因构建树缺少
  `bin/llvm-config` 无法启动，rc=2；未宣称完整 LLVM suite 通过。
- E2E 首轮 65/66，发现 `tp_probe.test` 两处
  `addi rd16, rd0, 0x5A5A` 依赖旧截断；按测试本意最小改为
  `setzw rd16, 0, 0x5A5A` 后目标测试 1/1、完整 E2E 66/66 PASS。
- differential：
  `AGREE(4-way)=200`、gem5/Sail 既有 out-of-slice skip 各 2、
  `DIVERGE=0`、`SAIL-DIVERGE=0`。
- `make manifest-check`：PASS。
- `make check-issues`：PASS（只读，未修改 issues）。

### Patch 与裸 pin 重放

- 新增
  `components/llvm/patches/0049-dadao-mc-immediate-range-validation.patch`
  并追加 `series`。
- patch SHA-256：
  `a2611309ddfc9804246a85593c04e5815de8a233b0964d5728785a244538bc74`。
- commit 与导出 patch 的 stable patch-id 均为
  `41721c9276c69392ac3f2720aea034b4c9b61620`。
- 从 manifest LLVM pin
  `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1`
  plain `git am`：49/49 PASS。
- 重放最终 tree 与当前 LLVM HEAD tree 均为
  `214c454ff1fcf163d95e0d72f5c7743b69374dcf`。
- `.work/llvm` clean；未修改 QEMU、gem5、musl、spec、wiki 或 issues。

完整命令、范围矩阵和首次 E2E 失败证据见
`docs/reviews/DL-071a-worker-report-20260723.md`。

## 独立 review

- 报告：`docs/reviews/DL-071a-independent-review-20260723.md`
- 判决：Accepted，无 blocking finding。
- 独立 clean build、范围/符号表达式矩阵、MC 14/14、E2E 66/66、
  differential、manifest/issues、patch-id 与裸 pin 49/49 replay 均通过。
- 原生 LLVM MC lit 目录仍因 build tree 缺少 `llvm-config` 未启动，不能扩大
  表述为完整 LLVM suite 通过。
- `immu6` 编码范围 `[0,63]` 已正确检查；multi-load/store 另有指令级
  count `[1,63]` 约束，`0` 的拒绝留给 DL-071b。
- `tp_probe` 的 `setzw 0x5A5A` 保持测试意图等价，不声称与旧非法编码逐 bit
  等价。
