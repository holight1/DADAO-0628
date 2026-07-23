# DL-071a：DADAO MC 立即数越界拒绝与边界测试

日期：2026-07-23

## 状态

待处理；依赖 IN-006a 先恢复 LLVM patch series 全量重放。

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
