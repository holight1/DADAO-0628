# ML-016f 独立 review

日期：2026-07-21（Asia/Shanghai）

审查范围：任务说明、已有 review，以及
`/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/` 下的原始日志、逐对象记录、
归档清单、符号输出和 link-only probe。未访问或引用受禁路径；本次只写入本文件。

## 结论

**Accepted-with-findings**。

证据包足以接受“隔离构建边界、archive 工具状态和 stdio link-only 解析结果”这一
报告；不接受把该隔离 archive 解释为完整 musl archive。worker 已明确将它称为
best-effort archive，并明确记录完整 archive 因 184 个编译失败而不可生成，因此没有
发现“把 partial archive 当完整 archive”的错误。

## 独立核验

| 项目 | 独立结果 | 证据 |
|---|---:|---|
| configure | `rc=0` | [`logs/configure.rc`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/configure.rc) |
| 全量 make | `rc=2` | [`logs/make.rc`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/make.rc) |
| 逐对象编译成功 | `1163` 个 `rc=0` | [`results/object-rc-distribution.txt`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/object-rc-distribution.txt)、[`results/object-results.success.tsv`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/object-results.success.tsv) |
| 逐对象编译失败 | `184` 个 `rc=1` | [`results/object-results.failed.tsv`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/object-results.failed.tsv) |
| llvm-ar | `rc=0`，stderr 为空 | [`logs/llvm-ar.rc`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/llvm-ar.rc)、[`logs/llvm-ar.stderr`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/llvm-ar.stderr) |
| llvm-ranlib | `rc=0`，stderr 为空 | [`logs/llvm-ranlib.rc`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/llvm-ranlib.rc)、[`logs/llvm-ranlib.stderr`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/llvm-ranlib.stderr) |

`object-results.tsv` 的逐行重算为 1163/184（加表头共 1348 行）。失败 stderr 的
签名是 LLVM DADAO backend 的 `unsupported library call operation`、`Cannot select`
等，而不是 archive 工具错误；例如 `getcwd.o` 的原始记录保留了完整 backend 诊断。
三个 stdio 对象在 compiler record 中均为 `rc=0`，对应 stderr 文件均为 0 字节：
`obj/src/stdio/__fdopen.o`、`fflush.o`、`fileno.o`。

## 1163/184 与 archive 成员数的范围差异

该差异可以由原始清单解释，不是计数算术错误：

- 1163 个成功编译记录包含 `obj/crt/crt1.o`。
- 归档脚本实际只从 `obj/src` 和可用的 `obj/compat` 收集 `.o`，所以成功对象路径和
  archive 都是 1162 个。
- [`results/compiler-vs-package-object-diff.txt`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/compiler-vs-package-object-diff.txt)
  只有 `obj/crt/crt1.o`，没有 package-only 对象；失败路径与 package 路径的交集也为
  0。
- [`results/isolated.archive.members`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/results/isolated.archive.members)
  为 1162 个 members、1159 个不同 basename；`clone.o`、`free.o`、`realloc.o` 的重复
  basename 来自不同目录路径。

因此 review 中的“1163 成功、最终 libc.a 为 1162 个 `obj/src`/`obj/compat` object”
是可同时成立的；后续引用这两个数字时应保留该范围说明。

## 指定 link-only 证据

原始命令使用 `--target=dadao -nostdlib -fuse-ld=lld -Wl,--no-undefined`，只生成
ELF，不执行 probe。结果如下；`fdopen` 是额外核验项。

| probe | isolated archive | main archive |
|---|---:|---:|
| `fflush` | `rc=0` | `rc=1` |
| `fileno` | `rc=0` | `rc=1` |
| `__fdopen` | `rc=0` | `rc=1` |
| `fdopen` | `rc=0` | `rc=1` |

isolated link stderr 均为空；main archive 的失败 stderr 均为对应的
`ld.lld: error: undefined symbol`。独立读取 isolated archive 也得到：

```text
T __fdopen
W fdopen
T fflush
T fileno
```

这只证明静态 link 解析，不证明 runtime、ABI 或 ML-014a。原始 probe 命令和 rc 见
[`probes/logs/commands.txt`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/probes/logs/commands.txt)
及 [`probes/logs/`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/probes/logs/)。

## Findings

1. **Clean-start provenance 不完整（低至中严重度）。** `run-configure.sh` 和
   `run-make.sh` 的已保存脚本只创建目录并运行 configure/make，没有保存初始 build
   树清场命令或初始 `.o` inventory；归档脚本按当前存在的 `.o` 收集。当前
   `compiler-vs-package-object-diff` 和失败路径交集检查没有发现 stale/failed object
   被打包，但它们不能单独证明 build 目录在 configure 前为空。严格要求 clean rebuild
   时，应补充初始清场或初始清单证据。

2. **归档命令日志不是严格可重放文本（低严重度）。** [`logs/archive.command.txt`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/logs/archive.command.txt)
   将 `find ... -name *.o` 写成未加引号的 glob；实际 [`tools/package-archive.sh`](/tmp/ml-016f-isolated-musl-clean-rebuild-20260721/tools/package-archive.sh)
   使用的是 `-name '*.o'`，随后从已排序路径列表调用 `llvm-ar`。实际执行和 rc 有独立
   证据，故不影响本次 rc/成员结论，但 command log 应与实际 shell 命令保持一致。

最终边界仍是：archive 工具成功，三项 stdio 对象和 link-only 符号可复现；184 个
backend 编译失败使“所有预期 musl object 的完整 archive”未完成。
