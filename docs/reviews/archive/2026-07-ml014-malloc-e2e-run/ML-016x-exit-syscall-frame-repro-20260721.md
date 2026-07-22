# ML-016x：`_Exit`/syscall 栈对齐最小复现与归因

日期：2026-07-21  
状态：Completed / diagnosis only / no production fix

## 结论摘要

ML-016w 的第一 fault 结论可以用最小探针独立复现，并可进一步收窄到 **DADAO
frame lowering 没有把 4-byte frame 向上取整到 ABI 要求的 8 bytes**：

```text
aligned caller
  -> _Exit prologue: rb1 -= 4       # rb1: 0 mod 8 -> 4 mod 8
  -> __syscall1 prologue: rb1 -= 40 # 仍为 4 mod 8
  -> enters/stays in first 64-bit sto block # MALIGN 129；trap 尚未成为有效执行点
```

`__syscall1` 的 `-40` 本身是 8 的倍数；实际破坏对齐的是 `_Exit`/非返回包装的
`-4`。显式 `trap 2, 0` 在没有错误 frame 时两端均以 `42` 正常退出，`-4` 后的
64-bit store 两端均为 `129`，因此 syscall trap 或 launcher 不是第一根因。

主修复归属建议是 **DADAO frame lowering**：当前 `DADAOFrameLowering` 构造函数声明
`Align(8)`，但 `emitPrologue`/`emitEpilogue` 直接使用 `MFI.getStackSize()`；ML-016u
exact `_Exit` 的 MIR 是 `stackSize: 4`，因而实际发出 `addi rb1, rb1, -4`。musl
syscall wrapper 可以作为短期规避面（例如避免该窄 frame 或改用直接 trap），但不能替代
通用 ABI frame 修复。测试 launcher 应排除：QEMU/Gem5 都从对齐 stack 启动，且直接 trap
fixture 成功。

本轮没有修改任何生产源、archive、测试或 launcher。

## 与 ML-016w 的关系

ML-016w 审计了 ML-016v partial archive 的实际 runtime：QEMU/Gem5 都 `rc=129`，静态
路径是 `exit -16 -> _Exit -4 -> __syscall1 -40 -> sto`；QEMU trace 进入下一条
store，Gem5 raw trace 精确停在 `__syscall1` 入口。ML-016x 不重复把 `rc=129` 解释为
main 返回值，也不把 Gem5 未执行到 store 的部分写成动态观测；本轮增加了：

- include-free C/IR/汇编的成功/失败对照；
- exact ML-016u `_Exit.o` 的 object identity 和 MIR；
- 对齐 caller 与自身 `-4` caller 的成对运行；
- 对 DADAO frame lowering 源码的直接核对。

ML-016w 使用的 ML-016v partial archive member `_Exit.o` SHA-256 为
`341a7148cda7ed4c033b93bdc477f1051f5cf052bf138a080ba46695d73638b0`，本轮 exact
编译结果与该 hash 完全一致。当前 `.work/build/musl/lib/libc.a` 是 2026-07-18 的
另一 vintage，未用于本轮 runtime 结论；从它抽出的 `_Exit.o` 是另一种 direct-trap
形状，不能覆盖 ML-016v/ML-016u partial archive 证据。

## 事实（可直接复核）

### 1. 源码和 ABI 路径

| 事实 | 证据 |
|---|---|
| musl `_Exit` 先调用 `SYS_exit_group`，再无限循环调用 `SYS_exit`。 | [`.work/source/musl/src/exit/_Exit.c`](/home/holight/DADAO-0628/.work/source/musl/src/exit/_Exit.c:4) lines 4–7；SHA-256 `624597e4...06fc6e`。 |
| DADAO `__syscall1` 把 syscall no/arg/return 放在 `rd16`/`rd17`/`rd31`，执行 `trap 2, 0`；源文件没有显式 stack adjustment。 | [`syscall_arch.h`](/home/holight/DADAO-0628/.work/source/musl/arch/dadao/syscall_arch.h:40) lines 40–48；SHA-256 `9a8608e...efd4786`。 |
| `exit(code)` 完成 fini/stdio 路径后调用 `_Exit(code)`。 | [`exit.c`](/home/holight/DADAO-0628/.work/source/musl/src/exit/exit.c:27) lines 27–33。 |
| musl CRT 从 `_start` 构造启动参数并调用 `_start_c`/`__libc_start_main`；`crt_arch.h` 初始 frame 使用 `-160`，为 8 的倍数。 | [`crt1.c`](/home/holight/DADAO-0628/.work/source/musl/crt/crt1.c:14)、[`crt_arch.h`](/home/holight/DADAO-0628/.work/source/musl/arch/dadao/crt_arch.h:61)–141；ML-016w linked disassembly 记录 `_start -160`、`_start_c -24`。 |
| ABI 要求 `SP` 在 `call` 前 8-byte aligned，callee frame size 8-byte aligned。 | [`contracts/abi/spec.md`](/home/holight/DADAO-0628/contracts/abi/spec.md:206)–210、265–269。 |
| DADAO frame lowering 的 target object 声明 `Align(8)`，但 prologue/epilogue 将 `MFI.getStackSize()` 原值直接取负/加回，没有 round-up。 | [`DADAOFrameLowering.h`](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/Target/DADAO/DADAOFrameLowering.h:9)–15；[`DADAOFrameLowering.cpp`](/home/holight/DADAO-0628/.work/source/llvm/llvm/lib/Target/DADAO/DADAOFrameLowering.cpp:19)–58；source hashes `729f0c2d...977203c`、`f97a3a61...bb733c`。 |

### 2. 最小探针和双后端结果

所有 C probe 使用 `-nostdinc -ffreestanding`；C/IR/汇编编译、汇编、链接和 objcopy
均保存原始 argv、stdout/stderr、rc。证据根目录为
[`/tmp/ml-016x-exit-syscall-frame-repro-20260721/`](/tmp/ml-016x-exit-syscall-frame-repro-20260721/)。

| probe | 静态关键 frame | QEMU rc | Gem5 rc | 解释 |
|---|---|---:|---:|---|
| `direct_syscall1` | `main` 无额外 frame；`__syscall1 -40` | 42 | 42 | 直接 syscall 成功对照 |
| `wrapper_return` | 外层 `-8`；`__syscall1 -40` | 42 | 42 | 有返回值包装，frame 余数不变 |
| `wrapper_noreturn` | 外层 `-4`；`__syscall1 -40` | 129 | 129 | 非返回包装复现 |
| `exit_shape` | `_Exit -4`；`__syscall1 -40` | 129 | 129 | include-free `_Exit.c` 结构孪生 |
| `trap_direct` | 无 stack use，直接 `trap 2,0` | 42 | 42 | trap/launcher 成功对照 |
| `trap_stack_minus4` | `rb1 -= 4` 后 `sto` 64-bit | 129 | 129 | 显式 MALIGN 对照 |
| `trap_stack_minus8` | `rb1 -= 8` 后 `sto` 64-bit | 42 | 42 | 对齐 frame 对照 |

每行的 compile/link/objcopy 正常路径均为 `rc=0`。例如 ELF SHA-256：

- `direct_syscall1.elf`: `9f65b704dc7d12c3ba7c96bdb5ca284613a2c8f31156260af950622fe0183998`
- `trap_direct.elf`: `0281ba4eab08e4f621622bc76921b3e9bb84c97cfffab40da231de2c249c9835`
- `trap_stack_minus4.elf`: `bd3a3baad37cf5db29c1522a2b4315f652c2e9642836360a88974b5eedf0054e`
- `trap_stack_minus8.elf`: `3983bf5abd511ea2a7e77b31e592431c85dde17503785e5339ef958e9da2fee6`

### 3. C/IR/汇编层的具体证据

- include-free `direct_syscall1.c` 生成 `__syscall1` 的 `addi rb1, rb1, -40`，然后
  在对齐 stack 上执行 `trap`，双后端 `42`。
- include-free `wrapper_return.c` 的 wrapper 是 `-8`，双后端 `42`；这确认“带返回值”
  不是必然失败条件。
- `wrapper_noreturn.c` 和 `exit_shape.c` 的外层 frame 是 `-4`，其 syscall helper
  仍是 `-40`，双后端都在 trap 前返回 `129`。
- `ir_frame_probe.ll` 的 llc object `rc=0`，静态输出独立显示：`i64 alloca` 为
  `rb1 -= 8`，`i32 alloca` 为 `rb1 -= 4`。对应 prologepilog MIR 的 hash 是
  `29bdba8304b8c1a436fdfb862caf22c6b97990232a253e5107cf0fe74e1c1236`。
- exact ML-016u `_Exit.c` 用 ML-016u 的真实 clang argv 重编译，compile/disasm 均
  `rc=0`，产物 hash 与 ML-016u object 完全相同：
  `341a7148cda7ed4c033b93bdc477f1051f5cf052bf138a080ba46695d73638b0`。

### 4. exact ML-016u object 的对齐 caller 试验

将 exact `_Exit.o` 与 include-free、无 prologue 的 `main_call_exit.s` 链接：

```text
main:       addi rd16, rd0, 42; call _Exit
_Exit:      addi rb1, rb1, -4
__syscall1: addi rb1, rb1, -40; sto rd16, rb1, 32
```

compile/assemble/link/objcopy/disasm 全为 `rc=0`；ELF SHA-256 为
`3a6fb2c304e45a5883fdb6ed57d240b8556827ae8cd9a3a48efc31b8d891414a`，BIN SHA-256 为
`dec68a085bf31287b3f7e6e6fddc6f70870b4334fd1ef1a8bd57d91fa696e9ff`。QEMU/Gem5 均
`rc=129`，Gem5 输出 `SIM_END: MALIGN code=129`。

另一个 include-free C caller 自己生成 `main -4`，然后调用同一 exact object；该版本
QEMU/Gem5 均 `rc=42`。这是 frame parity 偶然抵消：caller 的 `-4` 先把 entry stack
变成 `4 mod 8`，`_Exit -4` 又回到 `0 mod 8`。它不能证明 `_Exit` 遵守 ABI，反而证明
运行时结果会依赖 caller frame，存在 ABI 不稳定性。

### 5. MIR 和 runtime fault PC

对 exact ML-016u `_Exit.c` 先生成 LLVM IR，再用
`llc -mtriple=dadao-unknown-elf -O0 -stop-after=prologepilog` 保存 MIR：

```text
_Exit:      stackSize: 4, maxAlignment: 4, ec.addr size/alignment 4
            ADDI_RBRRII rb1, -4
__syscall1: stackSize: 40, maxAlignment: 8
            ADDI_RBRRII rb1, -40
            STO_RRII rd16, rb1, 32
```

MIR hash：`232a811685fe501660f3d04f645bb215c614c4966e8e87906929c2611d997af6`。

本轮 debug runtime 的原始 trace：

- QEMU `exit_shape` 在 `0x80000038` 的 `__syscall1` block 后进入 `0x8000003c` 的
  64-bit store block，随后反复停留，rc=129。
- Gem5 `exit_shape` 最后一条实际执行记录为 `0x80000038 @__syscall1 : addi.rb`，
  rc=129；对应下一条静态指令是 `0x8000003c` 的 64-bit `st`，因此不把 Gem5 写成
  已动态观测到 store。
- `trap_stack_minus4` 的 Gem5 trace 只执行到 `_start+4`，下一条 `sto` 触发 MALIGN；
  `trap_direct`/`trap_stack_minus8` 均正常返回 `42`。

QEMU 的 `exec,in_asm` trace 证明进入并停留在该 store block；它不单独证明 faulting
store 的完成语义。Gem5 的最后动态记录停在前一条指令，store 与 fault 的对应关系来自
静态反汇编和 simulator 的 `MALIGN 129` 结果。因此本文将 store 写为静态映射的
faulting-store block，不把它表述成两端都动态完成了该 store。

## 推断 / 归因（不是直接观测）

| 推断 | 依据与限制 |
|---|---|
| 第一根因是 callee prologue 的 `-4`，不是 `trap` 指令。 | 直接 trap 和 `-8` store 双端为 42，`-4` store 双端为 129；`__syscall1 -40` 不改变 mod-8 余数。 |
| 当前最可能且证据最窄的修复归属是 DADAO frame lowering。 | ABI 明确要求 frame size 8B aligned；target frame lowering虽声明 Align(8)，却将 MFI raw size 4 直接发为 `-4`。需要未来修复/回归验证，不在本任务实现。 |
| musl `_Exit` 是触发器/可选规避面，不是通用根因。 | `_Exit` 的 `int ec` 产生 4-byte local；把它改成 direct trap 或避免窄 spill 可能绕过，但其他任何 4-byte local/callee 仍可违反同一 ABI。当前 `syscall_arch.h` 的 `__syscall1` 自身 frame 为 40。 |
| launcher 不是根因。 | QEMU trampoline 初始 `rb1=0x87ff0000`，8-byte aligned；Gem5/QEMU 对齐入口下 direct trap 均为 42。改 launcher 只会改变 frame parity，可能掩盖问题。 |
| “某个 `_Exit` ELF 成功”不能作为修复证据。 | exact object + C caller `main -4` 为 42，但 exact object + aligned assembly caller 为 129；成功由 caller frame 抵消。 |

## 修复归属建议（本轮不实现）

1. **主归属：DADAO frame lowering。** 在 prologue、epilogue、varargs save area 和
   frame-index offset 计算中统一定义/执行 8-byte frame rounding，确保 `MFI` 的实际
   frame size、spill offset、恢复路径一致；加入 `stackSize=4`、`stackSize=8`、跨 call
   的 CodeGen regression。
2. **次级：musl syscall wrapper/`_Exit` 规避。** 可单独评估将 `_Exit` 的 syscall path
   变为无窄临时的 arch-specific direct trap，但这只能是 DADAO port 的 workaround，
   不应替代通用 frame contract 修复，也不应在本任务中改生产源。
3. **排除：测试 launcher。** 不能通过调低/改变初始 SP 对齐来“修复”；那会把真实 ABI
   fault 变成 caller-dependent 假通过。

## 未决风险

- 需要未来修复后验证所有静态 frame（尤其窄 local、callee-saved spill、varargs save
  area、异常/动态 stack path），不能只验证 `_Exit`。
- 当前 simulator 的 `trap 2,0` 是既有 host-side responder shortcut；本任务只证明
  MALIGN 发生在它之前，不证明 trap 后的 SEE syscall 语义已完整实现。
- QEMU/Gem5 trace 粒度不同：QEMU 可显示 faulting store block，Gem5 本轮只显示到
  faulting instruction 的前一条/入口；报告保留这一边界。
- `.work/build/musl/lib/libc.a` 与 ML-016u/ML-016v partial archive 不是同一 artifact
  vintage；未来复核必须携带 object hash，禁止只按 member 名称复用旧 archive。

## 命令、返回码、产物和复核入口

证据目录保存每条命令的 `.argv`、`.stdout`、`.stderr`、`.rc`，以及 build/disasm/runtime
产物和 hash：

- probe source：[`probes/`](/tmp/ml-016x-exit-syscall-frame-repro-20260721/probes/)
- 编译/链接/objcopy/disasm argv/rc：[`logs/`](/tmp/ml-016x-exit-syscall-frame-repro-20260721/logs/)
- C/IR/汇编产物：[`build/`](/tmp/ml-016x-exit-syscall-frame-repro-20260721/build/)、
  [`artifacts/`](/tmp/ml-016x-exit-syscall-frame-repro-20260721/artifacts/)
- exact ML-016u/archive member：[`musl-archive/`](/tmp/ml-016x-exit-syscall-frame-repro-20260721/musl-archive/)、
  [`ml016v-archive/`](/tmp/ml-016x-exit-syscall-frame-repro-20260721/ml016v-archive/)
- debug QEMU/Gem5 trace：[`runtime/`](/tmp/ml-016x-exit-syscall-frame-repro-20260721/runtime/)

本轮复跑使用的 ML-016v trampoline launcher identity：
`/tmp/ml-016w-malign-runtime-consistency-audit-20260721/launcher/ml-016v-trampoline.bin`，
SHA-256 `44042fabb2741724828443d7ae13bd42e3931e88d8be7f2f7dc48be3d851f5e0`；其生成命令和
`-bios`/`-kernel` 关系保留在 ML-016x 的 launcher/QEMU argv 日志中。

两类早期无效命令也保留在日志中并明确排除：第一批 objcopy 因脚本把
`artifacts/name.elf` 误写成 `artifacts/link-name.elf`，其 rc=1；第一批 Gem5 capture
因 shell 变量复用生成了错误日志名。随后使用修正后的命令重新执行，权威 Gem5 矩阵
为上表的 `42/129` 结果。没有以这些无效命令冒充成功，也没有因 host header 缺失伪造
成功：include-free probe 和 exact ML-016u source compile 都保留真实 `rc=0`。

## 变更边界

仓库内新增且仅新增：

- [`code-agent/tasks/ML-016x-exit-syscall-frame-repro.md`](../../code-agent/tasks/ML-016x-exit-syscall-frame-repro.md)
- [`docs/reviews/ML-016x-exit-syscall-frame-repro-20260721.md`](ML-016x-exit-syscall-frame-repro-20260721.md)

未修改 `.work/source/llvm`、`.work/source/musl`、archive、QEMU/Gem5、测试、规范、
launcher 或其他生产文件；现有未跟踪的 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`
保持不变。
