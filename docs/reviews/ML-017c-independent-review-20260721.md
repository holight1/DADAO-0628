# ML-017c independent review: targeted partial archive/QEMU/Gem5

日期：2026-07-21（Asia/Shanghai）  
Reviewer：independent reviewer  
范围：`ML-017c-targeted-partial-archive-qemu.md`、既有
`ML-017c-targeted-partial-archive-qemu-20260721.md`，以及
`/tmp/ml-017c-targeted-partial-archive-qemu-20260721/` 下的 archive/member/hash/link/
disasm/runtime/provenance evidence。未读取范围外的禁用目录，未修改 LLVM、musl、QEMU、
Gem5、spec、launcher 或 tracker。

## 结论

**Accepted-with-findings**。

本轮声明为 targeted partial archive/link/runtime gate 时可以接受：1166-member
partial archive 可复核地来自 ML-017a fresh success，主四个 probe 的编译、链接、
undefined、objcopy、object/ELF disassembly 和双后端运行均闭合，fixed `write`、
`_Exit`、return-valued syscall 均按预期完成。

但不能把本轮记为 high-level `puts` 输出成功。`puts` marker 在 QEMU/Gem5 均未出现，
return bypass 明确得到 `PUTS_RC_ERR`，errno bypass 明确得到
`PUTS_ERR_ERRNO_NONZERO`。`rc=42` 是 probe 的退出码，不是 puts 成功码。

## Findings

### B-1：阻塞 puts-success 子目标；不阻塞本轮已明确限定的 targeted gate

- `puts_probe` 两端均 `rc=42`、无 timeout、无 `ML-016v puts smoke` marker。
- `puts_return_bypass.c` 在同一链接产物中先调用 puts，再以 fixed `write` 输出；两端
  均输出 `PUTS_RC_ERR`。
- `puts_errno_bypass.c` 随后读取 `__errno_location()`，两端均输出
  `PUTS_ERR_ERRNO_NONZERO`。
- `write_fixed` 两端均真实输出 `write-ok`，Gem5 均记录
  `SIM_END: trap-exit code=42`；因此不能把缺失的 puts marker 归因于 simulator
  没有结束，也不能把 fixed-write 的成功替代为 puts 成功。

这足以把失败定位到已链接并运行的 libc stdio/output API 路径，而不是 undefined
symbol 或 startup/frame trap；但不能进一步确定具体 errno、首次失败的底层 syscall、
fd/console 语义或完整 flush 行为。若验收标准要求 puts marker 成功，本 finding 是
阻塞的；按本任务明确记录“puts runtime returns with errno, stdout marker not
observed”的 targeted 范围，它是已披露的结果，不导致整项 rejected。

### F-1：非阻塞 provenance 缺口：llvm-objdump 未纳入 tool hash

`disasm/*.argv` 使用 `/home/holight/DADAO-0628/.work/build/llvm/bin/llvm-objdump`，
且全部 disassembly rc=0；但
`provenance/tool-hashes.sha256` 没有该 executable 的 hash。clang、ld.lld、llvm-ar/
ranlib、llvm-objcopy、llvm-nm、QEMU、Gem5 及 Gem5 config 的 hash 均可验证，故这只
是 disassembler identity 的证据完整性问题，不改变已有 disassembly 结果。

### F-2：非阻塞 raw evidence 不完整：diagnostic bypass 不如主 probe 可复核

`puts_return_bypass` 缺少 `compile.rc`；`puts_errno_bypass` 缺少
`compile.rc`、`undefined.argv`、`objcopy.argv` 以及 object/ELF disassembly 的
`*.argv`。两者仍有 ELF/BIN、link rc、undefined rc/text、objcopy rc、disassembly
rc/text 和双后端 raw runtime，因此足以支持上述诊断；但既有 review 中“所有 raw
argv/rc”这一总括说法对 bypass 不准确。主四个 probe 的 raw 命令证据不受此缺口影响。

### F-3：非阻塞 fixture 文案过时

`inputs/main_exit.c` 的注释称使用“ML-016u-built musl `_Exit.o`”，但
`link/main_exit.map` 实际解析的是本轮
`archive/libc.partial.1166.d3bd.a(_Exit.o)`。实际链接 provenance 是 d3bd archive；
应修正文案以免把 fixture 注释误读为旧对象 provenance。

## 独立核验结果

### Archive selection、occurrence 与 hash closure

- ML-017a manifest SHA-256 为
  `964dcf67c7c30541bd5f84025c98498192f507117c8a910ca77cbf0be9605f3d`；独立筛选
  `rc=0,result=success,artifact_fresh=yes` 得到 1166 行，manifest 总对象数为
  1347，失败数为 181。
- `archive/object-selection.tsv` 与该筛选结果逐行、按顺序、按 artifact hash 完全
  相同；`object-inputs.tsv` 为 1166 条。
- 1166 个 ML-017a 源 object 逐一重算 hash，均匹配 object-inputs；1166 个 archive
  member 抽取文件逐一重算 hash，均匹配 `member-hashes.tsv`。`member-list.txt`、
  member hash basename/order、`llvm-ar t` 输出完全一致。
- 重复 basename `clone.o`、`free.o`、`realloc.o` 存在；occurrence-aware extraction
  evidence 的两次 `free.o` 抽取均 rc=0，且抽取出的大小不同，说明没有把 basename
  当作唯一 key。
- `llvm-ar rc=0`、`llvm-ranlib rc=0`、member-list rc=0、member validation 为
  `object_count=1166,member_count=1166,order_check_rc=0,member_hash_bad=0`；archive
  SHA-256 为
  `7403a3e8d98591d97455bb9500005cfea74f8e1b9e84037db312ae4067ffbd61`。
- `archive/partial-status.txt` 明确为 `partial_incomplete`，ar argv 的目标是隔离
  archive；当前主 `.work/build/musl/lib/libc.a` hash 仍为既有记录的
  `1b62bd670f481b0b46808639a65072021eca8f6d03d81adafa520e5c13ca07ee`。

### d3bd/musl/tool/launcher provenance

`provenance/llvm-head.txt` 为
`d3bd9c15434fd7a48c0b7bab87354778cd932a72`；ML-017a nested provenance 和
`/tmp/ml-017a.../source/.git/HEAD` 均为 musl
`4741d4d1105849adf551a7998503866ed4f8b961`，且 clean/status 记录一致。ML-017c
的 source/tool hash checks 对记录的路径均返回 OK。QEMU、Gem5、Gem5 config 和
trampoline 的 launcher-input hashes 也均可验证；F-1 是唯一发现的工具 hash 清单
遗漏。

### Link/disassembly/runtime semantics

主 probe `write_fixed`、`puts_probe`、`main_exit`、`return_syscall` 各自均有完整
compile/link/undefined/objcopy/object-disasm/ELF-disasm argv、rc、stderr/stdout；
compile/link/undefined/objcopy 两项 rc 均为 0，undefined lines 均为 0，双 disassembly
rc 均为 0。

`puts_probe.map` 解析到本轮 d3bd archive 的 `puts.o`，并包含 `fputs`、`fwrite`、
`__towrite`、`__stdout_write`、`__stdio_write`、`__errno_location` 等 stdio/output
链；这排除了“只声明未链接”的解释。object disassembly 也保留了各 caller 的
实际 call/trap 形态；`return_syscall.object.txt` 明确包含 `trap 2, 0`。

QEMU argv 使用同次链接的 BIN 和 `trampoline.bin`；Gem5 argv 以同次链接的 ELF
作为 `dadao_se.py` 的直接最终参数，`gem5.rc` 明确为
`input_mode=direct_elf_argument`，没有把 Gem5 运行写成 launcher/BIN 运行。

| probe | QEMU | Gem5 | marker/观察 |
|---|---:|---:|---|
| `write_fixed` | 42, no timeout | 42, no timeout | 两端 `write-ok` |
| `puts_probe` | 42, no timeout | 42, no timeout | 无 puts marker；正常 trap-exit |
| `main_exit` | 42, no timeout | 42, no timeout | 无 stdout marker；正常结束 |
| `return_syscall` | 42, no timeout | 42, no timeout | 无 stdout marker；正常结束 |
| `puts_return_bypass` | 42, no timeout | 42, no timeout | `PUTS_RC_ERR` |
| `puts_errno_bypass` | 42, no timeout | 42, no timeout | `PUTS_ERR_ERRNO_NONZERO` |

### Explicit boundaries

- archive 只有 1166 个成员，明确是 partial/incomplete；ML-017a 的 181 failures 未
  修复、未重链，也未作完整失败簇验收。
- manifest 中 `vfprintf.o`、`vfscanf.o` 均为失败行；本轮没有 vfprintf/vfscanf、
  varargs 或 integer printf acceptance。
- 本轮没有 mallocng 行为 probe，因此不覆盖 mallocng runtime，也不构成 ML-014a
  completion claim；不能把 archive 中存在若干 mallocng object 误读为 mallocng
  验收。
- 不覆盖 full musl/libc archive、full libc link、full kernel、kernel/userspace
  integration、完整 stdout/flush contract 或完整 syscall/console ABI。

## Evidence index

主证据目录：`/tmp/ml-017c-targeted-partial-archive-qemu-20260721/`。  
Archive closure：`archive/object-selection.tsv`、`object-inputs.tsv`、
`member-list.txt`、`member-hashes.tsv`、`tool.rc`、`archive.sha256`。  
Build/disasm：`link/`、`disasm/`、`results/build-summary.tsv`。  
Runtime：`runtime/<probe>/qemu.*`、`runtime/<probe>/gem5.*`、
`results/runtime-summary.tsv`；诊断 bypass 的 aggregate row 不完整，但 raw runtime
仍在各自目录。  
Provenance：`provenance/`、`runtime/launcher-input-hashes.sha256`。
