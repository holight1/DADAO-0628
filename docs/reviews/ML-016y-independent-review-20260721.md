# ML-016y 独立 reviewer 报告

日期：2026-07-21

身份：独立 reviewer；未修改 LLVM、musl、QEMU、Gem5、spec、launcher 或 tracker。

## 结论

**Rejected（存在 blocking evidence/provenance finding）。**

我没有从最终源码本身发现已证实的 prologue/epilogue 或普通 frame-index
布局错误；但当前验收不能把 varargs 的 QEMU/Gem5 rc=0 作为
d3bd9c15434fd7a48c0b7bab87354778cd932a72 的最终 commit 结果。该路径正是
最终 amend 新增的 alignDown 修订，缺少 final-commit-bound 的双后端证据，因而
不能接受现有 review 的“final runtime”事实表述。

审阅对象：

- [任务说明](/home/holight/DADAO-0628/code-agent/tasks/ML-016y-frame-rounding-fix.md)
- [原 review](/home/holight/DADAO-0628/docs/reviews/ML-016y-frame-rounding-fix-20260721.md)
- [最终 frame lowering 源码](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/Target/DADAO/DADAOFrameLowering.cpp)
- [最终 regression](/home/holight/DADAO-0628/.work/source/llvm/llvm/test/CodeGen/DADAO/frame-lowering-stack-alignment.ll)
- [/tmp 证据目录](/tmp/ml-016y-frame-rounding-fix-20260721/)

## Findings

### B1 — blocking：最终 varargs runtime 没有被 final commit 绑定

最终 commit 是 d3bd9c...，提交时间为 21:01:58；中间 commit
3ae8bff... 的时间为 20:58:18。最终 commit 相对中间 commit 的唯一源码语义
差异是 varargs frame-index 分支由：

    FrameSize -= VarArgsSaveSize;
    FrameSize -= MFI.getStackSize();

改为计算 Padding 后执行 alignDown(Padding, 8)。这不是可忽略的文档变化，而
是本任务用于处理 padding=4 的关键修复。

证据时间线如下：

- build-clang-llc-varargs-align-final.rc=0：21:00:39；
- compile-varargs_runtime-final3.rc=0、link/objcopy：约 21:01:29；
- qemu-varargs_runtime-final3.rc=0、gem5-varargs_runtime-final3.rc=0：约
  21:01:29–21:01:30；
- nested-commit-final.rc=0、产生 d3bd9c...：21:01:59；
- commit 之后的 build-clang-llc-on-final-head.rc=0 虽然证明工具链后来重编，
  但没有相应的 varargs compile/link/objcopy/QEMU/Gem5 重跑。

因此这些 final3 结果至多是“提交前工作树结果”。由于源码在中间 commit 之后
曾被修改，不能仅凭时间断言它们一定来自 3ae8...；但也没有命令输出、源 hash
或 artifact hash 将它们绑定到 d3bd9c...。原 review 第 51–53、72–82 行把它们
写成 final runtime/真实执行，超出了证据能够支持的事实范围。

要求：在 clean d3bd9c... HEAD 上重新执行 varargs（包括 odd/padding 场景）
compile、link、objcopy、disasm，以及 QEMU/Gem5 两端；同一批日志中记录 HEAD、
最终源 hash、输入 hash、artifact hash 和 rc。未完成前这是 blocking。

### B2 — blocking：final-source.sha256 是 stale hash

[hashes/final-source.sha256](/tmp/ml-016y-frame-rounding-fix-20260721/hashes/final-source.sha256)
记录的是：

    b44430361be2...  DADAOFrameLowering.cpp
    6e871fa22863...  frame-lowering-stack-alignment.ll

其中第一项匹配中间 commit 3ae8bff...，不匹配最终 d3bd9c...。当前 final
commit/tree 的实际 hash 为：

    a3ed13fcc5f0...  DADAOFrameLowering.cpp
    6e871fa22863...  frame-lowering-stack-alignment.ll

final-manifest.txt 后来列出了当前的 a3ed.../6e871...，且
nested-commit-final.sha 是正确的 d3bd9c...；这说明 final commit hash 本身没有
写错，但名为 final-source.sha256 的权威性文件没有同步。它也不能支持 B1 中
“final3 artifact 来自 final commit”的链路，需随 B1 一并重生成。

### F1 — non-blocking：源码布局审阅结果基本成立，但 regression 对 varargs FI 覆盖不足

最终源码的静态逻辑是一致的：

- getDADAOFrameSize 以 MFI.getStackSize()+VarArgsSaveSize 为 raw size，并
  alignTo(..., 8)；prologue 与 epilogue 共享该值；
- 普通 frame-index 使用 objectOffset + rounded size。i32 raw frame 4 生成
  -8/+8，对象 offset -4 变成 rb1+4；i64 raw frame 8 保持 -8/+8；
- varargs save-area FI 单独将 rounded frame 扣除 save size 和普通 MFI frame，
  再 alignDown(..., 8)。已观察到的 120-byte save + 8-byte MFI frame 形状中，
  save stores 是 rb1+0..112，callee/local 位置在其上方，没有重叠；较大探针的
  -152/+152 形状也显示 save area 与 locals 分离。

但是提交的 LLVM regression 的 variadic 函数没有 va_start/va_arg，它检查了
save stores 的边界，却没有直接走 varargs frame-index reference 分支。真正走该
分支的是 /tmp 下的 C probe；由于 B1 的 provenance 问题，该覆盖目前不能作为
最终 commit 的双后端验收替代品。

### F2 — non-blocking：静态与 runtime 矩阵本身的可复核性

以下结果在证据目录中可由 argv/rc、MIR 或 disassembly 复核，且语义互相一致：

| 场景 | QEMU | Gem5 | reviewer 判断 |
|---|---:|---:|---|
| no-frame direct trap | 42 | 42 | 支持无 frame adjustment |
| direct_syscall1 | 42 | 42 | helper -40，非窄 frame 路径 |
| wrapper_noreturn | 42 | 42 | 外层 frame 为 -8，helper 为 -40 |
| exit_shape | 42 | 42 | 与 wrapper 形状一致 |
| 故意 trap_stack_minus4 | 129 | 129 | 负对照仍能触发未对齐行为 |
| trap_stack_minus8 | 42 | 42 | 对齐对照 |
| varargs runtime | 0 | 0 | 结果存在，但受 B1/B2 限制，不能称 final-commit-bound |

我在 clean d3bd9c... HEAD 上做了只读的 assembly/MIR FileCheck 重跑，分别为
rc=0；这确认了当前提交的 regression 生成结果，但不补齐历史 varargs 双后端
runtime 的 commit provenance。

## llvm-lit 与失败命令的边界

### llvm-lit rc=2

logs/lit-dadao-final.rc 为 2，stderr 的 fatal 原因是无法运行
.work/build/llvm/bin/llvm-config --assertion-mode --build-mode。此可以判断为
测试基础设施初始化限制，不能写成目录测试失败，也绝不能写成完整 LLVM 测试套件
通过。直接 llc | FileCheck 的 rc=0 只覆盖该 regression 的两条直接命令，不等于
llvm-lit 或全套测试通过。原 review 对这一点的限定是正确的。

### 不得作为权威结果的记录

下列记录应明确标为历史/无效尝试，而不是验收结果：

- compile-varargs.rc=1 使用未定义的 $E，展开成 /probes/varargs_min.c；
  varargs-asm.rc=1、varargs-mir.rc=1 同样引用 /tests/...；
- test-assembly-final.rc=1、final2.rc=1 是旧 FileCheck 期望值（分别把
  112/124 等形状写错），final3.rc=0 才是修正后的直接检查；
- test-mir-final.rc=1 仍期待 stackSize: 4，final2/final3.rc=0 才使用了
  实际的 stackSize: 8；
- link-trap_stack_minus4-final.rc=1 和 minus8-final.rc=1 是把自带 _start
  的 trap object 与 crt0.o 重链造成的 duplicate symbol；对应的 *-fixed-final
  才是有效链接；
- disasm-trap_stack_minus4-final.rc=1/minus8-final.rc=1 及其 objcopy 失败是对
  尚未生成的旧 artifact 名称执行的 stale-path 命令；不能据此判断 trap binary
  失败。

这些失败在部分原 review 文字中有提及，但“正常路径均 rc=0”的概括必须和上述
历史尝试分开，并不能覆盖 B1/B2 的 final provenance 缺口。

## 不越界的范围声明

本轮证据没有验证完整 LLVM suite、musl 全量构建、完整 E2E/differential，亦没有
修改或审阅 QEMU/Gem5 实现本身。129 与 42 是双后端行为对照，支持对齐归因，
但不能单独把 simulator rc 反推为 LLVM 源码事实。

## 交接

阻塞项是证据重跑与 hash 修复，不是本报告对已经观察到的 i32/i64 普通 frame
布局的功能性否定。完成 B1/B2 后，再以 final commit 绑定的 varargs odd-padding
双后端结果重新决定是否提升为 Accepted 或 Accepted-with-findings。
