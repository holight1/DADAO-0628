# ML-016f isolated musl clean rebuild review

日期：2026-07-21（Asia/Shanghai）

## 结论

已在 `/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/` 完成一次全新的隔离 configure + clean build，并等待 make 自然结束。

结论分两层：

- 可以重新生成一个包含 `fflush.o`、`fileno.o`、`__fdopen.o` 的静态 archive。隔离 archive 中还解析出 `fflush`、`fileno`、`__fdopen`，以及 `fdopen` 的 weak alias；四个独立 link-only probe 均为 `rc=0`。
- 不能生成“全部预期 musl object 均成功”的完整 archive。全量 `make` 原始 `rc=2`；逐对象记录为 1163 个成功、184 个失败。最终 archive 是仓库现有 best-effort packaging 边界内的 1162 个 `obj/src`/`obj/compat` 成功 object，而不是完整 musl archive。

这次没有把 link 成功解释为 stdio runtime 或 ML-014a 已修复；没有替换主 archive，也没有修改主 build、source、LLVM 或其他受限内容。

## 实际配置与命令

隔离 source 是当前 musl checkout 的提交 `4741d4d1105849adf551a7998503866ed4f8b961`，复制后 status clean。LLVM 工具版本为 clang/LLVM 22.1.8（assertions build）。实际配置为 `dadao`、`--disable-shared`，`nproc=6`。包装器的每次真实编译调用均执行现有 clang 加 `--target=dadao`，不改变 musl 的编译参数。

阶段命令和原始 rc：

| 阶段 | 实际命令 | rc |
|---|---|---:|
| configure | `CC=.../record-clang AR=.../llvm-ar RANLIB=.../llvm-ranlib source/configure --target=dadao --disable-shared --prefix=.../install` | 0 |
| clean build | `make -k -j6 lib/crt1.o lib/libc.a` | 2 |
| archive | `llvm-ar rc .../build/lib/libc.a <成功 object 列表>` | 0 |
| index | `llvm-ranlib .../build/lib/libc.a` | 0 |

对应的完整环境、命令、stdout、stderr 和 rc 文件：

- [configure.environment.txt](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/configure.environment.txt)、[configure.stdout](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/configure.stdout)、[configure.stderr](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/configure.stderr)、[configure.rc](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/configure.rc)
- [make.environment.txt](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/make.environment.txt)、[make.stdout](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/make.stdout)、[make.stderr](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/make.stderr)、[make.rc](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/make.rc)
- [config.mak](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/build/config.mak)、[build-identity.txt](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/build-identity.txt)

## 逐对象结果与失败归因

编译器包装器保存了每次实际 argv、输出路径、原始 rc、时间戳和对应 stderr。汇总为 [object-results.tsv](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/object-results.tsv)，其中成功/失败分别为 [object-results.success.tsv](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/object-results.success.tsv) 与 [object-results.failed.tsv](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/object-results.failed.tsv)。每个原始 stderr 和 record 在 [logs/compiler](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/compiler/)；成功 object 的大小、mtime、sha256 在 [object-artifact-manifest.tsv](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/object-artifact-manifest.tsv)。

失败不是 archive 工具失败，而是 LLVM DADAO 后端编译失败：make stderr 中可见 `fatal error: error in backend: unsupported library call operation`、`Cannot select` 和 `DADAO DAG->DAG Pattern Instruction Selection`。例如 `getcwd.o` 的原始 stderr 保留了 `dynamic_stackalloc` 选择失败和 clang frontend exit code 70 的完整诊断。失败签名索引见 [make-failure-signatures.txt](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/make-failure-signatures.txt)，单对象原始记录仍以 object-results.tsv 中的路径为准。

本次 stdio 目标对象全部编译成功，且其记录中的 stderr 原始文件为空：

| object | compiler rc |
|---|---:|
| `obj/src/stdio/__fdopen.o` | 0 |
| `obj/src/stdio/fflush.o` | 0 |
| `obj/src/stdio/fileno.o` | 0 |

## Archive 对照

隔离 archive：1162 个 members、1159 个不同 basename。主 archive：1002 个 members、1000 个不同 basename。隔离成功 object 清单见 [successful-object-paths.absolute.txt](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/successful-object-paths.absolute.txt)，archive member 清单见 [isolated.archive.members](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/isolated.archive.members)；主 archive 清单见 [main.archive.members](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/main.archive.members)。basename 差异见 [archive-member-basename-diff.txt](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/archive-member-basename-diff.txt)。

关键产物的原始 hash/size/mtime 在 [key-artifact-manifest.tsv](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/key-artifact-manifest.tsv)：

- 隔离：2506354 bytes，sha256 `ba58585aa09abcd9bb7f443486ec21098ade267acdbee3bc326cb5f2dcee5bbd`，2026-07-21 14:29:45 +0800。
- 主 archive：1399820 bytes，sha256 `1b62bd670f481b0b46808639a65072021eca8f6d03d81adafa520e5c13ca07ee`，2026-07-18 15:00:32 +0800。

归档工具原始文件为 [llvm-ar.rc](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/llvm-ar.rc)、[llvm-ar.stderr](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/llvm-ar.stderr)、[llvm-ranlib.rc](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/llvm-ranlib.rc)、[llvm-ranlib.stderr](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/llvm-ranlib.stderr)。两者 stderr 均为空、rc 均为 0。

隔离 archive 的 `llvm-nm -g --defined-only` 包含：

```text
T __fdopen
W fdopen
T fflush
T fileno
```

原始符号输出见 [isolated.archive.nm](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/isolated.archive.nm) 和 [isolated.key-symbols](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/isolated.key-symbols)。主 archive 没有这些关键符号，见 [main.archive.nm](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/main.archive.nm) 和 [main.key-symbols](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/main.key-symbols)。

## Link-only probes

探针源、实际命令、stdout/stderr、每个 archive 的 rc 均在 [probes](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/probes/)；命令总表为 [commands.txt](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/probes/logs/commands.txt)。探针只做目标链接，不运行 ELF：

| symbol probe | isolated archive | main archive |
|---|---:|---:|
| `fflush` | 0 | 1 |
| `fileno` | 0 | 1 |
| `fdopen` | 0 | 1 |
| `__fdopen` | 0 | 1 |

主 archive 的四个失败 stderr 都是 `ld.lld: error: undefined symbol: <symbol>`；隔离 probe 输出文件实际生成。该结果只证明静态链接解析边界，不证明 runtime 行为、ABI 完整性或 ML-014a。

## 边界

本任务没有修改主 `.work/build/musl`、musl source、LLVM/QEMU/gem5、contracts、vectors、issues、wiki 或 ML-014a；隔离副本和全部中间产物均在 `/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/`。当前剩余阻塞边界是编译器后端的 184 个对象失败，因此“包含三个 stdio object 的 archive”可复现，但“所有预期 musl object 的完整 archive”仍不可复现。
