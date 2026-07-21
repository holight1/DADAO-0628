# ML-016b worker report：musl output API linkability

日期：2026-07-21

本轮使用当前 `.work/build/musl/lib/libc.a` 做只读符号审计，并在
`/tmp/ml-016b-musl-output-api-linkability-20260721/` 生成临时 probe；未修改
主线组件或 ML-014a。

| probe | clang | link | objcopy | QEMU | Gem5 |
|---|---:|---:|---:|---:|---:|
| `puts("puts-ok")` | 0 | 1 | N/A | N/A | N/A |
| `fputs("fputs-ok", stdout)` | 0 | 0 | 0 | rc=42/no timeout | rc=42/no timeout |
| `printf("value=%d", 42)` | 0 | 1 | N/A | N/A | N/A |
| fixed `write` | 0 | 0 | 0 | rc=42/no timeout | rc=42/no timeout |

原始 link error：

- `puts`：`undefined symbol: puts`。
- integer-only `printf`：`undefined symbol: vfprintf`。

符号审计显示 `write`、`fputs`、`printf` 有定义，`puts` 无精确符号，
`vfprintf` 只有未定义引用。`fputs` 两后端虽然 rc=42，但没有 `fputs-ok`
marker；固定 `write` 两端实际输出 `write-ok`。

结论：固定 `write` 仅作为诊断 fallback；ML-014a 要求的高层输出路径仍未通过。
