# ML-016v：targeted puts partial-archive link/QEMU smoke

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：22/30）

## 背景

ML-016u fresh matrix 已有 1166 个成功 object、181 个 backend failures，其中
`puts.o` 已成功，stdio 114/116；完整 archive/link/runtime 仍不可进入。现在可以
在 `/tmp` 用成功 object 做受控 partial archive，目标化验证 `crt1 + libc partial +
puts` 的 link 边界，并在 link 成功时运行现有 QEMU/Gem5 bare-metal path；不能修改主
archive 或添加未经规范审查的新测试。

## 目标与 ownership

worker 只在 `/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/` 工作：

1. 从 ML-016u 成功 artifact 清单生成 partial `libc.a`，保存输入 object 列表、每个
   object hash、llvm-ar/ranlib rc、member 列表和 partial/incomplete 明确标记；不得
   覆盖主 `.work/build/musl/lib/libc.a`。
2. 用当前 linker、ML-016u crt1、musl headers/ABI 参数构造最小 `puts` user ELF；
   保存 compile/link/objcopy rc、argv、stderr、map/undefined symbols。若 link 失败，
   分类为缺 object、符号/ABI 或 syscall/runtime，不把失败当 runtime 结论。
3. 只有 link 与 flat image 成功时，才使用已有 QEMU/Gem5 执行入口做一次临时 smoke，
   保存两个 backend 的 rc/timeout/stderr/output；不新增测试向量、不修改 spec/issues/wiki。
4. 明确 partial archive 不能代表完整 libc archive，也不能替代 ML-014a 高层输出验收。

## 约束

- 只写本 task 完成区和 `docs/reviews/ML-016v-targeted-puts-archive-link-smoke-20260721.md`；
  其他 archive/ELF/log 放 `/tmp`。
- 不修改主 `.work/build/musl`、musl source、LLVM、QEMU/gem5、contracts、vectors、
  issues、wiki 或 ML-014a；不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不使用 `|| true`；每一阶段保留原始 rc，禁止使用旧 archive/旧 ELF 冒充新产物。

## 完成区

### worker 交付（2026-07-21）

状态：**Completed / archive-link-flat 成功，双 backend runtime smoke 失败**。

本轮所有产物只写在 [`/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/)。ML-016u fresh success manifest 的 1166/1166 个 object 均为 `artifact_fresh=yes`，实际 hash 与 manifest hash 一致。

#### Partial archive

- 生成 [`libc.partial.1166.a`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/archive/libc.partial.1166.a)，输入 object=1166、archive member=1166；明确标记为 `partial_incomplete`，不是完整 `libc.a`。
- `llvm-ar rc=0`、`llvm-ranlib rc=0`、member list `rc=0`；archive SHA-256：`530f3a8a7db8c10fba31704bab6b20a3fb706935100712210063e5224e233c74`。
- object hash 见 [`object-inputs.tsv`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/archive/object-inputs.tsv)，member hash 见 [`member-hashes.tsv`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/archive/member-hashes.tsv)：1166 行、extract failure=0、object/member mismatch=0；同 basename 的 `free.o`、`realloc.o`、`clone.o` 按 occurrence 单独核对。
- 未写入或替换主 `.work/build/musl/lib/libc.a`。

#### Minimal puts ELF

使用 ML-016u fresh `crt1.o`（SHA-256 `2c986f02946d7e117607e9d5a0b738b3a9960def45b67459b75beb8238ed13c2`）、当前 linker script 的 `/tmp` 副本和 ML-016u C99/freestanding/ABI 参数。

- compile `rc=0`；argv/stderr/rc 保存在 [`link/compile.*`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/link/)。
- puts link `rc=0`，生成 fresh ELF；argv/stderr/map 保存在 [`link/`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/link/)。
- final ELF undefined check `rc=0`，undefined symbol 行数=0；证据：[`undefined-symbols.txt`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/link/undefined-symbols.txt)。
- objcopy `rc=0`，生成 16628-byte flat image；证据在 [`link/objcopy.*`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/link/)。

#### QEMU/Gem5

因为 link 与 flat image 均成功，按任务要求各执行一次既有入口：QEMU 使用同次链接的 flat image，Gem5 使用同次链接的 ELF。两者均无 timeout，但 runtime 未通过：QEMU `rc=129`、无 puts marker；Gem5 `rc=129`，输出 `SIM_END: MALIGN code=129`、无 puts marker。原始 argv/stdout/stderr/rc 在 [`runtime/`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/runtime/)。

结论：partial archive、puts link、undefined check 和 flat image gate 成功；双 backend runtime smoke 失败。本结果不代表完整 libc archive、完整 link/runtime 或 ML-014a 验收通过。汇总见 [`results/summary.txt`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/results/summary.txt)。

独立 reviewer Plato the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016v-independent-review-20260721.md`。review 确认 partial archive
和 puts link 使用本轮 fresh inputs，QEMU/Gem5 均真实执行且 rc=129；finding 是一组
早期重复 basename 辅助抽取文件不可靠，正式 member hash/offset 校验已通过。
