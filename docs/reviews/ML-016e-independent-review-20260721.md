# ML-016e 独立 review（2026-07-21）

## 身份与范围

本 review 独立于 ML-016e worker，仅抽查关键证据，没有重做完整审计，也没有访问或引用 `~/toolchain`、`~/knowledge-graph`。只读复核了任务文件、worker review、当前 musl Makefile/config、主 obj/archive、`/tmp` 复现记录和仓库状态；本次只新增本 review 文件。

## 独立复核结果

1. Makefile/source 选择：当前 `src/stdio/*.c` 为 116 个；通过 `.work/build/musl` 的实际 Makefile 展开得到 116 个 `obj/src/stdio/*.o` expected object，source 与 expected 集合无差异。主 `obj/src/stdio` 只有 88 个，因此缺失 28 个。缺失清单与 worker review 一致，包括 `__fdopen.o`、`fflush.o`、`fileno.o`。

2. 主 obj/archive 层级：用 config 指定的 `/home/holight/DADAO-0628/.work/build/llvm/bin/llvm-ar` 读取主 archive，原始 member 数为 1002；主 obj 原始文件数为 1005。按 basename 对照，obj 中而 archive 中没有的正好是 `aio.o`、`aio_suspend.o`、`lio_listio.o`。stdio 的 28 个缺失项均同时缺失于主 obj 和 archive，所以不能归因于这 28 项的 archive selection；另有上述 3 个已存在 obj 未进入 archive，说明主 archive 不是当前 obj 快照的完整打包。

3. `/tmp` 独立编译与 rc：`compile-results.tsv` 显示 25 个原始 rc=0、3 个原始 rc=2。直接检查 raw 记录确认 `__fdopen.o`、`fflush.o`、`fileno.o` 均为 `ORIGINAL_RC=0` 且产物存在；`puts.o`、`vfprintf.o`、`vfscanf.o` 均为 `ORIGINAL_RC=2`，并保留 LLVM backend 原始诊断。`pack-current/status.tsv` 记录输入 1005、`llvm-ar rc=0`、`llvm-ranlib rc=0`、member 1005；加入 25 个成功编译的 stdio object 后为 1030。这里的 `find_rc=1` 是因为命令同时查找不存在的 `obj/compat`，不是 archive 工具失败；该非零 rc 已被记录，未被隐藏。

4. 保护文件状态：`.work/source/musl` 的 git status 为空；source Makefile、主 config 的 SHA-256 分别为 `58c8b95c...ab9e`、`cf64c040...6266`，与 worker 记录一致；主 archive SHA-256 为 `1b62bd67...07ee`，mtime/size 也与 worker 记录一致。根仓库当前 tracked diff 仅指向 `code-agent/tasks/ML-016-30-task-run-20260721.md`，没有指向 contracts、vectors、issues、wiki、LLVM/QEMU/Gem5 或 ML-014a 的 diff。当前还有一个 mtime 为 2026-07-18 的未跟踪 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`；它早于本任务，不能作为本 worker 修改它的证据。由于 `.work` 等路径可能被 ignore，且没有任务开始前的全仓快照，不能把当前 git status 表述为对所有历史修改的绝对证明。

## Findings / 过度推断

- worker 的主要结论得到独立支持：当前证据不支持 stdio manifest/wildcard 排除；28 个 stdio 缺失首次可定位到 object/编译输出层；主 archive 另有 3 个已有 object 缺失；`/tmp` 结果支持 partial/stale build output 假设。
- “archive packaging/input snapshot 层”是对 3 个已有 aio object 的层级定位，不是具体历史根因。没有历史逐对象构建/打包日志，不能断言究竟是陈旧 archive、不同的历史输入清单，还是构建顺序/失败处理造成的。
- `/tmp` 的成功编译只证明这 3 个 source 在该复现条件下可生成 object，不证明主构建当时必然应该成功，也不证明 archive 可链接、stdio runtime 或 writev runtime 已修复。
- “未修改任何受保护文件”应限定为“当前可见证据未发现 worker 对受保护文件的修改”；对 ignored 构建树及缺少 pre-task baseline 的历史变化，不应作绝对证明。

## 独立结论

**Accepted-with-findings**

关键证据充分且可复核；保留上述证据边界和历史根因未定的 findings。后续应进行隔离的 controlled rebuild，逐对象保存 rc，再按实际 object 清单重建 archive，并另行做 link/runtime 验收。
