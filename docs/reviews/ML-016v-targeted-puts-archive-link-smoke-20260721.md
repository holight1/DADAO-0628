# ML-016v targeted puts archive/link smoke review

日期：2026-07-21

## 结论

ML-016u 的 1166 个 fresh success object 已打包为明确 partial/incomplete archive。使用 ML-016u fresh `crt1.o`、当前 linker script 和 ABI 参数的最小 puts ELF compile、link、undefined 检查和 flat image 全部成功；因此按前置条件各执行一次既有 QEMU/Gem5 smoke。QEMU 与 Gem5 均 `rc=129`、无 timeout，Gem5 明确输出 `SIM_END: MALIGN code=129`，runtime smoke 未通过。

这不是完整 `libc.a` 重建、完整 libc link 或 ML-014a 验收结果。

## Evidence

工作目录：[`/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/)。

| gate | result |
|---|---|
| fresh success inputs | 1166/1166，manifest/artifact hash 一致 |
| `llvm-ar rc` | 0 |
| `llvm-ranlib rc` | 0 |
| archive member count | 1166 |
| puts compile rc | 0 |
| puts link rc | 0 |
| final undefined check | rc=0，0 lines |
| objcopy rc | 0，flat image 16628 bytes |
| QEMU | rc=129，no timeout |
| Gem5 | rc=129，no timeout，`SIM_END: MALIGN code=129` |

partial archive SHA-256：`530f3a8a7db8c10fba31704bab6b20a3fb706935100712210063e5224e233c74`。逐 object/member hash 分别见 [`archive/object-inputs.tsv`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/archive/object-inputs.tsv) 和 [`archive/member-hashes.tsv`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/archive/member-hashes.tsv)。compile/link/objcopy 的 argv、stderr、map、undefined 和 rc 均在 [`link/`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/link/)。双 backend 原始 argv/stdout/stderr/rc 在 [`runtime/`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/runtime/)。

## Boundary

本轮未写入主 archive，未修改 musl source、LLVM、QEMU/Gem5、contracts、vectors、issues、wiki、ML-014a 或既有测试；未新增测试，也未用旧 archive/ELF 冒充 fresh 结果。partial archive 不能代表完整 libc，runtime 失败不能上升为 puts runtime 或高层输出验收通过。
