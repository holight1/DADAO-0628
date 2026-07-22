# ML-017c targeted partial archive/link/QEMU/Gem5 review

日期：2026-07-21（Asia/Shanghai）  
结论范围：ML-017a final d3bd fresh success=1166 的 partial archive、ML-016v
puts/link gate，以及 fixed write、puts、`_Exit`/return 的目标化 QEMU/Gem5 运行。
这不是完整 libc、完整 kernel 或 ML-014a 验收。

## 结论

ML-017a 的 `1166` 个 fresh success object 可以在新隔离目录中完整重建 partial
archive，archive/link/undefined/objcopy/disasm gate 全部通过。ML-016v 的 puts
probe 在 final d3bd fresh objects 上也能 link，并在 QEMU/Gem5 两端正常返回
`42`；ML-016v 中的 `MALIGN=129` 不再出现。

但高层 `puts` 没有真实输出 marker。独立旁路显示 `puts` 返回负值且
`__errno_location()` 读到非零 errno；旁路固定 `write` 仍真实输出。因此本轮把
问题精确归类为已进入 libc stdio/输出 API 的 runtime error，而不是 undefined
symbol/link failure、当前 simulator trap 或 host stdout 假设。该证据尚不能单独
证明 errno 的具体数值、底层 `writev`/fd 原因或完整 flush 语义。

## Facts

### 1. Fresh input and provenance

输入 manifest 是：

`/tmp/ml-017a-post-frame-musl-matrix-20260721/results/object-results.post-frame.enriched.tsv`

其 SHA-256 为 `964dcf67c7c30541bd5f84025c98498192f507117c8a910ca77cbf0be9605f3d`。
筛选条件为 `rc=0,result=success,artifact_fresh=yes`，得到 1166 行；每一行的
artifact hash 都重新对 `/tmp/ml-017a.../build/obj/<output>` 校验通过。该 fresh
success 清单不是旧 ML-016v archive 的输入。

| identity | value |
|---|---|
| LLVM HEAD | `d3bd9c15434fd7a48c0b7bab87354778cd932a72`，detached clean |
| musl source | `4741d4d1105849adf551a7998503866ed4f8b961`，clean copy |
| clang SHA-256 | `64a8067ec4de0794ad137919565ec7d632631719d2d6f9ef8a3357068ad743e6` |
| ld.lld SHA-256 | `c345424c32040dadbd529bd83a581436285ece63a3cbfbedd9b1a2fe98438956` |
| llvm-ar / ranlib SHA-256 | `9c897dc7ccc10e93de1ca8ef2f227115d2e236440005cf76dd2074cfa33ab8c4` |
| llvm-objcopy SHA-256 | `038a459905aa7a87d075b917ccd409e6096fe6ee7d6f91b5750f8d303a06824a` |
| llvm-nm SHA-256 | `ed2b2c6627794ef54c080ff5679c8df70ed9813fcf50f54a609c92dd71913ab3` |
| QEMU SHA-256 | `e270daaaa9ff0eed8856020840fa30856d28c35a5a3f487ddadcdf7cda448fb7` |
| Gem5 SHA-256 | `637ff701b5dd50b34304e18eb10f452ab9e06daf467c372310e8d302755174e7` |
| Gem5 config SHA-256 | `d30b90fe234b025c68992e965461aab6dd87806bd32af6ca7b7774c357b45c18` |

Frame lowering source hash is `a3ed13fcc5f03765e6980936454b2761f72efd7b55b44b9261f025d6c9882e6b`；
musl configure hash is `f911a9997e9ba565b9b8a25efa8bbd24dc7196b346a7122c6f06141fc19c5a37`。
完整 provenance 在 `/tmp/ml-017c-targeted-partial-archive-qemu-20260721/provenance/`。

### 2. Partial archive gate

新 archive：

`/tmp/ml-017c-targeted-partial-archive-qemu-20260721/archive/libc.partial.1166.d3bd.a`

SHA-256：`7403a3e8d98591d97455bb9500005cfea74f8e1b9e84037db312ae4067ffbd61`。

- object input：1166；member：1166。
- order：ML-017a manifest 的 output order；完整 order 在 `archive/object-inputs.tsv`
  和 `archive/member-list.txt`。
- `llvm-ar rc=0`，`llvm-ranlib rc=0`，member-list `rc=0`。
- 使用 `llvm-ar xN <occurrence> ... <basename>` 对重复 basename 做 occurrence-aware
  抽取；1166/1166 member hash 与输入 artifact hash 相同。
- `archive/partial-status.txt` 明确标记 `partial_incomplete`；没有接触主
  `.work/build/musl/lib/libc.a`。

主 archive 完成后只读 identity 仍为 SHA-256
`1b62bd670f481b0b46808639a65072021eca8f6d03d81adafa520e5c13ca07ee`，大小
1399820 bytes，mtime `2026-07-18 15:00:32.375253784 +0800`。

### 3. Fixture and build gates

ML-016v puts fixture 原样为 `puts("ML-016v puts smoke"); return 42;`，source
SHA-256 `6016e24a3623484efdfb30e0324fbd098a17a946ce3503edb14cc59f826ea91f`。
链接使用 ML-016v 的 linker script fixture（SHA-256
`bc3c1bf453ec0ddd6a4e0856c085930f1d12eeae3238a897f1c320f843d95b39`）、ML-017a
fresh `obj/crt/crt1.o`（SHA-256
`7ad77f97b6058154badc99b258321c99975e052ea5559585a079cd767852a1b5`）和本轮新
archive。

| probe | compile | link | undefined | objcopy | object/ELF disasm |
|---|---:|---:|---:|---:|---:|
| `write_fixed` | 0 | 0 | 0 / 0 lines | 0 | 0 / 0 |
| `puts_probe` | 0 | 0 | 0 / 0 lines | 0 | 0 / 0 |
| `main_exit` | 0 | 0 | 0 / 0 lines | 0 | 0 / 0 |
| `return_syscall` | 0 | 0 | 0 / 0 lines | 0 | 0 / 0 |
| `puts_return_bypass` | 0 | 0 | 0 / 0 lines | 0 | 0 / 0 |
| `puts_errno_bypass` | 0 | 0 | 0 / 0 lines | 0 | 0 / 0 |

The `puts_probe` link map resolves `puts` from the new archive's `puts.o` and pulls
the expected stdio chain (`fputs`, `fwrite`, `__towrite`, `__stdio_write`, stdout
and lock helpers). The final ELF undefined checks contain zero lines.

Representative final hashes:

| probe | ELF SHA-256 | BIN SHA-256 |
|---|---|---|
| `write_fixed` | `c23ce243cba1f4fccf39a69d359e4ac4221f73fab48a8578edee8c68775a4bd3` | `90025d26427c6ac3092ac2188bc4dcdc6a9a72ac2e8185b0311f6d96ee265027` |
| `puts_probe` | `fb4786effe1cde2413aa81603e2ab3373798e366f0b84a1c8894dfffa0dbe6ee` | `54a10cf69c6d9c35ca3036875186db7573d4ea11dbdfa191b26a5983c20ae872` |
| `main_exit` | `2848cb991874938246c3f2de8b70f959916f051a774ed32ad60117baa1514995` | `c99b441b92baae49b17ad806c5c339cfbc79fae3af4b732a7833a4b3b4985634` |
| `return_syscall` | `72d0ab69b53d7a10eb21e2bd212d4f108eedfcab6fe342a404bf9b84711b7577` | `54606f229099e3df031f54b46fc8c733870e2a0b2f47de6b5756d14db3710cd8` |

### 4. Runtime facts

Every runtime command used a 60-second timeout and completed before it. QEMU used
`qemu-system-dadao -M dadao-m1 -nographic -bios trampoline.bin -kernel <same-run BIN>`.
Gem5 used `gem5.opt tests/dadao/dadao_se.py <same-run ELF>` with the ELF as the
direct final argument; it did not use the QEMU trampoline/BIN or a launcher wrapper.
Raw traces and exact argv are under `runtime/<probe>/`.

| probe | QEMU stdout/result | Gem5 stdout/result |
|---|---|---|
| `write_fixed` | monitor plus `write-ok`; `rc=42`, no timeout | `SIM_START`, `SIM_END: trap-exit code=42`, `write-ok`; `rc=42`, no timeout |
| `puts_probe` | monitor only, no puts marker; `rc=42`, no timeout | `SIM_START`, `SIM_END: trap-exit code=42`, no puts marker; `rc=42`, no timeout |
| `main_exit` | monitor only; `rc=42`, no timeout | `SIM_START`, `SIM_END: trap-exit code=42`; `rc=42`, no timeout |
| `return_syscall` | monitor only; `rc=42`, no timeout | `SIM_START`, `SIM_END: trap-exit code=42`; `rc=42`, no timeout |
| `puts_return_bypass` | `PUTS_RC_ERR`; `rc=42`, no timeout | `SIM_START`, trap-exit, `PUTS_RC_ERR`; `rc=42`, no timeout |
| `puts_errno_bypass` | `PUTS_ERR_ERRNO_NONZERO`; `rc=42`, no timeout | `SIM_START`, trap-exit, `PUTS_ERR_ERRNO_NONZERO`; `rc=42`, no timeout |

The QEMU/Gem5 launcher-input hash record is
`runtime/launcher-input-hashes.sha256`; the raw simulator stderr contains only the
known Gem5 warnings/info and no fault, panic, or timeout.

## Inference and precise failure classification

1. **Undefined symbol/link failure：排除。** `puts_probe` compile/link/undefined/
   objcopy all pass; the map contains the archive `puts.o` and its high-level stdio
   dependencies.
2. **Simulator trap：排除为本轮 puts 结果的首要原因。** Both simulators return
   `42`; Gem5 reaches `SIM_END: trap-exit code=42`, not `MALIGN`, and the fixed-write,
   `_Exit` and return controls also complete.
3. **Simulator-only issue：不支持。** The same fresh launcher/config and both
   backends produce the fixed marker; the missing puts marker is reproduced as a
   puts negative return in both backends.
4. **High-level stdio/errno path：已证实。** The independent bypass calls the same
   `puts` and then reports `PUTS_RC_ERR`; the errno probe reports
   `PUTS_ERR_ERRNO_NONZERO`. The source implementation returns failure when its
   `fputs` or newline path fails, so this is a libc output API error with errno set.
5. **Flush/underlying syscall root cause：尚未完全分离。** The current evidence
   proves the API error and rules out a host-stdout assumption, but does not identify
   the exact errno value or prove whether the first failing internal operation is
   `writev`, fd/console semantics, buffering state, or another stdio condition.
   The fixed-write marker is only a positive control/diagnostic and is not a high-level
   output substitute.

## Comparison with ML-016v

| item | ML-016v | ML-017c |
|---|---|---|
| object source | ML-016u fresh objects | ML-017a fresh d3bd objects |
| partial archive SHA-256 | `530f3a8a7db8c10fba31704bab6b20a3fb706935100712210063e5224e233c74` | `7403a3e8d98591d97455bb9500005cfea74f8e1b9e84037db312ae4067ffbd61` |
| puts link/undefined/objcopy | pass | pass |
| QEMU puts runtime | `rc=129`, no marker | `rc=42`, no marker |
| Gem5 puts runtime | `rc=129`, `SIM_END: MALIGN code=129` | `rc=42`, `SIM_END: trap-exit code=42` |

The comparison supports that the final d3bd fresh targeted path no longer hits the
earlier ML-016v startup/frame MALIGN. It does not establish that frame rounding alone
fixes every runtime or that high-level stdout is complete; the input archive and
fresh-object provenance changed as required by this task.

## Boundaries / not covered

- The archive remains a 1166-member partial/incomplete archive; the remaining **181**
  ML-017a object failures were not repaired or relinked.
- `vfprintf.o` and `vfscanf.o` remain among the stdio matrix failures; no vfprintf/
  vfscanf or integer printf acceptance was run here.
- No claim is made for the 181 failure clusters, full musl/libc archive, full libc
  link, full kernel, or full kernel/userspace integration.
- No mallocng minimal probe was needed for this targeted gate; therefore this report
  makes no mallocng or ML-014a completion claim.
- No full stdout/flush contract, `fflush`, `fwrite` matrix, varargs, tail-call, or
  complete syscall/console ABI acceptance is claimed.
- The pre-existing untracked `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`
  was preserved and not edited.

## Evidence index

Primary directory: `/tmp/ml-017c-targeted-partial-archive-qemu-20260721/`

- archive: `archive/object-selection.tsv`, `object-inputs.tsv`, `member-list.txt`,
  `member-hashes.tsv`, `tool.rc`, `archive.sha256`;
- link: `link/*.{argv,rc,stderr,stdout,map,elf,bin}`;
- disassembly: `disasm/`;
- runtime raw traces: `runtime/<probe>/qemu.*` and `runtime/<probe>/gem5.*`;
- aggregate results: `results/build-summary.tsv`, `results/runtime-summary.tsv`;
- provenance: `provenance/` and `runtime/launcher-input-hashes.sha256`.
