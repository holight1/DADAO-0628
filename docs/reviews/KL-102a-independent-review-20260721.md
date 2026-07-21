# KL-102a 独立 review（2026-07-21）

## 结论

**Needs-fix**。

报告的核心事实判断基本准确：QEMU 现有的是 `EXCP_CFXTRAP`/host-side `cfx_smon` shortcut；gem5 没有当前已应用的 `src/arch/dadao`，相关内容只能称为 patch-defined surface；O1/O2 也被标为后续实现建议/验收草案，没有直接写成 M1 已实现。

但在作为可执行、可审计的独立评估交付前，仍需补三处限定：

1. gem5 patch-defined surface 的可用性需明确标注为“代码形状/拟议承载点”，而非可直接复用的实现。`0001` 的 `ISA::copyRegsFrom()` 体内使用未定义的 `tc`，因此该 patch 链不能据此暗示已有可构建的复制路径。
2. O1 的“12 个 delegation”没有在报告中列出具体寄存器/字段/编码，`cfx2rc` 与 `escape cfx_power,0` 也没有给出可直接核验的 opcode/operand 证据；当前只能审计到语义级边界，不能审计到测试向量级边界。
3. 统一字段列表是建议，不是现有协议。报告没有定义 `mode`/`cfx_mask` 的数值编码、`event` 状态转换、`marker`/`rc` 的来源及 legacy/real profile 的实际互斥检查点；因此“字段相同即可双端验收”尚未完全可审计。应继续保留 `[实现建议]`/`[推断/验收草案]` 标签，并补字段 schema 或明确声明其尚未冻结。

## 三条证据与命令

### 证据 1：契约边界引用准确，但 CFX 仍是排除/延后范围

事实：`spec.md` 只冻结 SEE 的 `rb0` reset vector，完整 reset state 标为 C-18 partial/open；M1 explicitly excludes `trap`、`escape`、`cfx2rd`、`cfx2rc`、`cfxld`、`cfxst`；异常 contract 将 full CFX routing/masking/nesting/escape deferred。报告没有把这些写成现行实现。

```bash
cd /home/holight/DADAO-0628
nl -ba contracts/isa/spec.md | sed -n '50,52p;947,959p;1146,1150p'
nl -ba contracts/exception/README.md
```

### 证据 2：QEMU 文件、符号和行号引用与现状相符

事实：`CPUArchState` 只有寄存器 bank、PC 和 `trap_*` scratch；reset 设置 `0x00100000`；`helper_trap()` 设置 `EXCP_CFXTRAP` 后退出 loop；`dadao_cpu_do_interrupt()` 的 `cfxcode==2` 分支直接执行 host syscall 行为；没有 inner CFX state、`cfx2rc` 或 `escape`。

```bash
cd /home/holight/DADAO-0628
nl -ba .work/source/qemu/target/dadao/cpu.h | sed -n '8,12p;49,59p'
nl -ba .work/source/qemu/target/dadao/cpu.c | sed -n '40,57p;109,242p'
nl -ba .work/source/qemu/target/dadao/helper.c | sed -n '8,31p;99,108p'
nl -ba .work/source/qemu/target/dadao/translate.c | sed -n '452,464p'
```

### 证据 3：gem5 明确是 patch-defined，但 patch 本身不能当作现有实现

事实：当前 `.work/source/gem5/src/arch/dadao` 不存在；series 仅提供拟议 patch。`0001` 的 `isa.hh`/`registers.hh` 只有 skeleton misc state，`0010` 的 `TrapInst::execute()` 直接读 RD 并调用 `std::cout`/`exitSimLoop`；同时 `0001` 的 `copyRegsFrom()` 使用未定义的 `tc`，支持本 review 的 Needs-fix 限定。

```bash
cd /home/holight/DADAO-0628
test -d .work/source/gem5/src/arch/dadao && find .work/source/gem5/src/arch/dadao -maxdepth 1 -type f -print || echo NO_CURRENT_GEM5_DADAO_SOURCE
nl -ba components/gem5/patches/series
nl -ba components/gem5/patches/0001-dadao-arch-skeleton.patch | sed -n '712,735p;763,795p;1009,1023p'
nl -ba components/gem5/patches/0010-dadao-trap-syscall.patch | sed -n '19,43p;48,53p'
```

本次只读审阅；未访问 `~/toolchain` 或 `~/knowledge-graph`，未修改原报告。仅写入本文件。
