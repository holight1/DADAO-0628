# ML-017c：targeted partial archive/link/QEMU/Gem5 gate

日期：2026-07-21（Asia/Shanghai）  
范围：使用 ML-017a final d3bd HEAD 的 fresh success=1166 对象，重建隔离
partial archive，并复用 ML-016v puts/link fixture 做 archive、link、fixed-write、
puts、`_Exit`/return 和 QEMU/Gem5 targeted gate。

## 约束与 ownership

- 只在 `/tmp/ml-017c-targeted-partial-archive-qemu-20260721/` 生成 archive、
  object、ELF、BIN、raw trace 和 provenance。
- 仓库内只新增本 task 与对应 review；不修改 LLVM/musl/QEMU/Gem5/spec/launcher/
  docs/issues.yaml/wiki/30-task tracker/已有生产文件。
- 不使用或引用 `~/toolchain`、`~/knowledge-graph`；不生成 nested source commit。
- archive 明确为 partial/incomplete，不能代表完整 libc 或 ML-014a。

## 验收结果（2026-07-21）

状态：**Audit-accepted-with-findings / archive-link successful / fixed-write successful /
puts runtime returns with errno, stdout marker not observed**。独立 review 接受限定
范围 targeted gate；puts-success 仍是 blocking 子目标。

### Archive

- 输入：`/tmp/ml-017a-post-frame-musl-matrix-20260721/results/object-results.post-frame.enriched.tsv`。
- fresh success 输入和 archive members 均为 **1166**；输入路径和 manifest artifact
  hash `1166/1166` 匹配。
- order、object hash、occurrence-aware member hash 均通过：`object_count=1166`、
  `member_count=1166`、`order_check_rc=0`、`member_hash_bad=0`。
- `llvm-ar rc=0`、`llvm-ranlib rc=0`、member list `rc=0`。
- archive：`/tmp/ml-017c-targeted-partial-archive-qemu-20260721/archive/libc.partial.1166.d3bd.a`
  SHA-256 `7403a3e8d98591d97455bb9500005cfea74f8e1b9e84037db312ae4067ffbd61`。
- object order、expected artifact hash、member list 和 member hash 分别保存在
  `archive/object-inputs.tsv`、`archive/member-list.txt` 和
  `archive/member-hashes.tsv`；未写入主 `.work/build/musl/lib/libc.a`。

### Link/runtime

四个主 probe（`write_fixed`、ML-016v 原样 `puts_probe`、archive `_Exit` 的
`main_exit`、return-valued syscall 的 `return_syscall`）均为：compile/link/
undefined/objcopy/object-disasm/ELF-disasm `rc=0`。QEMU 使用同次链接的 BIN；
Gem5 使用同次链接的 ELF 直接参数，未记录为 launcher 运行。

| probe | QEMU | Gem5 | 观察 |
|---|---:|---:|---|
| `write_fixed` | `rc=42`, no timeout | `rc=42`, no timeout | 两端真实 `write-ok` |
| `puts_probe` | `rc=42`, no timeout | `rc=42`, no timeout | 无 puts marker；Gem5 `SIM_END: trap-exit code=42` |
| `main_exit` | `rc=42`, no timeout | `rc=42`, no timeout | 无 stdout marker；正常 trap-exit |
| `return_syscall` | `rc=42`, no timeout | `rc=42`, no timeout | 无 stdout marker；正常 trap-exit |

独立诊断（不替代原始 puts gate）：

- `puts_return_bypass` 两端 marker 为 `PUTS_RC_ERR`。
- `puts_errno_bypass` 两端 marker 为 `PUTS_ERR_ERRNO_NONZERO`。
- 两个诊断均 compile/link/undefined/objcopy/disasm `rc=0`，QEMU/Gem5 均 `42`、
  no timeout；固定 `write` 旁路仍可用。

## Evidence

完整 report：`docs/reviews/ML-017c-targeted-partial-archive-qemu-20260721.md`。
所有 raw argv/rc/stdout/stderr、ELF/BIN hash、disassembly、map 和 provenance 在
`/tmp/ml-017c-targeted-partial-archive-qemu-20260721/`。
