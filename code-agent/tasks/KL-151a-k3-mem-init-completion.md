# KL-151a：K3 `mem_init` 完成与首个 post-memory 边界

**状态**：独立 review 首轮 findings 已修复，待复核

**日期**：2026-07-29  
**前置**：KL-150a  
**后续**：KL-152a（由本任务 evidence 冻结的首个 post-memory 阻塞）

## 背景

KL-150a 已以 QMP raw memory 为主 oracle，证明 Linux 真实进入
`setup_arch()`、完成 `paging_init()` 并进入 `mem_init()`。最终 frozen
QEMU HEAD 为 `dfc7842229c139cc606141b82845ecf20086e657`，Linux HEAD 为
`06c3d571a8ae249e451dc4f2151e6bfd8e8a5873`。

当前第一个实证阻塞是 DADAO LLVM `KCFLAGS=-O0` 的 bool stack-slot
lowering：QEMU 报 `EXCP_MALIGN pc=0x80284100`，符号位于
`mm/page_alloc.c::free_pcp_prepare`。现有源码在非 `CONFIG_DEBUG_VM`
路径以 `bool` 返回 `free_pages_prepare()` 的结果；后端把单字节栈槽以
八字节 `ldo` 重新加载。

本任务只关闭这条实证链并证明 `mem_init()` 真正完成。不得把它扩大为
“Linux 已完成 early boot”、trap/syscall、timer/IRQ、调度、MMU 用户页表、
initramfs、TTY、login 或用户态能力。

## 目标

1. 在既有 `CONFIG_DADAO_K3_O0_LINK_COMPAT` 边界内修复
   `free_pcp_prepare` 当前实证的 natural-width carrier 问题；
2. 如继续执行后在 `mem_init()` 返回前遇到同类 `-O0` bool/stack-slot
   MALIGN，可按“一个实证位置、一个窄修复”的方式继续关闭，但必须逐项记录
   PC、符号、反汇编/栈槽依据；禁止预防性批量改写全部 generic bool；
3. 在 `arch/dadao/mm/init.c::mem_init()` 的最后一个真实初始化动作之后，
   写入新的 guest-authored progress word：
   - 地址 `0x87fd0028`；
   - 值 `0x4b4c3135314d4944`（ASCII `KL151MID`，mem-init done）；
4. 用 QMP 证明旧 KL-149/KL-150 progress 保持有序且新 word 只在
   `memblock_free_all()` 和 `mem_init_print_info()` 返回后出现；
5. 达到新 progress 后继续观察并冻结第一个真实 post-memory 阻塞，作为
   KL-152a 输入。

## 实施约束

- Linux component 必须用普通 commit；导出新 patch，追加
  `components/linux/patches/series`，记录完整 commit 与 stable patch-id。
- 预计不修改 QEMU；若确有不可回避的诊断需求，先在任务记录中说明原因，
  且不得借机扩张设备或体系结构能力。
- 所有 generic Linux 改动必须受 `CONFIG_DADAO_K3_O0_LINK_COMPAT`
  控制；普通配置保持原 `bool` 类型和语义。
- 跨编译单元接口若改变 carrier，声明与定义必须同步；只能返回规范化
  `0/1`，不得改变结构布局、持久数据格式、UAPI、模块 ABI 声明或函数参数。
- 继续固定 `KCFLAGS=-O0`，不处理 KL-148b 的默认 `-O2` 问题。
- progress 必须由 `mem_init()` C 函数在末尾写入；禁止在 `head.S`、
  HBI ROM、runner、QEMU 或更早函数预填。
- 保留 `0x87fd0000..0x88000000` bring-up scratch reservation，检查 Image、
  ELF、stack 与扩展后的 48-byte oracle window 不重叠。
- 不显式参考 `~/toolchain` 或 `~/knowledge-graph`。
- 不修改、不提交顶层既有未跟踪 `gcc-torture-results.json`。

## 验收

新增 `tests/scripts/run_kl151a_mem_init_completion.py`，必须 fail-closed：

1. 验证 KL-150a 根提交/任务记录和 frozen summary
   `.work/evidence/kl150a-linux-early-console/summary.json` 的 SHA256
   `844f5ece4ea5b837e7ada01e4b2c841aecf7118ffb18b814de55eb24fe28d83c`；
   精确检查其中 `PASS 4/4, FAIL=0, SKIP=0`、QEMU/Linux identity、正例
   五个旧 words、console anchors 和 wrong-mode oracle；
2. 检查 Linux/QEMU source worktree clean；精确绑定 Linux 全 patch queue
   的名称、commit、stable patch-id；QEMU 至少固定 KL-150a parent/HEAD、
   38 个 commit/patch 总数及 0037/0038 身份。历史 QEMU 0001..0036
   replay mismatch 作为既有债务记录，不得静默声称已修复；
3. 从 `mrproper` fresh build Linux `Image`，拒绝 forbidden diagnostics，
   验证 ELF64 big-endian、`EM_DADAO`、入口、无 undefined symbol、
   Image/scratch non-overlap，并记录 Image/vmlinux SHA256；
4. QEMU 用 `-S` 启动，`cont` 前 QMP 读取完整 48-byte oracle 全零；
5. 正例逐轮拒绝非法/跳级状态，并最终精确得到：
   `(KL149AHE, 0, KL150SAE, KL150SAD, KL150MIN, KL151MID)`；
   达标后延迟采集的最终快照必须再次精确匹配；
6. source contract 必须隔离 `mem_init()` 函数体并验证
   `KL150MIN -> memblock_free_all -> mem_init_print_info -> KL151MID`
   的顺序；扫描 `head.S` 与两份 HBI ROM，拒绝新值被预填；
7. console 仅为 secondary observation。正例要求 KL-150a anchors 仍唯一
   有序，并出现真实 `mem_init_print_info()` 的 `Memory:` 行；使用同一
   positive Image 加 `-serial none` 时，QMP 必须仍完整而 console verdict
   必须为 false；
8. wrong-mode ROM 必须保持
   `(0, KL149BAD, 0, 0, 0, 0)` 并 shutdown；
9. evidence 保存命令、component/patch/QEMU/Image identity、initial/final
   raw bytes、逐级 snapshots、console bytes、异常 trace、首个下一阻塞及
   明确 `PASS/FAIL/SKIP` 计数；不得把 QEMU 仍运行、日志非空或旧 progress
   当成 PASS；
10. 完整 runner 至少执行一次并为 `PASS 3/3, FAIL=0, SKIP=0`；结束时两个
    component source worktree仍 clean。

## 非声明

本任务只声明 `mem_init()` 的真实完成和第一个 post-memory 观察边界。即使
console 打印继续前进，也不声明 scheduler 可切换、trap/syscall 正确、
timer/外部中断可用、MMU 用户地址空间可用、initramfs `/init` 可执行、
TTY/login 或用户态 hello。

## 实施记录

### 既有部分审查与续做

接手时保留并核验了根提交 `382a9d3` 已定义的合同、Linux ordinary
commit `537c61baef6e8ca04cc3d77f6cc9da7856fd6d5e`、已导出的 0008 patch
以及尚未提交的 runner，没有重做或丢弃前一个 worker 的成果。

0008 在 `CONFIG_DADAO_K3_O0_LINK_COMPAT` 下只把
`free_pages_prepare`、`free_pcp_prepare` 与
`free_unref_page_prepare` 的实证真假 carrier 改为自然字宽，普通配置仍为
原 `bool`；同时在 `memblock_free_all()` 和
`mem_init_print_info(NULL)` 均返回后，由 `mem_init()` C 函数写
`0x87fd0028 = 0x4b4c3135314d4944`。对应身份为：

- commit `537c61baef6e8ca04cc3d77f6cc9da7856fd6d5e`；
- patch `0008-dadao-complete-K3-mem_init-progress.patch`；
- stable patch-id `dd1a1b39796f9ebf27ed6e6f07ba02c22252fcd4`。

### 继续执行暴露的两个同型阻塞

第一次完整 runner 在旧五个 words 后停住，首错为
`EXCP_MALIGN PC=0x80280d8c`，符号
`mm/page_alloc.c::page_expected_state`。反汇编证明函数先在
`rb1+43` 以 `stb` 保存 bool return，随后在返回点用八字节 `ldo` 取回。
因此只对该实证函数追加 config-gated natural-width result carrier：

- commit `3e83c7744f5d093eba3a46284416b8409f3d452c`；
- patch `0009-dadao-widen-page-expected-state-result-for-K3-O0.patch`；
- stable patch-id `bc9463edbe258e4e3c417c5c9563f00748d57cb2`。

第二次完整 runner 继续前进后停在
`EXCP_MALIGN PC=0x80282400`，符号
`mm/page_alloc.c::compaction_capture`；其 return slot 为 `rb1+31`，
同样由 `stb` 写入、`ldo` 取回。只对该实证函数的两个 config 分支同步
改用受配置约束的自然宽 carrier：

- commit `8f0b11da8346dc46402974e7a6a8626cff103ed3`；
- patch `0010-dadao-widen-compaction-capture-result-for-K3-O0.patch`；
- stable patch-id `80d0cabb985e3d30b95c8cdc61038ea0f494bc0b`。

三个 patch 都是 ordinary Linux commits 的精确导出，并按
`0008 -> 0009 -> 0010` 追加到 series。没有修改 QEMU。

### 最终 runner 与 evidence

最终执行：

```sh
cd /home/holight/DADAO-0628
python3 tests/scripts/run_kl151a_mem_init_completion.py
```

结果：

```text
PASS: KL-151a mem_init completion (3/3, FAIL=0, SKIP=0)
```

runner 从 `mrproper` fresh build，精确绑定 Linux 全 10 个
commit/patch/stable patch-id、QEMU KL-150a frozen HEAD/patch 数量/binary
身份和 KL-150a summary SHA256。最终 Linux 身份：

- Image：7,655,516 bytes，SHA256
  `e3d480226d26ba8c5672151471407cc88e187167d8800b30dc303aafde97818a`；
- vmlinux：8,381,096 bytes，SHA256
  `b9f6a058a63708950f153317d36fb4a80f7a90176944c16e9283d194a8f353cb`；
- `_end = 0x8074d05c`，低于 scratch `0x87fd0000`。

positive 和 `-serial none` 都从启动前 48 字节全零开始，逐级观察并最终
精确保持：

```text
(KL149AHE, 0, KL150SAE, KL150SAD, KL150MIN, KL151MID)
```

positive console 的四个真实 anchors 均唯一有序，计数 `[1,1,1,1]`，
包括 `Memory:`；`-serial none` 使用同一 Image，QMP words 完整但
console 0 字节、verdict=false。wrong-mode ROM 保持
`(0, KL149BAD, 0, 0, 0, 0)` 并 shutdown。

完整机器可读证据位于
`.work/evidence/kl151a-mem-init-completion/summary.json`，SHA256
`e6682d902e067e69ce0384d468ec3067e831999d2c573633be1ca6d2a093cd08`。
同目录保存 build/QEMU 命令、initial/final raw bytes、逐级 snapshots、
console bytes、exception trace、符号解析和反汇编。Linux 与 QEMU source
worktree 在最终运行后均 clean。

### 首个下一阻塞（KL-152a 输入）

两个 console transport 场景都在 `KL151MID` 已写入且延迟复读保持后，
冻结同一个首个 post-memory 阻塞：

- exception：`EXCP_MALIGN`（index 3）；
- PC：`0x000000008027985c`；
- symbol：`prepare_alloc_pages+0x1c8`，symbol start
  `0x0000000080279694`；
- source：`mm/page_alloc.c::prepare_alloc_pages`；
- stack-slot 证据：在 `rb1+71` 以 `stb` 写 bool return，在返回点用
  八字节 `ldo` 读取。

runner 会自动解析 positive/`-serial none` trace、解析符号、校验这组
反汇编，并要求两个场景身份一致。该异常发生在 `mem_init()` 完成 marker
之后，不降级 KL-151a verdict；KL-152a 应从这个精确边界继续，仍不得据此
宣称 scheduler、trap/syscall、timer/IRQ、MMU 用户态、initramfs、TTY、
login 或用户态 hello 已可用。

## Review

### 独立 reviewer 首轮

独立 reviewer 结论为 **Not Accepted**，要求全部关闭以下 findings：

1. runner 开始时必须使旧 PASS summary 失效，采用干净单次 evidence
   语义；失败不能遗留旧 PASS，成功后才能原子发布 summary；
2. 0009/0010 缺少可独立复核的中间实证，必须分别在 Linux
   `537c61bae...` 和 `3e83c7744...` 重建、运行并保存 Image、commit、
   trace、symbol、disassembly、PC/stack-slot 与 size/SHA256；
3. summary 必须绑定当前 runner 身份，并通过无哈希自引用环的 manifest
   绑定关键 raw/trace/console/symbol/disassembly/命令日志；
4. source contract 必须证明 `KL151MID` write 是 `mem_init()` 的最后一条
   真实语句；
5. 任务 MD 必须记录首轮 findings、修复和验证；
6. 修复后完整 runner 必须保持 `PASS 3/3, FAIL=0, SKIP=0`，component
   clean，`py_compile` 与 `diff --check` 通过。

### Findings 修复

1. runner 的第一项操作现在会整体删除旧 KL-151a evidence 目录，创建全新
   `RUNNING.json`。任何 gate 失败时都会删除 `summary.json` 和
   `RUNNING.json`，原子发布本次 `FAILED.json`；成功时先完成全部 gate，
   再以 `os.replace` 原子发布 summary。旧文件不能混入新目录。修复过程
   中一次真实 QMP socket-path 失败验证了旧 summary 已消失且 component
   worktree 被清理；随后修复短 `/tmp` transport 并完成最终成功运行。
2. runner 使用两个临时 detached Git worktree 和独立 output tree：
   - `537c61baef6e8ca04cc3d77f6cc9da7856fd6d5e`：
     Image 7,655,516 bytes，SHA256
     `9bc0d953ecb4935eba596a2763a5a0f8c257aeb2e01980207122f7c85c9e2bd4`；
     trace 2,597 bytes，SHA256
     `18ea12a543bd73f32cb2c1ccbb3a89d6e23f76ab8847feb41603ab1115300d27`；
     symbol log 1,071,282 bytes，disassembly 1,102 bytes。QMP 精确复现
     `page_expected_state+0x1c0` 的 `PC=0x80280d8c`、`rb1+43`
     `stb -> ldo` MALIGN。
   - `3e83c7744f5d093eba3a46284416b8409f3d452c`：
     Image 7,655,516 bytes，SHA256
     `e50e27fed887e98bace9e2cfeefbfe06e06e1e3af25b8b6e9adc50e6dcc2672f`；
     trace 1,926 bytes，SHA256
     `4270d765f3c9aecc1ad815cb25c1a45e2360f3f5e3f5769fa07e813e0eb22128`；
     symbol log 1,071,281 bytes，disassembly 1,112 bytes。QMP 精确复现
     `compaction_capture+0xe8` 的 `PC=0x80282400`、`rb1+31`
     `stb -> ldo` MALIGN。
   两阶段都从 48-byte 全零 oracle 开始，最终只达到旧五个 words、
   `KL151MID=0` 后 shutdown；Image/raw/trace/console/runtime/build/commit/
   status/worktree-remove identities 均写入 summary 的
   `carrier_fix_evidence`。临时 worktree/output 在每阶段结束后删除，最终
   component HEAD 未改变且 clean。
3. summary 绑定 runner 62,078 bytes、SHA256
   `74f6c02ef1fa4ac5320ffe77a313614b541301b4e30b7f5b1bfc664b6ca6b5c7`。
   独立 `artifact-manifest.json` 在 summary 之前发布，覆盖 evidence
   目录内本次运行的全部 artifacts，包括历史 Image，以及历史/最终
   raw、trace、console、symbol、disassembly 和命令日志。最终
   Image/vmlinux、QEMU binary 与 runner 则由 summary 直接绑定
   path/size/SHA256。manifest 明确排除自身和 summary，避免循环；
   summary 再绑定 manifest 20,478 bytes、SHA256
   `a661f9241bb028f8aaf3cdd23bb582e8db788cb8c1be5d75f48d6be4f64923df`。
   最终逐项重新计算 85 个文件的 size/SHA256，全部匹配。
4. source contract 除原有
   `KL150MIN -> memblock_free_all -> mem_init_print_info -> KL151MID`
   顺序外，现在正则隔离唯一 completion write，并要求其后到
   `mem_init()` 右花括号之间无任何非空内容；因此它必须是最后一条真实
   语句。
5. 本节已记录 reviewer 首轮意见、修复设计和最终实证。

### 修复后验证

最终执行：

```sh
cd /home/holight/DADAO-0628
python3 tests/scripts/run_kl151a_mem_init_completion.py
```

结果为 `PASS 3/3, FAIL=0, SKIP=0`。最终 summary SHA256 为
`e6682d902e067e69ce0384d468ec3067e831999d2c573633be1ca6d2a093cd08`；
summary 中 runner hash 与当前文件一致，manifest hash 与当前文件一致，
manifest 的 85/85 artifacts 均通过重算。`RUNNING.json`、`FAILED.json`
均不存在；Linux/QEMU component worktree clean，Linux 只有最终 detached
worktree `8f0b11da8...`；`python3 -m py_compile`、`git diff --check`
通过。顶层 `gcc-torture-results.json` 保持未跟踪且未修改。

### 独立 reviewer 第二轮与主控低风险修复

独立 reviewer 第二轮确认首轮 2 High + 2 Medium 全部关闭，结论
**Accepted**；仅剩两个 Low：

1. 临时 worktree remove 失败时 runner 尚未检查返回码、路径消失和 Git
   注册表；
2. 任务文字曾把最终 Image/vmlinux 误述为 artifact manifest 内文件。

主控直接关闭这两个 Low：runner 现在要求 `git worktree remove` 成功，
临时 source/output 路径均消失，并通过
`git worktree list --porcelain` 证明临时路径不再注册；对应 list-after
日志也纳入 evidence manifest。上文已改为准确边界：manifest 覆盖 evidence
目录全部产物，summary 单独绑定最终 Image/vmlinux、QEMU binary 与 runner。
修改后完整 runner 再次 `PASS 3/3, FAIL=0, SKIP=0`，本节记录的
summary/manifest/runner 身份均来自这次最终运行。主控二次复核结论：
**Accepted**。
