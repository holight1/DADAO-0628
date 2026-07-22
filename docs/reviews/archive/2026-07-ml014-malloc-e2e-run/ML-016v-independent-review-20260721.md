# ML-016v targeted puts archive/link smoke：independent review

日期：2026-07-21

Reviewer：独立复核

## 结论

**Accepted-with-findings**。

交付满足本 task 的 archive、puts compile/link/undefined/objcopy 和双 backend smoke
证据要求，且边界声明正确；但双 backend runtime smoke 均失败，另有一组早期
重复 basename 抽取辅助文件与正式 member hash 证据不一致，需保留为 evidence
hygiene finding。该 finding 不改变 archive 本体的独立校验结果。

## 独立核对结果

证据根目录：
[`/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/`](/tmp/ml-016v-targeted-puts-archive-link-smoke-20260721/)。

### Partial archive

- `archive/partial-status.txt` 将产物标为 `partial_incomplete`，输入和 member 均为
  1166；明确声明不是完整 `libc.a`、runtime acceptance 或 ML-014a acceptance。
- `object-inputs.tsv` 有 1166 条数据行，所有 `artifact_fresh=yes`，actual object
  hash 与 manifest artifact hash 全部匹配。
- `llvm-ar rc=0`、`llvm-ranlib=0`、member-list `rc=0`；archive SHA-256 为
  `530f3a8a7db8c10fba31704bab6b20a3fb706935100712210063e5224e233c74`。
- 独立执行 `llvm-ar t` 得到 1166 个 member，和 `member-list.txt` 完全一致。
  `member-hashes.tsv` 有 1166 条数据行，`member_extract_rc=0`、hash match 和
  `member-validation.rc` 的 `bad_extract_rc=0`、`bad_object_member_match=0` 均一致。
- 对保存的 `archive/members-corrected/` 做了全量交叉核对：1166 个 `.o`、所有
  `extract.stderr` 为空，文件 hash 与 `member-hashes.tsv` 全部匹配。三组重复
  basename（`free.o`、`realloc.o`、`clone.o`）的第二 occurrence 也以 archive
  offset/size 直接读取并匹配对应 hash。

### puts compile/link/undefined/objcopy

- `link/compile.rc` 为 0；argv 使用 `--target=dadao`、C99、freestanding、musl
  headers 和本轮 ABI 参数，输出为本轮 `/tmp` 下的 `puts_probe.o`。
- `link/link.rc` 为 0；argv 明确使用 ML-016u fresh `crt1.o`、本轮
  `puts_probe.o` 和 `archive/libc.partial.1166.a`，并带 `--no-undefined`，输出
  为本轮 `puts_probe.elf`。
- `link/undefined.rc` 为 0，`undefined-symbols.txt` 为 0 bytes/0 lines。
- `link/objcopy.rc` 为 0；本轮 flat image `puts_probe.bin` 为 16628 bytes。
  evidence SHA-256 清单全部通过。

### QEMU/Gem5

| backend | argv/target | timeout | rc | stdout/stderr 结论 |
|---|---|---:|---:|---|
| QEMU | `qemu-system-dadao -M dadao-m1 -nographic -bios inputs/trampoline.bin -kernel link/puts_probe.bin` | 60s，`no` | 129 | stdout 只有 monitor banner/prompt，stderr 为空，无 puts marker |
| Gem5 | `gem5.opt tests/dadao/dadao_se.py link/puts_probe.elf` | 60s，`no` | 129 | stdout 含 `SIM_START`、`SIM_END: MALIGN code=129`，stderr 仅 warning/info，无 puts marker |

因此两 backend 的 `rc=129`、Gem5 `MALIGN code=129`、无 marker 均已由原始
argv/rc/stdout/stderr 复核；这是 runtime smoke failure，不是 runtime acceptance。

## Findings

1. **Runtime gate failed（明确、非误报）**：QEMU 和 Gem5 都以 129 结束，未观察到
   puts marker。该 task 允许在 link/flat 成功后暴露此 smoke 结果，但不能将本轮
   结果称为 runtime 或 ML-014a accepted。

2. **重复 member 的早期辅助文件不可靠**：`archive/test-289.member`、
   `test-294.member`、`test-927.member` 实际是 `llvm-ar` usage 输出，其 stderr
   报告 `N` modifier 用在错误 operation；旧的平铺 `archive/members/0289-free.o`、
   `0294-realloc.o`、`0927-clone.o` 也对应了第一次同名 member。正式的
   `member-hashes.tsv`、`members-corrected/`、`test-x/` 和 archive offset/size
   交叉核对显示 archive 本体及第二 occurrence 正确，因此这是证据清理/呈现
   问题，不是 partial archive 内容错误；后续引用应以 corrected extraction 和
   `member-hashes.tsv` 为准。

## 旧产物与边界检查

- `link/link.argv` 没有使用主 archive，而是直接使用本轮
  `archive/libc.partial.1166.a`；link map 也显示 `puts.o` 来自该 partial archive。
- QEMU 使用本轮 `puts_probe.bin`，Gem5、undefined check 和 objcopy 使用同一轮
  `puts_probe.elf`；ELF、flat image 的 stat/sha256 与证据清单一致，未发现旧 ELF
  冒充 fresh 结果。
- `inputs/tool-and-input-identity.txt` 中主 archive 的 hash/size/mtime 与当前只读
  检查一致，且 `partial-status.txt` 为 `main_archive_touched=false`；未发现主
  archive 被用于本轮 link 或被覆盖。
- 结果被正确限定为 partial archive + flat-link smoke；没有把 runtime failure
  误称为 runtime acceptance，也没有误称为 ML-014a acceptance。

