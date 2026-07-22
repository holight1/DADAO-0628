# ML-014q：补齐 direct brk 证据与显式断言

**执行环境**：本地 subagent worker；承接 ML-014p independent review

**状态**：Completed；等待独立 reviewer（2026-07-18）

## 目标

不修改 gem5/QEMU/LLVM/musl 实现，只补齐 ML-014p 的可审计证据：用带条件
失败路径的 direct probe 显式断言 gem5 `SYS_brk=214` 的初始边界、页内/跨页
增长、查询返回值和第二页 backing 读回；同时整理此前多次失败/异常运行尝试，
避免只保留最终 exit 42 的尾项。

本任务只做测试/证据记录，不处理 mallocng、pointer ABI、`-O X`、puts、free、
varargs 或 ML-014a。

## Ownership

- worker 负责：仅在本任务 `.work/ML-014q-gem5-brk-evidence-probe/` 生成
  probe 源码、ELF、gem5 stdout/stderr/VMA 日志、失败尝试索引和任务记录；
  不修改 `/home/holight/DADAO-gem5` 源码。
- 可以读取 ML-014o/p 产物、当前 ELF/QEMU/链接脚本和既有 probe；不得修改
  LLVM/QEMU/musl、root patch series、docs/issues、contracts、manifests 或
  用户原始 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`。
- 不得把 `~/toolchain` 或 `~/knowledge-graph` 传给 subagent；架构师可自行
  参考，worker 不得依赖它们。

## 执行阶梯

1. 阅读 ML-014p reviewer，列出既有 probe 的所有尝试（包括 exit 1/126/0、
   `0xffff87e00000` fault 等）及最终采用结果；保留原始文件，不覆盖或删除。
2. 在本任务目录创建独立 direct probe，必须具备可见的条件失败路径，至少
   验证：
   - `brk(0) == 0x87e00000`；
   - 页内设置 `brk(base+1)` 后查询仍为 `base+1`；
   - 跨页设置 `brk(base+0x1001)` 后查询仍为该值；
   - 对第二页写入并读回 marker，证明 VMA/fault-in backing；
   - 任一断言失败返回非 42，并能从 stdout/exit code 定位失败项。
3. 使用当前 gem5 source `c7e92c7f80` 构建产物运行 probe；每次尝试记录命令、
   exit、stdout、stderr、VMA/fault 日志和采用/废弃原因。若要复核 mmap，只能
   读取既有 mmap probe，不能把未直接观测的返回地址写成新证据。
4. 完成本任务记录和自审，明确“probe evidence accepted”与“实现/allocator
   完成”不同；等待独立 reviewer。

## 验收

- 存在可读的 probe 断言代码和至少一次 exit 42 的完整日志；失败路径实际可
  触发或至少由代码审查明确存在。
- 每项 brk/读回断言有明确输出或机器可判定的失败退出码；历史失败尝试没有
  被隐去，且没有覆盖原始证据。
- 未修改任何实现源码和越权文件；ML-014p 的 source/ABI 结论仍只接受到
  “边界统一”，ML-014f/ML-014a 不得关闭。
- 有 subagent 自审，随后由独立 reviewer 复核。

## 完成区

**Finding：Probe evidence accepted（仅限 direct `SYS_brk` 证据；不等同于实现、allocator、ML-014f 或 ML-014a 完成）**

### 新 probe 与断言

- 新增 probe：`.work/ML-014q-gem5-brk-evidence-probe/brk_assert_probe.s`，最终
  ELF/BIN/O 也保留在同一目录；没有覆盖 ML-014p 的旧 probe。
- 最终源码用 `setzw rd1, 0, 0x87e; shlu rd1, rd1, 20` 构造期望值
  `0x87e00000`，并有真实条件分支：
  1. `brk(0) == 0x87e00000`；
  2. 设置 `brk(base+1)` 后 setter 返回 `base+1`；
  3. 查询返回值保持 `base+1`；
  4. 设置 `brk(base+0x1001)` 后 setter 返回该值；
  5. 查询返回值保持 `base+0x1001`；
  6. 在第二页起点 `base+0x1000` 写入 `0x5a` 并读回，才进入 PASS。
- 失败分支输出 `ML-014q FAIL-n` 并以 n（1–6）退出；成功输出
  `ML-014q PASS` 并以 42 退出。失败路径已实际触发：把临时副本期望值改为
  `0x87d00000` 后，`run_fail_expected/` 记录 `exit=1`、
  `ML-014q FAIL-1`；最终源码已恢复为 `0x87e00000`。

### 构建与最终采用运行

使用当前 `/home/holight/DADAO-gem5` source `c7e92c7f804febcdfee0b8e4ac19792683a8fea5`
（短提交 `c7e92c7f80`）对应的现有构建产物
`/home/holight/DADAO-gem5/build/DADAO/gem5.opt`；source 工作树在任务期间保持 clean。

```text
/home/holight/DADAO-0628/.work/build/llvm/bin/clang --target=dadao -c \
  -o .work/ML-014q-gem5-brk-evidence-probe/brk_assert_probe.o \
  .work/ML-014q-gem5-brk-evidence-probe/brk_assert_probe.s
/home/holight/DADAO-0628/.work/build/llvm/bin/ld.lld -T tests/scripts/dadao.ld \
  .work/ML-014q-gem5-brk-evidence-probe/brk_assert_probe.o \
  -o .work/ML-014q-gem5-brk-evidence-probe/brk_assert_probe.elf
/home/holight/DADAO-0628/.work/build/llvm/bin/llvm-objcopy -O binary \
  .work/ML-014q-gem5-brk-evidence-probe/brk_assert_probe.elf \
  .work/ML-014q-gem5-brk-evidence-probe/brk_assert_probe.bin
timeout 30s /home/holight/DADAO-gem5/build/DADAO/gem5.opt \
  --outdir=/home/holight/DADAO-0628/.work/ML-014q-gem5-brk-evidence-probe/run4 \
  --debug-flags=Vma,PageTableWalker,Faults \
  --debug-file=brk_assert_probe.debug.log \
  /home/holight/DADAO-gem5/tests/dadao/dadao_se.py \
  /home/holight/DADAO-0628/.work/ML-014q-gem5-brk-evidence-probe/brk_assert_probe.elf
```

最终命令 exit=`42`。完整 stdout 位于
`.work/ML-014q-gem5-brk-evidence-probe/run4/stdout`，关键内容为：

```text
SIM_START
SIM_END: trap-exit code=42
ML-014q PASS
```

stderr 位于 `run4/stderr`，只有 gem5 的既有 dot/DRAM/legacy-stat warning，
没有 fault。`run4/brk_assert_probe.debug.log` 的 VMA/fault 证据为：

```text
0:     ... creating vma (stack) [0x7fffffffe000 - 0x7ffffffff000]
9000:  ... creating vma (heap)  [0x87e00000 - 0x87e01000]
21000: ... creating vma (heap)  [0x87e01000 - 0x87e02000]
```

该日志未出现 page-table fault；第二页 marker 的写读比较由 probe 自身通过后
才会进入 `ML-014q PASS`。因此本任务对 direct brk 的初值、页内/跨页查询保持和
第二页 backing 提供了可判定的证据，但不把 VMA 日志或 exit 42 扩大解释为
allocator/E2E 完成。

### 所有尝试索引

ML-014p 旧目录中的原始文件均保留，未删除或覆盖；本任务补充索引如下：

| 原始文件/目录 | 实际结果 | 处置 |
|---|---|---|
| `ML-014p.../brk_boundary_probe.stdout` → `m5out2` | exit 1 | 旧无断言 probe 的中间尝试，保留 |
| `brk_boundary_probe.exec.stdout` → `m5out3` | exit 1 | `Exec,Vma` 运行，保留 |
| `brk_boundary_probe.stdout4` → `m5out4` | exit 126 | 异常中间尝试，保留 |
| `brk_boundary_probe.stdout5` → `m5out5` | exit 126 | 异常中间尝试，保留 |
| `brk_boundary_probe.stdout6` → `m5out6` | exit 0 | 旧 probe 中间结果，不能当 PASS，保留 |
| `brk_boundary_probe.stdout7` → `m5out7` | exit 0 | 旧 probe 中间结果，不能当 PASS，保留 |
| `brk_boundary_probe.stdout8` → `m5out8` | exit 0 | 旧 probe 中间结果，不能当 PASS，保留 |
| `brk_boundary_probe.stdout9` → `m5out9` | page-table fault，VA=`0xffff87e00000` | 原始 fault 证据，保留 |
| `brk_boundary_probe.stdout10` → `m5out10` | exit 42，但旧汇编无真实条件断言，且输出含旧 raw/NUL 尾项 | 仅作历史对照，不作为 q 验收 |
| `run1/` | exit 1：`invalid debug flag 'PageTable'` | 调试参数错误，真实 stdout/stderr 保留 |
| `run2/` | exit 42，但 PASS 写长度多 1 字节导致 NUL | 修正 probe 输出长度后不采用，保留 |
| `run3/` | exit 42，条件路径通过，输出已干净 | 有效复核，最终 run4 重建后再次采用 |
| `run_fail_expected/` | exit 1，stdout=`ML-014q FAIL-1` | 实际失败路径验证，保留 |
| `run4/` | exit 42，stdout=`ML-014q PASS`，VMA/fault 日志完整 | 最终采用结果 |

### 自审与范围边界

- 自审确认 probe 源码包含六个 `breq` 断言对应的失败跳转，失败消息和退出码
  可定位；第二页 marker 比较不是注释性承诺，而是 PASS 前的实际控制流条件。
- 自审确认最终源码已恢复正确期望值，`run4` ELF 与源码一致；run4 命令使用
  `c7e92c7f80` 对应 gem5 构建产物，且 gem5 source `git status --short` 为空。
- 本任务没有修改 `/home/holight/DADAO-gem5`、QEMU、LLVM、musl、root patch
  series、`docs/issues.yaml`、contracts、manifests 或用户原始
  `ML-014a-musl-e2e-malloc-printf.md`；没有使用或传递
  `~/toolchain`、`~/knowledge-graph`。
- 本任务没有重跑 QEMU、mallocng、pointer/read-write probes、全量 E2E、
  differential、`make check`，也没有验证 mmap 返回地址；这些仍是未跑项，不能
  从本任务 exit 42 推出。
- 本任务不处理 `-O X`、puts、free、varargs、pointer ABI，也不关闭 ML-014f 或
  ML-014a。ML-014p 的 source/ABI 结论仍限于边界统一；整体仍需独立 reviewer
  复核后再决定是否接受。

**自审结论：Confirmed（仅 direct brk evidence probe；等待独立 reviewer）。**

## 审阅记录

### 独立 reviewer 复核（2026-07-18）

**Finding：Needs-fix（仅限 direct `SYS_brk` evidence；不否定 brk 实现本身，也不扩展到 allocator/E2E）**

本轮只读本任务 MD、ML-014p review、`.work/ML-014q-gem5-brk-evidence-probe/`
下的 probe/ELF/五组 stdout、stderr、stats 和 debug log，并核对
`/home/holight/DADAO-gem5` 的 `c7e92c7f80`。没有修改 gem5 source，没有删除
任何产物；gem5 source 工作树在 `c7e92c7f80` clean。

#### 1. 汇编控制流与地址计算

- `setzw rd1, 0, 0x87e` 后 `shlu rd1, rd1, 20` 构造 `0x87e00000`；
  `brk(0)`、页内 setter/query、跨页 setter/query 均以 `breq` 成功分支或
  `jump failN` 失败分支相连。`add rd0, rd3, rd1, rd5` 符合 DADAO 双目的
  128-bit 加法格式：`rd3` 接低半部，因此确实得到 `base+0x1000`；不是把结果
  丢进 `rd0`。
- `rd2rb rb8, rd3, 1` 后 `sto rd5, rb8, 0` / `ldo rd6, rb8, 0`，并以
  `breq rd6, rd5, pass` 控制是否进入 PASS；marker 比较是实际执行路径，不是
  注释承诺。
- `run4` 的反汇编与最终源码一致；`run_fail_expected` 是临时把期望边界改错
  后生成的独立 ELF，最终源码和 `brk_assert_probe.elf` 已恢复正确值。
- 发现一个失败诊断缺口：`fail5` 进入统一分发时，`rd5` 仍是前面构造页大小
  的 `1`，并未保持失败编号 `5`。因此 `fail5` 的 `breq rd17, rd5,
  fail5_msg` 不会命中，随后 1–4 也不命中而落入 `fail6_msg`；退出码仍由
  `rd20=5` 给出，但 stdout 会错误显示 `ML-014q FAIL-6`。当前
  `run_fail_expected` 只触发了 check 1，不能覆盖这个问题。需修正分发并至少
  增加一次 check 5 的失败路径复核后，失败编号才满足“可定位失败项”。

#### 2. 五组 q 运行产物

- `run1` 的 stderr 是 `invalid debug flag 'PageTable'`，stdout 只有 gem5
  启动信息，且没有 debug log；记录为参数错误而非 probe 结果，准确。
- `run2` exit 42 且 VMA 两页存在，但 stdout 末尾确有一个 NUL；与“PASS
  写长度多 1 字节”的处置描述一致，不能作为最终干净输出。
- `run3`、`run4` 均为 exit 42，stdout 可读尾部为
  `SIM_END: trap-exit code=42` 和 `ML-014q PASS`，无 raw/NUL 尾项；stderr
  只有既有 gem5 warning。`run_fail_expected` 为 exit 1，stdout 为
  `ML-014q FAIL-1`，stderr 同样只有既有 warning，失败路径真实生效。
- `run2/3/4` debug log 均真实包含
  `[0x87e00000 - 0x87e01000]` 与 `[0x87e01000 - 0x87e02000]` 两个 heap
  VMA；`run_fail_expected` 在 check 1 失败前只有 stack VMA，这是预期的。
  日志足以证明 VMA 页范围和无显式 fault 输出，但不应把它描述成包含逐次
  PTE/fault-in 事件的日志；第二页 backing 的主要证据仍是 probe 的 marker
  写读控制流及 exit 42。

#### 3. ML-014p 历史失败索引

- `.work/ML-014p-gem5-brk-boundary-unify/` 中 `m5out2..m5out10` 和对应
  `brk_boundary_probe.stdout*` 全部保留；独立读取确认 exit 序列为
  `1, 1, 126, 126, 0, 0, 0, fault(0xffff87e00000), 42`。q 记录明确把
  `m5out6..m5out8` 的 exit 0 标为旧中间结果、不能当 PASS，也保留了旧 fault
  和 `m5out10` 的 raw/NUL 历史尾项，没有把旧结果冒充 q 的最终 PASS。
- 本轮没有发现 ML-014p review 所指出的历史失败遗漏；run1 的 debug flag
  失败、run2 的 NUL、run3/run4 的采用关系也都有对应产物。

#### 4. 范围与结论

- `c7e92c7f80` 仍只改 gem5 `src/arch/dadao/process.hh` 的 `BrkBase`，本轮
  未发现 probe 任务对 gem5/QEMU/LLVM/musl、root patch series、issues、
  contracts、manifests 或 `ML-014a` 的实现修改。
- 不能由本任务推出 mmap 地址、allocator、ML-014f 或 ML-014a 完成；任务记录
  对这些未跑项的边界声明准确。

**Reviewer decision：Needs-fix。** 修正 `fail5` 失败消息分发，并用显式失败
运行证明 check 5 的退出编号/消息后，可重新复核 direct brk evidence；在此之前
不接受“所有失败项均可定位”的验收项。

### 后续修正（2026-07-18）

独立 reviewer 发现的 check 5 失败消息误报已由 ML-014r 修正并经独立 reviewer
Accepted（`2f1f460`、`36fe0d5`）；ML-014q 的直接断言证据应与 ML-014r 的
`PASS/42`、`FAIL-5/5` 路由结果联合阅读。ML-014q 原始 `Needs-fix` 记录保留为
历史审计，不再作为当前 evidence routing blocker。
