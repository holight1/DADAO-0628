# ML-014c: QEMU mmap arena 真实 backing

**执行环境**：本地 subagent worker；QEMU ownership only

**状态**：待处理

## 背景与目标

ML-014a 真实 mallocng 路径证明 `SYS_mmap=222` 返回的固定 arena 地址没有真实
MemoryRegion backing。请在当前 QEMU HEAD 上实现 M1 所需的最小真实 backing，保持
`DADAO_MMAP_ARENA_BASE=0x100000000`，不要迁移到现有 128MiB RAM 窗口。

## Ownership

- 允许修改：`.work/source/qemu/hw/dadao/`、`.work/source/qemu/target/dadao/`
  中实现所需的 QEMU 源文件；`components/qemu/patches/0018-*.patch` 和
  `components/qemu/patches/series`；本任务 md 的完成区与 review 记录。
- 不允许修改：LLVM、gem5、musl、contracts、manifests、`docs/issues.yaml`、
  其它任务文件和既有测试源文件。
- 不得 reset、rebase、重放整条历史或覆盖别人已有修改；在当前 component HEAD
  上追加普通 commit。

## 实现要求

- 在固定 `0x100000000` arena 建立独立 host-backed RAM MemoryRegion，容量必须
  是明确常量并写出理由；不能继续无界推进 cursor。
- 对零长度、页对齐溢出、超出容量和重复/重叠区间作明确失败处理，不能静默
  返回不可访问地址或 alias 已分配空间。错误码必须遵循当前 syscall responder
  约定，不能猜测新 ABI。
- 保持 ROM、exit MMIO、现有 RAM、trampoline、linker 和 flat binary 地址不变。
- `mprotect` 的 M1 deferred 语义不能伪称为真实权限；`munmap` 的当前行为要在
  报告中说明，不能顺手扩展成未批准的完整 Linux 语义。
- 用 `.work/` 下临时的 hand-assembled discriminating probe 实际写入并读回
  arena 内至少两个页边界；不得修改仓库测试源来凑绿。

## 验收

- QEMU 重新构建成功。
- 临时 probe 在 QEMU 上验证：两次不同长度 mmap、页对齐、跨页写读、多次
  分配、失败路径和 exit=42；必须是真实 `sto/ldo`，不能只比较返回地址。
- 既有 QEMU E2E 全量回归通过，`python3 tools/run_differential.py` 不得新增
  divergence（若整个项目被既有 wiki drift 阻断，必须贴真实退出码并区分原因）。
- 在 `.work/source/qemu` 追加普通 commit，导出一个可独立应用的 `0018` patch，
  正确追加 series；不得修改旧 patch 内容。
- 完成区必须贴真实命令/退出码；返回前必须完成 `## 审阅记录（subagent）`。

## 参考

- `code-agent/tasks/ML-014b-mmap-backing-recon.md`
- `docs/reviews/mmap-backing-recon-2026-07-18.md`
- `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`
- `components/qemu/patches/0017-*`
- `tests/scripts/run_qemu_test.py`
- `reviewer.md`

## 完成区

**状态**：已完成（架构师最终复核）

- **修改文件**：
  - `.work/source/qemu/hw/dadao/dadao-machine.c`
  - `.work/source/qemu/target/dadao/cpu.c`
  - `.work/source/qemu/target/dadao/cpu.h`
  - `components/qemu/patches/0018-target-dadao-mmap-arena-backing-ML-014c.patch`
  - `components/qemu/patches/series`
  - 本任务 md 完成区
- **QEMU commit**：`ac58f31 target/dadao: add mmap arena host backing (ML-014c)`，在 `3587e17` 上追加普通 commit；QEMU component 工作树干净。
- **实现摘要**：保持 `0x100000000`，注册独立 16 MiB host-backed RAM `MemoryRegion`；mmap 使用单调、页对齐、有界 cursor；零长度/页对齐溢出返回 `-EINVAL`，容量耗尽/越界返回 `-ENOMEM`；成功区间不回收、不复用，因此不产生重复/重叠 alias。ROM、exit MMIO、128 MiB RAM、trampoline、linker 和 flat binary 地址未改动。`munmap` 仍为 M1 accounting-only，`mprotect` 仍为 deferred/no-op。

- **验收结果**：
  - `ninja -C .work/source/qemu/build qemu-system-dadao`：通过；退出码 `0`。
  - 临时 `.work/ML-014c-mmap-backing.s` 经当前 `llvm-mc`/`ld.lld`/`llvm-objcopy` 构建：`MC_RC=0 LD_RC=0 OBJCOPY_RC=0`；QEMU 实际运行 `QEMU_RC=42`，输出 `mmap-backing-ok`。probe 执行真实 `sto/ldo`、两个页边界两侧读写、三次不同长度 mmap、零长度、`UINT64_MAX` 页对齐溢出、超 16 MiB 容量失败，以及 `munmap`/`mprotect` 返回检查。
  - QEMU-only 临时回归（从既有 58 个 E2E 测试移除 gem5 RUN 行，未修改仓库测试源）：`Total Discovered Tests: 58; Passed: 58; QEMU_ONLY_E2E_RC=0`。
  - 标准 `llvm-lit -v tests/lit/E2E`：无法完成双后端验收；QEMU 侧已执行，gem5 命令启动时报 `Permission denied`。
  - `python3 tools/run_differential.py`：退出码 `1`，在启动 `/home/holight/DADAO-gem5/build/DADAO/gem5.opt` 时收到 `PermissionError: [Errno 13]`；没有得到可据此宣称的 divergence 结论。
  - 0018 patch 已由 `git format-patch` 从 `ac58f31` 导出，且已追加到 `components/qemu/patches/series`；旧 patch 未修改。

**遗留问题**：

- gem5 构建产物当前不可由标准 E2E/differential 正常启动（外部 ownership/环境 blocker），因此双后端验收未完成；不得将本任务标为 Accepted。后续由 gem5/基础设施任务恢复后重跑双后端门禁。

## 审阅记录（subagent）

独立 reviewer 首轮判决为 Needs Revision / Partial：QEMU 侧证据完整，但当时 gem5
产物权限异常，differential 未完成，因此没有替双后端盖章。该 finding 已由 gem5
产物恢复后重新跑通，详见下方架构师复核。


## Codex Review

**审查身份**：独立 reviewer。本次未修改 QEMU 源码、patch、tests、contracts、manifests 或其它任务文件；本节是唯一追加内容。

### 重跑记录

以下命令均由 reviewer 独立执行，退出码取自命令本身：

```text
ninja -C .work/source/qemu/build qemu-system-dadao
QEMU_BUILD_RC=0
```

```text
/home/holight/DADAO-0628/.work/build/llvm/bin/llvm-mc -triple=dadao -filetype=obj -o /tmp/ml014c-review.v0TYBC/probe.o .work/ML-014c-mmap-backing.s
/home/holight/DADAO-0628/.work/build/llvm/bin/ld.lld -T tests/scripts/dadao.ld /tmp/ml014c-review.v0TYBC/probe.o -o /tmp/ml014c-review.v0TYBC/probe.elf
/home/holight/DADAO-0628/.work/build/llvm/bin/llvm-objcopy -O binary /tmp/ml014c-review.v0TYBC/probe.elf /tmp/ml014c-review.v0TYBC/probe.bin
.work/source/qemu/build/qemu-system-dadao -M dadao-m1 -nographic -bios tests/scripts/trampoline.bin -kernel /tmp/ml014c-review.v0TYBC/probe.bin
输出：QEMU 10.0.0 monitor - type 'help' for more information
(qemu) mmap-backing-ok
MC_RC=0 LD_RC=0 OBJCOPY_RC=0 QEMU_RC=42
```

该 probe 实际包含真实 `sto/ldo`、两个页边界两侧的字节读写、三次不同长度 mmap、零长度、页对齐溢出、16 MiB+1 容量失败，以及 munmap/mprotect 返回值检查；不是只比较返回地址。

```text
/home/holight/DADAO-0628/.work/build/llvm/bin/llvm-lit -v tests/lit/E2E
-- Testing: 58 tests, 6 workers --
...
Testing Time: 5.64s
Total Discovered Tests: 58
  Passed: 58 (100.00%)
STANDARD_E2E_RC=0
```

```text
git apply --check --reverse /home/holight/DADAO-0628/components/qemu/patches/0018-target-dadao-mmap-arena-backing-ML-014c.patch
PATCH_REVERSE_APPLY_CHECK_RC=0
```

正向 `git apply --check` 在当前 `ac58f31` 上失败是预期的：该 patch 的基线是 `ac58f31` 的父提交 `3587e17`，当前工作树已经包含该 patch；反向检查通过，且 `git show ac58f31` 与 `0018` 内容一致。`ac58f31` 的提交统计仅涉及任务允许的三个 QEMU 源文件；`components/qemu/patches/series` 仅追加 `0018`，旧 patch 未改。

### 约束核验

| 约束 | 结果 | 证据 |
|---|---|---|
| 固定 `DADAO_MMAP_ARENA_BASE=0x100000000` | 通过 | `target/dadao/cpu.h` 保持原值，MemoryRegion 在该地址注册 |
| 独立 host-backed RAM、明确容量 | 通过 | `memory_region_init_ram(..., DADAO_MMAP_ARENA_SIZE)`；容量为 16 MiB，并有理由说明 |
| 页对齐、零长度、溢出、容量耗尽失败 | 通过 | `cpu.c` 的 `EINVAL`/`ENOMEM` 分支；独立 probe 全部走到 exit 42 |
| 不重复、不重叠、不回收复用 | 通过（M1 语义） | 单调 cursor + 上界检查；`munmap` 仍明确为 accounting-only |
| 不改变 ROM/exit MMIO/128 MiB RAM/trampoline/linker/flat binary | 通过 | `ac58f31` 只新增 arena region 和 mmap 常量/逻辑，原地址定义未改 |
| 不伪称 mprotect 为真实权限 | 通过 | 代码注释及任务完成区明确 deferred/no-op |
| 不修改禁止范围 | 通过 | QEMU commit diff 仅为三个允许的源文件；项目根目录其它既有改动未触碰 |
| QEMU build/probe/E2E | 通过 | 本记录中的真实命令分别为 0、42、58/58 |
| differential 无新增 divergence | 未验证 | 本轮命令在等待期间被中断，没有真实退出码和输出 |
| gem5 双后端独立验收 | 未作为本轮依据 | 不对 gem5 结果作推断或盖章 |

### Finding 处置

1. **F-014c-1：双后端/differential 门禁未形成独立证据。** 任务验收明确要求 `python3 tools/run_differential.py` 不得新增 divergence。本轮该命令没有完成，不能把未完成命令当作通过，也不能声称 gem5 已通过。处置：**未关闭，阻断 Accepted**。
2. **F-014c-2：任务完成区的 gem5 权限 blocker 与本轮标准 `llvm-lit` 的 `58/58`、退出码 0 不一致。** 本轮只记录实际命令结果，不据此推断所有 gem5 语义或覆盖 differential；后续应由架构师在 gem5 环境稳定后更新任务记录并重跑 differential。处置：**保留为环境/证据一致性问题，不伪造结论**。

### 判决

**Needs Revision / Partial，不 Accepted。**

QEMU 实现、commit `ac58f31`、`0018`/`series`、真实 backing probe、QEMU build 和当前 E2E 命令均有独立证据支持；但任务验收要求的 differential 结果本轮未完成核验，且 gem5 结果不能从其它命令或 worker 叙述推导。任务状态应继续保持“部分完成”，待 gem5 可执行且由架构师/后续 reviewer 独立重跑 `python3 tools/run_differential.py` 后再作最终接受决定。

## 架构师最终复核（ground-truth，2026-07-18）

**判决：Accepted**

先处理并确认了此前的外部 blocker：`/home/holight/DADAO-gem5/build/DADAO/gem5.opt`
现为可执行 ELF，gem5 ML-014d 已有独立 reviewer 通过。随后重新执行 QEMU 任务缺失
的双后端门禁：

- `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E` → `Total Discovered Tests: 58`、`Passed: 58 (100.00%)`、退出码 `0`。
- `python3 -u tools/run_differential.py` → `AGREE(3-way)=200`、`DIVERGE=0`、`AGREE(4-way)=200`、`SAIL-DIVERGE=0`、退出码 `0`。
- QEMU 真实 backing probe → `QEMU_RC=42`，输出 `mmap-backing-ok`；probe 覆盖跨页写读、三次不同长度 mmap、零长/溢出/容量失败和 `munmap`/`mprotect` 返回值。
- `ninja -C .work/source/qemu/build qemu-system-dadao` → 退出码 `0`。
- `ac58f31` 的提交 diff 仅包含允许的三个 QEMU 源文件；`0018` patch 已追加 series，旧 patch 未修改。

首轮 reviewer 的 F-014c-1（缺少独立 differential 证据）已由上述重跑关闭；F-014c-2
（gem5 权限/证据环境问题）也已由 ML-014d 的 gem5 构建和最终四方差分关闭。QEMU
实现保留固定 `0x100000000`、独立 16 MiB backing、单调有界 cursor；M1 的
`munmap` accounting-only 和 `mprotect` deferred/no-op 边界均未被伪称为完整语义。
