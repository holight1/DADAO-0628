# ML-014e: 固化 mmap backing 判别性双后端 probe

**执行环境**：本地 subagent worker；测试 ownership only

**状态**：待处理

## 目标

把 ML-014c/ML-014d 使用过的临时 hand-assembled probe 固化为
`tests/lit/E2E/mmap_backing_probe.test`，用一个可提交的 lit 测试同时验证：

- 固定 arena 地址返回与页对齐；
- 两次不同长度 mmap 的单调 cursor；
- 至少两个映射、跨页首尾位置的真实 `sto/ldo` 写读；
- 零长度、页对齐溢出、容量超限等明确失败路径；
- `munmap`/`mprotect` 的当前 M1 语义；
- QEMU 与 gem5 两个后端都以明确 exit=42 和成功标记结束。

## Ownership

- 允许修改：`tests/lit/E2E/mmap_backing_probe.test`、必要的测试输入/README、
  本任务 md 的完成区和 review 记录。
- 不允许修改：QEMU、gem5、LLVM、musl、contracts、manifests、
  `docs/issues.yaml`、既有测试文件、patch series。
- 不得通过 `|| true`、忽略退出码、只检查文本或只运行一个后端来凑绿。
- 不得把测试改成依赖 musl/printf/varargs；基础设施 probe 必须保持 raw
  hand-assembled，避免把 libc 或 CodeGen 问题混入 mmap backing 验收。

## 验收

- `llvm-lit -v tests/lit/E2E/mmap_backing_probe.test`：QEMU/gem5 均真实通过，
  exit=42，输出成功标记。
- 代码中存在多个独立 marker 的写读和跨页判定，测试失败码可定位到具体阶段。
- 临时删除/禁用 backing 的 mutation 能使 probe 失败（只在 `.work` 验证，不提交
  mutation）。
- 全量 `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E` 保持 59/59。
- `python3 tools/run_differential.py` 保持四方 200、DIVERGE=0。
- 完成区必须贴真实命令与退出码；返回前必须填写 `## 审阅记录（subagent）`。

## 参考

- `docs/reviews/mmap-backing-recon-2026-07-18.md` §4
- `code-agent/tasks/ML-014c-qemu-mmap-backing.md`
- `code-agent/tasks/ML-014d-gem5-mmap-backing.md`
- `tests/lit/E2E/mmap_probe.test`
- `tests/lit/E2E/lit.cfg`
- `reviewer.md`

## 完成区

**状态**：待处理

**修改文件**：

**验收结果**：

**遗留问题**：

## 审阅记录（subagent）

> 必须由独立 reviewer 填写真实代码审查、命令输出、finding 处置和判决。

