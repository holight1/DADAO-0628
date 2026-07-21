# ML-016z final-head varargs provenance report

日期：2026-07-21

结论：**B1/B2 已闭合。** 新的 varargs compile/link/objcopy/disasm 和双后端运行均在
final nested HEAD 上重新执行；旧 ML-016y 提交前证据未被覆盖，也未被重新表述为
final-head 证据。

## Final HEAD 与 source manifest

证据目录：[`/tmp/ml-016z-final-head-varargs-provenance-20260721/`](/tmp/ml-016z-final-head-varargs-provenance-20260721/)

- nested HEAD：`d3bd9c15434fd7a48c0b7bab87354778cd932a72`
- parent：`be99e5505abe341100c62d70cd955b2df7e4711e`
- nested status：`## HEAD (no branch)`，clean
- production source：`a3ed13fcc5f03765e6980936454b2761f72efd7b55b44b9261f025d6c9882e6b`
- LLVM regression source：`6e871fa22863278808e77c2acbc33142555d4dbeb54fe6c884cbc39d55eb4e80`

明确命名的新 manifest：
[`final-head-source-manifest-20260721.txt`](/tmp/ml-016z-final-head-varargs-provenance-20260721/manifests/final-head-source-manifest-20260721.txt)
和用于校验的
[`final-head-source.sha256`](/tmp/ml-016z-final-head-varargs-provenance-20260721/manifests/final-head-source.sha256)。
`sha256sum -c` 对两条 source 均输出 `OK`。旧目录中的
`/tmp/ml-016y-frame-rounding-fix-20260721/hashes/final-source.sha256` 保持为历史
证据，没有覆盖；它不再作为 final-head source manifest 使用。

## Final-head 重跑链

`ninja -C .work/build/llvm clang llc` 在该 HEAD 上 rc=0，clang VCSVersion 为该
`d3bd9c...`。有效 final-head 命令均保存于 `logs/`，每个命令的 argv 首部写明 HEAD
和两条 source hash；stdout/stderr/rc 及其哈希由
[`final-head-command-logs.sha256`](/tmp/ml-016z-final-head-varargs-provenance-20260721/hashes/final-head-command-logs.sha256)
覆盖。

| 阶段 | rc | 证据 |
|---|---:|---|
| clang C → IR | 0 | `static/varargs_min.ll` |
| llc → MIR | 0 | `static/varargs_min.mir` |
| llc → assembly（`-filetype=asm`） | 0 | `static/varargs_min.s` |
| llc → object | 0 | `build/varargs_min.llc.o` |
| clang C → object | 0 | `build/varargs_min.clang.o` |
| final llvm-mc → crt0 object | 0 | `build/crt0.final-head.o` |
| lld + crt0 + varargs object → ELF | 0 | `artifacts/varargs_final_head.elf` |
| llvm-objcopy → BIN | 0 | `artifacts/varargs_final_head.bin` |
| llvm-objdump disasm | 0 | `static/varargs_final_head.disasm` |
| source manifest SHA-256 check | 0 | `logs/verify-final-head-source-manifest.*` |

最终 ELF hash 为 `255649528ed07019737e5530e89f2eaeb2404308341a0b75008706081667661c`，
BIN hash 为 `35fb09087d8914d9f21031beb97d23fade4c1ab3c85abf0e282cd032e2414e26`。

## 双后端 final-head runtime

新 runtime source 副本的 `main` 实际调用 `varargs_frame(1, -1)`，该 `va_start/va_arg`
正常路径期望返回 0；source hash 为
`548b6450130258b276e3c8607b084b22e4d6006e698e369a24a7f414271d7434`。

| 后端 | rc | 结果 |
|---|---:|---|
| QEMU | **0** | halt，无额外程序 stdout；raw stdout/stderr 已保存 |
| Gem5 | **0** | raw trace 含 `SIM_END: halt code=0` |

QEMU 使用 ML-016v trampoline launcher：
`/tmp/ml-016w-malign-runtime-consistency-audit-20260721/launcher/ml-016v-trampoline.bin`，
hash `44042fabb2741724828443d7ae13bd42e3931e88d8be7f2f7dc48be3d851f5e0`；Gem5 不使用该
launcher，而是直接加载 final-head ELF，并记录 Gem5 binary、script 与 ELF hash。
QEMU、Gem5、launcher、ELF/BIN 的输入和产物 hash 在
[`final-head-runtime-inputs-and-artifacts.sha256`](/tmp/ml-016z-final-head-varargs-provenance-20260721/hashes/final-head-runtime-inputs-and-artifacts.sha256)。
完整 argv、raw output/trace、rc 位于 `logs/qemu-varargs-final-head.*`、
`logs/gem5-varargs-final-head.*` 和 `runtime/{qemu,gem5}/`。

## odd/padding=4 静态边界

最终生成 MIR 中最小 odd 形状 `varargs_one_local` 的观察值为：

`stackSize=4`，fixed varargs save size `120`，`roundUp(4+120,8)=128`，因此
`lower padding=4`，最终 `alignDown(4,8)=0`。计算输出在
[`varargs_odd_padding4_static_probe.txt`](/tmp/ml-016z-final-head-varargs-provenance-20260721/static/varargs_odd_padding4_static_probe.txt)。

该函数 `hasVAStart=false`，所以此形状只作静态边界 probe，不声称 odd runtime 安全；
实际 `va_start/va_arg` 的 `varargs_frame` 在 final assembly/MIR 中使用 `-152/+152`，
save stores 从 `rb1+0` 开始并保持 8-byte 对齐。没有伪造 padding=4 的 QEMU/Gem5 结果。

## direct/wrapper/exit 轻量 provenance

用 final HEAD 的 llc 对既有 IR 重新生成静态 assembly，三条命令均 rc=0：

- `direct_syscall1`：helper `-40/+40`；
- `wrapper_noreturn`：外层 `-8`，helper `-40/+40`；
- `exit_shape`：外层 `-8`，helper `-40/+40`。

输出和输入 hash 在
[`lightweight-final-head-provenance.sha256`](/tmp/ml-016z-final-head-varargs-provenance-20260721/hashes/lightweight-final-head-provenance.sha256)。
按任务要求没有重跑这些 fixture 的完整双后端矩阵。

## B1/B2 closure 与失败边界

- **B1**：旧的 `final3` runtime 发生在 final commit 产生前；本报告的新 IR/MIR/object/
  assembly/ELF/BIN/disasm 和 QEMU/Gem5 均由 HEAD=`d3bd9c...` 的工具链在该 HEAD 绑定
  日志下重新生成，runtime 使用的新 ELF/BIN hash 也已绑定到日志和 launcher hash。
- **B2**：新增的 final-head source manifest 记录当前 production/test source hash，
  并以 `sha256sum -c` 验证；没有覆盖旧 ML-016y source/hash 文件。
- 本次新证据目录中所有权威 final-head 阶段和两端 runtime 均 rc=0。

新目录中出现的非零 rc 均为非权威尝试，原因真实如下：

1. `llc-varargs-min-final-head-assembly.rc=1`：误用该版本不支持的 `llc -S`，stderr
   明确为 unknown argument；随后使用合法 `llc -filetype=asm` rc=0。
2. `llc-varargs-odd-padding4-final-head.rc=134`：将 pre-PE MIR 错误地作为可独立运行
   的合成输入，LLVM 在解析 `main` 的未定义物理 `rd31` 时 abort；未将该输出当成结果。
3. 依赖上述缺失输出的 `odd-padding4-static-check-final-head.rc=1` 是 grep 找不到
   产物；最终使用 final-head 生成 MIR 的算术静态分析 rc=0，并明确不做 runtime 声明。

ML-016y 历史目录中的 `llvm-lit` rc=2（缺少 `llvm-config`）仍是基础设施边界，本任务
没有把它改写成通过，也没有声称完整 LLVM suite、musl 或完整 E2E/differential 矩阵通过。

## 变更边界与剩余边界

没有提交 nested LLVM commit；nested LLVM 生产工作树保持 clean。没有修改
`.work/source/llvm`、musl、QEMU/Gem5、spec、launcher、LLVM regression 或 tracker。
本任务只新增 canonical task 与本 report；历史 ML-016y report 未修改。

剩余边界是 odd/padding=4 形状没有安全 runtime 入口，以及更复杂的 overflow argument、
动态 stack object、异常路径和完整 suite 未覆盖；这些不影响本次 B1/B2 provenance closure。
