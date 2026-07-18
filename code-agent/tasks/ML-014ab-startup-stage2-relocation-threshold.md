# ML-014ab：startup stage2 地址物化的最小阈值与重定位诊断

**执行环境**：本地 subagent worker；承接 ML-014aa 的 startup→main 未命中

**状态**：Ready（30-task run：8/30）

## 目标

在不运行 allocator、不中改 LLVM/lld 实现的前提下，找出
`libc_start_main_stage2` 间接调用错误地址的最小代码布局/页边界触发条件，区分
“输入对象中的 relocation/地址物化错误”和“链接后 RELA_PAGE/RELA_LO 计算错误”。

## Ownership

- worker 只写 `.work/ML-014ab-*` 派生 probe/runner/trace 与本 task MD。
- 可使用锁定 clang/lld/crt1/libc.a/script 产生最小 ELF；不得修改实现源码、root
  tests、patches、issues、contracts、manifests 或 ML-014a。
- 不运行 malloc/free 语义验证，不宣称 mallocng 已解决；不查阅或引用
  `~/toolchain`、`~/knowledge-graph`。
- 多人共享仓库，不回滚他人改动；完成后提交本 task MD 及本任务专属 artifacts。

## 执行阶梯

1. 以 ML-014aa/Accepted ML-014y 的 startup layout 为基线，构造尽可能小的
   stage2 地址物化样本；用 object/ELF readobj、反汇编、map/symbol 记录
   `RELA_PAGE`/`RELA_LO`、P、S、A 与最终指令。
2. 通过受控 padding/section 排布或等价最小源程序，让 stage2/调用点跨越相邻
   4 KiB 页及 signed-low 边界；至少保留一个成功布局和一个失败布局。
3. 在 QEMU 与 gem5 各跑一次失败/成功样本，确认动态目标是否分别为预期函数和
   `0x7ffff...` 栈地址；若运行不是必要条件，明确标为静态结论。
4. 给出首个可证明差异、当前最可能的责任层级和下一修复任务边界；不得在本任务
   直接改 linker/compiler。

## 验收

- 至少一对可复现的 success/failure layout，或有充分证据说明无法构成且给出原因。
- 同时保存 relocation decode 与双后端结果；不以 host rc 代替 guest 行为。
- 结论必须区分事实、推断和未决项，并由独立 reviewer 复核。

## 完成区

（由 worker 填写；完成后由不同 subagent 独立 review）
