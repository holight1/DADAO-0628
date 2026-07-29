# KL-149a：K3 Linux linked image 与 reset handoff

**状态**：PASS（独立 review Accepted）
**日期**：2026-07-29
**前置**：KL-148a
**后续**：KL-150a（early console + boot progress）

## 目标

1. 在 KL-148a 的 `KCFLAGS=-O0` 边界内完成 Linux 5.4 `vmlinux` 链接；
2. 提供链接地址/入口均为 `0x80000000` 的 flat `Image`，匹配
   `dadao-m1 -kernel` 的 frozen raw-loader contract；
3. 实现最小但真实的 architecture entry、linker script 和链接所需
   runtime hooks，不允许用“永远不调用”的空符号批量掩盖未定义项；
4. 提供 ROM reset trampoline，把 QEMU 的
   `hypv/cfx_power @ 0x00100000` 状态按现行 HBI/K1 contract 交给
   supervisor kernel entry；
5. 用 guest-authored early marker + host raw-memory oracle证明同一
   `Image` 真正到达 Linux `_start`，并保存完整构建/运行 evidence；
6. Linux component 主体变更形成 patch 0003，并以独立 review follow-up
   patch 0004/0005 收敛 mode/O0/oracle 门禁；runner fail-closed。

## 验收边界

- `make vmlinux` 成功且 `llvm-nm -u vmlinux` 无未定义符号；
- ELF64、big-endian、Machine=0xDA0，entry=`0x80000000`；
- flat `Image` 首字节对应 `_start`，大小不超过 QEMU 128 MiB RAM；
- QEMU 必须经 ROM handoff 后由 kernel image 写出正确 early marker；
  timeout、host log、仅 PC 猜测均不能判 PASS；
- runner 检查 ROM/Image hash、marker 地址和值、QEMU binary identity、
  patch/commit identity和 Linux clean worktree；
- 无 SKIP。

## 实现约束

- 继续显式使用 `KCFLAGS=-O0`；KL-148b 单独拥有默认 `-O2`；
- 不复制历史 `arch/dadao` 实现；可依据当前 contract/K2 evidence重新
  设计；
- early marker 只能位于 test-machine 专用、defconfig 可关闭的 bring-up
  路径，并继续进入 `start_kernel`，不得以写 marker 后退出冒充启动；
- ROM handoff 必须与现行 QEMU reset run-mode/cfx 状态一致，不能只做
  早期 ADR-0004 的裸 jump；
- 本任务不声称 console、memblock、trap、timer、MMU、initramfs 或
  userspace 已工作。

## 计划记录

先执行一次完整 `vmlinux` link，以真实 undefined/compile diagnostics
确定最小 architecture object 集；逐项实现并记录，不预先批量添加 stub。

## 完成记录

### 实现

- Linux component commits：
  - `fca53b59dc8048ba9c4cd3965e488d8a11e07dbd`；patch 0003
    `dadao-link-K3-image-and-add-reset-entry`；stable patch-id
    `476ab7b802482f307123dc7aa3e165d948323ca0`；
  - `b5f89a803600ecbe445c3aad64fceb51d8a61140`；独立 review
    follow-up patch 0004 `dadao-harden-KL-149a-mode-and-O0-link-gates`；
    stable patch-id
    `94de1e4bf4c4f25c9771963989f43bfce0125a2b`。
  - `f1349f6ee7858f8be8f6e91d18ea9b006f52c281`；第二轮 review
    follow-up patch 0005 `dadao-identify-KL-149a-bad-mode-path`；
    stable patch-id
    `aa1651702ecaa5c80918c376662f72489e9e015f`。
- 新增真实 `_start`、`vmlinux.lds.S`、architecture kernel/mm objects、
  flat `Image` target，以及 generic Linux 链接所需的 page/ELF/syscall/
  ptrace/io 接口。`_start` 建立 M1 保留 scratch 内的临时栈；在可由
  defconfig 关闭的 `CONFIG_DADAO_K3_EARLY_MARKER` 路径中，先执行真实
  `trap cfx_smon`，读取硬件 frame 保存的 trap 前
  `prev_run_mode`，只有值为 `supv(2)` 才写 marker。一个有限计数的
  observation window 后继续调用 `start_kernel`，没有写 marker 后退出。
- RAM contract 固定为 `0x80000000 + 128 MiB`；memblock 保留完整
  `_start.._end` image 和 `0x87fd0000..0x88000000` bring-up scratch，
  避免 init/head 段或 early stack 被 allocator 覆盖。
- reset trampoline 复用 KL-110a 已冻结的 HBI §3 顺序：清除 12 个
  hypv delegation register，设置 previous run mode=`supv`、previous
  CFX mask=`~0`、cause IP=`0x80000000`，再执行
  `escape cfx_power,0`。ROM 本身不包含 marker 值。
- 尚未实现的 process context switch、ret-from-fork、PTBR/TLB flush、
  trap vector、timer clocksource 和 external interrupt 路径均显式
  fail-closed 或保持硬件全 mask，不把空实现声称为能力。

### `KCFLAGS=-O0` 链接边界

第一次完整链接先消除了真实 architecture interface 缺口；剩余 undefined
全部来自 Linux 5.4 在正常优化构建中依赖 constant-false 分支消除的禁用特性
路径（FRONTSWAP、THP/HUGETLB、MEMCG_KMEM、DAX、SMP、PTE_DEVMAP）。
本任务没有启用这些特性，也没有散落批量伪符号，而是集中增加
`CONFIG_DADAO_K3_O0_LINK_COMPAT`：

- 仅给出对应 feature-disabled 的返回语义；
- 任一所代表特性被启用时编译期 `#error`；
- `__OPTIMIZE__` 出现时编译期 `#error`，确保它不会进入未来正常优化
  build；
- 无 cycle counter 时 `get_cycles()` 为显式常量 0，不虚构 timer。

`CONFIG_KALLSYMS` 在本阶段显式关闭。打开后生成的 kallsyms 第二链接会让
当前 DADAO `R_DADAO_RELA_PAGE` 窄距模型对 linker-generated symbols
报 range overflow；KL-149a 不以放宽 relocation 或伪造 kallsyms 为代价
扩大范围。该限制不影响本任务的 linked-image/reset-entry 证明。

### 自动验收

新增：

- `tests/scripts/gen_kl149a_linux_handoff.py`
- `tests/scripts/run_kl149a_linux_link_boot.py`

最终执行：

```text
python3 tests/scripts/run_kl149a_linux_link_boot.py
```

结果为 PASS，且 runner：

1. 先复跑 KL-148a；
2. 从 `mrproper` 开始，重新执行 defconfig/olddefconfig 和
   `KCFLAGS=-O0 make Image`；
3. 精确冻结 0001–0005 名称、完整 commit ID 和 stable patch-id，并逐项
   核对 component commit 与 patch payload；构建前后均要求 Linux source
   clean；
4. 断言 `vmlinux` 为 ELF64、big-endian、ET_EXEC、
   Machine=`0xDA0`、entry=`0x80000000`，`llvm-nm -u` 为空；
5. 断言 `_start=0x80000000`，flat `Image` 前缀逐字节等于
   `.head.text`，Image/ELF `_end` 均不得进入 marker/stack scratch；
6. 精确核对 QEMU source clean、HEAD、version 中的 git ID 和 binary
   SHA256 后，以同一 Image 经 HBI ROM/QEMU `dadao-m1 -kernel` 启动；
7. QEMU 先以 `-S` 停住，QMP 证明 marker scratch 初值为 0，再启动
   vCPU；正例必须由 guest 写出 marker 且 QEMU status 仍为 running；
8. 自动运行一个仅把 HBI previous mode 改为 `hypv(3)` 的 frozen 错误
   ROM。该负控必须在 guest mode assertion 处 shutdown、marker 保持 0；
9. 保存正/负 QMP evidence 和 QEMU/ROM/Image/vmlinux identity。

关键结果：

- `vmlinux`：8,380,624 bytes，
  SHA256 `cf8e8825f6a226230c51a6dd75df5091daa98c19739ad4ddea04fcd966ec1303`；
- `Image`：7,655,516 bytes，
  SHA256 `781dffba6e84328bafef9629758e4009d146fb1e64393a1b12999127afb6cb6f`；
- ELF `_end=0x8074d05c`，低于 marker `0x87fd0000`；
- `.head.text`：4,108 bytes，确为 Image prefix；
- ROM：132 bytes，
  SHA256 `46c1e4af50162dd9be1adb82eb9223a6902f0629a0a4c9d3f18822aee5e536c7`；
- QEMU HEAD：
  `eee0933b064014f3ab305eaa275883f025223d53`；binary SHA256：
  `97bfa45fbb15c1f2c52dd7ddeec555da4b3d8a447c47cba3bdf862db5a76fcd8`；
- QMP raw-memory oracle：
  CPU start 前 `[0x87fd0000]=0`；正例启动后
  `[0x87fd0000]=0x4b4c313439414845` 且 status=`running`；
- wrong-mode ROM：
  SHA256 `7cf369ba7b7cac026b693f560d991da91ddc201725848ab621c355488f9aca8c`，
  PASS marker `[0x87fd0000]=0`、failure word
  `[0x87fd0008]=0x4b4c313439424144`（`KL149BAD`），且
  status=`shutdown`；
- evidence：
  `.work/evidence/kl149a-linux-link-boot/summary.json`。

### 明确非声明

当前证明止于 reset handoff、Linux `_start` 和进入 `start_kernel` 前的
guest-authored marker。它不声称 console、完整 mem_init、trap handling、
timer、MMU enable/page fault、context switch、initramfs、login 或用户态
程序可用；这些继续由 KL-150a 及后续任务推进。默认 `-O2` 仍由 KL-148b
独立跟踪。

## Review

实现者主审已检查 Linux component diff、链接输出、Image prefix、HBI ROM
字节来源、QMP oracle、patch identity 和 source clean 状态；早期主审修正了
`memblock_reserve()` 起点遗漏 `_start.._text`、early marker 缺少可关闭
Kconfig gate 两项问题。

独立 subagent 第一轮结论为 **Not Accepted**，包含 1 Blocker、2 High、
4 Medium：

1. 仅凭 marker 无法证明 hypv→supv；错误 previous-mode ROM 也会写
   marker，且旧 runner 未要求 running；
2. QEMU identity 只记录未核对；
3. Linux gate 仅冻结 patch prefix/stable patch-id，未冻结精确 HEAD；
4. disabled THP 在 `-O0` 下产生 21 个 negative-shift diagnostics；
5. Image 上界未排除 marker/stack scratch；
6. `asm/elf.h` 递归 include 导致 `ELF_CLASS` 未定义 warning；
7. 因上述门禁缺口，任务 MD 的证明声明越界。

主控接受全部 finding，并以 patch 0004 + runner follow-up 修复：

- `_start` 通过真实 cfx_smon precise-entry frame 读取 trap 前 run mode，
  非 supv 直接 `unimp`；错误 ROM 自动负控现为 marker=0/shutdown；
- QMP 在 `-S` 状态先验证 scratch=0，正例 marker 后要求
  running=true；ROM 正负身份均冻结；
- QEMU source clean、完整 HEAD、binary SHA256、version git ID 全部
  fail-closed 核对；
- Linux series 精确为 0001–0004，完整 commit ID 与 patch-id 双冻结，
  构建前后 source clean；
- `CONFIG_DADAO_K3_O0_LINK_COMPAT` 下 disabled THP 以一页作为无 UB
  的禁用单位，negative-shift diagnostics 清零；runner 明确拒绝该
  warning 和 `ELF_CLASS` warning；
- `asm/elf.h` 改由 UAPI ELF 头提供常量，打破递归 include；
- 同时核对 flat Image end、ELF `_end`、marker、early stack 和 scratch
  end 的非重叠顺序。

修复后完整 runner 正/负矩阵 PASS。

独立 subagent 第二轮确认第一轮 7 项的核心实现全部关闭，但指出 2 个
Medium 门禁精度和 1 个 Low 文档残留：

1. warning 哨兵字符串没有匹配 Clang 在 `ELF_CLASS` 两侧加引号的真实
   输出；
2. wrong-mode 仅拒绝 PASS marker，未要求其保持 0，也未把 shutdown
   精确绑定到 `.Lbad_handoff`；
3. 目标段仍只写 patch 0003。

主控再次全部接受并修复：

- warning gate 改为逐行同时匹配 `ELF_CLASS` 与 `is not defined`；
- patch 0005 在 `.Lbad_handoff` 只写独立 `KL149BAD` failure word，
  PASS marker 保持 0；负控必须同时满足 marker=0、
  failure=`KL149BAD`、shutdown，任意其它提前 shutdown 均 FAIL；
- 目标段同步声明 0003 主体和 0004/0005 review follow-up。

第三版完整 runner PASS。

独立 subagent 最终复审结论：**Accepted**，无 Blocker / High / Medium /
Low finding。复审独立核对了：

- 0005 commit/patch stable patch-id、正向重放、反向检查，以及
  0001–0005 在 series/runner 中的精确冻结；
- `ELF_CLASS` 带引号真实诊断可被新哨兵捕获，fresh log 中该 warning
  为 0；
- `.Lbad_handoff` 只写 failure word，不触碰 PASS marker；
- 独立 `/tmp` QMP 等价复跑正例得到
  `PASS marker + failure=0 + running`，wrong-mode 得到
  `marker=0 + KL149BAD + shutdown`，且 trace 的 mode 链为预期；
- Linux/QEMU component worktree clean，任务声明与 evidence 一致。

主控二次复核接受该结论。最终结论：
**KL-149a 在明确的 `KCFLAGS=-O0`、QEMU dadao-m1 reset-to-Linux-entry
范围内 PASS**。
