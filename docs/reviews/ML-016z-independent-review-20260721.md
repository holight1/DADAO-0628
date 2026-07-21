# ML-016z 独立 reviewer 报告

日期：2026-07-21

身份：ML-016z 独立 reviewer。审阅了任务说明、既有 report 与证据目录；未读取
`~/toolchain` 或 `~/knowledge-graph`，未修改 LLVM、musl、QEMU、Gem5、spec、
launcher 或 tracker。本文是唯一新增文件。

## 结论

**Accepted-with-findings**。

ML-016y 的两个 blocking finding（B1 final-commit provenance、B2 stale source
hash）在实质上已闭合。final-head 的 compile/link/objcopy/disasm 和正常 varargs
QEMU/Gem5 运行均有独立可复核的 argv、rc、输出与 hash。odd/padding=4 只保留了
静态边界分析，没有被写成 runtime 通过。

没有发现新的阻塞性功能或 provenance 证据缺口；但有两项非阻塞的审计/表述问题，
见下文 findings。

审阅对象：

- [任务说明](/home/holight/DADAO-0628/code-agent/tasks/ML-016z-final-head-varargs-provenance.md)
- [既有 final-head report](/home/holight/DADAO-0628/docs/reviews/ML-016z-final-head-varargs-provenance-20260721.md)
- [证据目录](/tmp/ml-016z-final-head-varargs-provenance-20260721/)
- [ML-016y 独立 review](/home/holight/DADAO-0628/docs/reviews/ML-016y-independent-review-20260721.md)

## 独立核验结果

### 1. HEAD、source hash 与 clean 状态

证据目录中的 `final-head-rev.stdout` 为：

```text
d3bd9c15434fd7a48c0b7bab87354778cd932a72
```

`final-head-source-manifest-20260721.txt` 和 `final-head-context.env` 记录了同一
HEAD、parent `be99e5505abe341100c62d70cd955b2df7e4711e`，以及：

```text
production DADAOFrameLowering.cpp  a3ed13fcc5f03765e6980936454b2761f72efd7b55b44b9261f025d6c9882e6b
test       frame-lowering-stack-alignment.ll  6e871fa22863278808e77c2acbc33142555d4dbeb54fe6c884cbc39d55eb4e80
```

我重新计算了当前文件 hash，并用 `git show HEAD:<path>` 计算 HEAD blob hash；两者
分别与上述 production/test hash 完全一致。`sha256sum -c` 对 source manifest、
command-output manifests、runtime manifests、artifact manifests 均通过。当前
final clang 的版本字符串还明确包含：

```text
clang version 22.1.8 (... d3bd9c15434fd7a48c0b7bab87354778cd932a72)
```

证据中记录的 nested status 是 `## HEAD (no branch)`，没有后续 porcelain 项；我
在本轮所有审阅动作后再次只读执行 status，结果仍为同一行。`git diff-tree` 也确认
该 HEAD 相对 parent 只涉及预期的 LLVM frame-lowering 源文件和 regression 文件。

### 2. final-head 全链路

`logs/` 中各权威命令的 argv 注释都绑定相同 HEAD 和两份 source hash；阶段 rc
如下：

| 阶段 | rc | 独立判断 |
|---|---:|---|
| clang C → IR | 0 | 通过 |
| llc → MIR | 0 | 通过 |
| llc → assembly（合法 `-filetype=asm`） | 0 | 通过 |
| llc → object、clang C → object | 0 | 通过 |
| llvm-mc crt0 | 0 | 通过 |
| lld link ELF | 0 | 通过 |
| llvm-objcopy ELF → BIN | 0 | 通过 |
| llvm-objdump disasm | 0 | 通过 |

final ELF hash 为
`255649528ed07019737e5530e89f2eaeb2404308341a0b75008706081667661c`，BIN hash 为
`35fb09087d8914d9f21031beb97d23fade4c1ab3c85abf0e282cd032e2414e26`；这些 hash
在 artifact manifest 与 runtime input manifest 中一致。link argv 明确使用
`crt0.final-head.o` 和 final-head 生成的 `varargs_min.clang.o`，没有把历史 final3
产物混入新链路。

### 3. 正常 varargs QEMU/Gem5 闭环

输入与产物 manifest 同时覆盖 launcher、QEMU、Gem5、Gem5 script、ELF 和 BIN，且
hash 可复算。两个正常路径均为 rc=0：

- QEMU argv 使用 `-bios .../ml-016v-trampoline.bin` 与
  `-kernel .../artifacts/varargs_final_head.bin`；launcher hash 为
  `44042fabb2741724828443d7ae13bd42e3931e88d8be7f2f7dc48be3d851f5e0`，BIN hash
  与上述一致。raw stdout/stderr 也与 manifest 一致。
- Gem5 argv 直接使用 `.../artifacts/varargs_final_head.elf`；Gem5 `m5out/config.ini`
  的 `cmd` 与 `executable` 指向同一个 ELF。Gem5 binary、script、ELF 的 hash
  均已记录，raw trace 含 `SIM_END: halt code=0`。

因此 QEMU 的 launcher+BIN 闭环和 Gem5 的 direct-ELF 闭环分别成立。正常 C probe
的 `main` 确实调用 `varargs_frame(1, -1)`；final disassembly 观察到 `-152/+152`
及 varargs save stores，和两端 rc=0 结果相互一致。

### 4. odd/padding=4 边界

最终生成的 `static/varargs_min.mir` 中，`varargs_one_local` 观察到：

```text
stackSize: 4
fixed varargs save size: 120, alignment: 8
hasVAStart: false
```

静态 probe 的算术为：`roundUp(4 + 120, 8) = 128`，lower padding 为 4，随后
`alignDown(4, 8) = 0`。对应最终 MIR/assembly 为 `-128/+128`，local slot 位于
`rb1+124`；这准确区分了 raw local、save area、rounded frame 和 residual padding。

没有 odd/padding=4 的 QEMU 或 Gem5 命令。报告明确写出 `hasVAStart=false` 和
“no runtime claim”，故没有把该静态边界伪造为 runtime 通过。

### 5. B1/B2 与历史 final3 分离

旧 ML-016y final3 证据仍在 `/tmp/ml-016y-frame-rounding-fix-20260721/`；新证据
全部位于独立的 `/tmp/ml-016z-final-head-varargs-provenance-20260721/`，文件名也
使用 `final-head`。新命令日志、工具版本、source manifest、ELF/BIN hash 和
QEMU/Gem5 rc 均不依赖旧 final3 的 hash。因此：

- B1：新 compile/link/objcopy/disasm/runtime 是 final HEAD 绑定的重跑结果，旧
  final3 没有被改写成 d3bd9c 的结果。
- B2：新增 `final-head-source-manifest-20260721.txt` 与对应 sha256 manifest
  验证了当前 HEAD 的 production/test source；旧 stale `final-source.sha256`
  没有被覆盖，也没有继续作为权威 manifest。

## Findings

### Blocking findings

无。

### Non-blocking findings

#### N1：证据包缺少链路结束后的 nested status 日志

`logs/final-head-status.*` 的生成时间为 21:23:17，早于 link/objcopy（约 21:24:13）
和 QEMU/Gem5（约 21:25:57）；证据目录只有这一份 status 输出，没有单独的
post-chain `git status` 日志。我的独立只读检查在本轮结束后确认 nested LLVM 仍为
clean detached HEAD，且所有展示的命令都只写 build、artifact、runtime 或日志
路径，所以这不阻塞本次结论；但若要让证据包自身完整证明“全链路前后 clean”，应
补充一份链路结束后的 status 记录。

#### N2：既有 report 对 Gem5 launcher 的表述过宽

既有 report 写“两端使用同一个 ML-016v launcher”，但当前证据的 Gem5 argv 没有
launcher，且 Gem5 config 也直接加载 final-head ELF。launcher 实际只出现在 QEMU
的 `-bios` argv 中；Gem5 的 ELF、Gem5 binary 和 script hash 仍然闭合，因此这是
事实表述问题，不是 Gem5 rc=0 结果或其实际输入 provenance 的缺失。后续引用时应
明确写成：QEMU 使用 launcher+BIN，Gem5 使用直接 ELF。

## 全部非零 rc 边界

新证据目录的 `.rc` 文件中非零值恰好只有以下三项，既有 report 的标注准确：

1. `llc-varargs-min-final-head-assembly.rc=1`：使用了该版本不支持的 `llc -S`，
   stderr 为 `Unknown command line argument '-S'`；随后合法的 `-filetype=asm`
   命令 rc=0。
2. `llc-varargs-odd-padding4-final-head.rc=134`：把 pre-PE synthetic MIR 独立
   送入 `llc -run-pass=prologepilog`，因 `main` 中未定义物理 `rd31` 触发 LLVM
   verifier abort；没有生成并使用所谓 odd runtime artifact。
3. `odd-padding4-static-check-final-head.rc=1`：依赖上述不存在的输出文件，grep
   找不到文件；最终采用 final-head MIR 的算术静态 probe rc=0。

这三项均不是权威通过结果。历史 ML-016y 目录中的 `llvm-lit rc=2` 仍是旧的
`llvm-config` 基础设施限制；本 report 没有把它改写为 ML-016z 通过，也没有声称
完整 LLVM suite、musl 或完整 E2E/differential matrix 通过。

## 范围与剩余边界

本轮接受的是 final-head varargs 最小 compile/link/runtime provenance closure，
不是完整 ABI 或完整测试套件证明。odd/padding=4 没有安全 runtime 入口；复杂
overflow argument、动态 stack object、异常路径、完整 LLVM suite、musl 和完整
E2E/differential matrix 仍未覆盖。
