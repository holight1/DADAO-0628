# KL-152a：K3 `mm_init` 完成与 allocator 初始化边界

**状态**：完成（PASS 3/3，FAIL=0，SKIP=0）
**日期**：2026-07-29
**前置**：KL-151a
**后续**：KL-153a（由本任务 evidence 冻结的首个 post-`mm_init` 阻塞）

## 背景

KL-151a 已用六个 guest-authored QMP words 证明 Linux
`mem_init()` 完成，并冻结首个下一阻塞：

- `EXCP_MALIGN`，PC `0x8027985c`；
- `mm/page_alloc.c::prepare_alloc_pages+0x1c8`；
- `rb1+71` 单字节 slot 由 `stb` 写入、由八字节 `ldo` 读取；
- positive 与 `-serial none` 两个场景身份一致。

KL-151a 最终根提交为 `81b21dd`，frozen summary SHA256 为
`e6682d902e067e69ce0384d468ec3067e831999d2c573633be1ca6d2a093cd08`。

Linux 5.4 的 `init/main.c::mm_init()` 在 `mem_init()` 之后继续初始化
SLUB、kmemleak、pgtable、debug objects、vmalloc、ioremap 和架构空实现。
本任务只证明这个真实函数边界完成，不把它扩大为 scheduler、interrupt、
initcall、login 或用户态能力。

## 目标

1. 在既有 `CONFIG_DADAO_K3_O0_LINK_COMPAT` 边界内关闭
   `prepare_alloc_pages` 的实证 bool stack-slot MALIGN；
2. 若到 `mm_init()` 返回前继续遇到同类缺陷，只能按“一个实证位置、一个窄
   修复”推进，并为每个新增 patch 保存修复前 Linux HEAD、Image、QMP raw、
   trace、symbol、disassembly、PC/slot 与 size/SHA256；
3. 在 `init/main.c::mm_init()` 的最后一个真实初始化动作
   `pti_init()` 返回后写入：
   - 地址 `0x87fd0030`；
   - 值 `0x4b4c3135324d4d44`（ASCII `KL152MMD`）；
4. 用 QMP 证明旧六个 words 无回归，新 word 只在完整 `mm_init()` 返回边界
   出现；
5. 达到 marker 后继续观察并冻结首个真实 post-`mm_init` 阻塞，作为
   KL-153a 输入。

## 实施约束

- Linux component 使用普通 commit；每个实证修复独立导出 patch 并追加
  `components/linux/patches/series`。预计不修改 QEMU。
- generic Linux carrier 修改必须受 `CONFIG_DADAO_K3_O0_LINK_COMPAT`
  控制；普通配置保留原 `bool`、结构布局、UAPI、模块 ABI 和语义。
- carrier 返回必须规范化为 `0/1`；跨翻译单元声明/定义必须同步。
- 禁止预防性批量改写 generic bool；禁止用 head.S、ROM、QEMU 或 runner
  预填 progress。
- 继续固定 `KCFLAGS=-O0`；不处理 KL-148b 的默认优化问题。
- runner/evidence 必须采用 KL-151a 已收紧的干净单次运行、RUNNING/FAILED、
  原子 summary 和无循环 artifact manifest 语义。
- 临时 historical worktree 清理必须检查命令返回码、路径消失和 Git 注册表。
- 不显式参考 `~/toolchain` 或 `~/knowledge-graph`。
- 不修改、不提交顶层既有未跟踪 `gcc-torture-results.json`。

## 验收

新增 `tests/scripts/run_kl152a_mm_init_completion.py`，必须：

1. 精确验证根提交 `81b21dd`、KL-151a summary SHA256、`PASS 3/3`、旧六词
   oracle、negative、Linux/QEMU identity、runner 与 85-item manifest；
2. 检查 Linux/QEMU component clean，精确绑定 Linux 全 patch queue；
   QEMU 固定 KL-150a HEAD/binary/0037/0038 身份，并如实保留 0001..0036
   历史 replay 债务；
3. fresh `mrproper` 构建 `Image`，验证 ELF64 big-endian、`EM_DADAO`、
   entry、undefined symbol、forbidden diagnostics，以及扩展为 56 bytes
   后的 Image/scratch/stack non-overlap；
4. QEMU `-S` 启动，`cont` 前读取 56-byte oracle 全零；正例逐级拒绝非法或
   跳级状态，最终并延迟复读精确得到：
   `(KL149AHE, 0, KL150SAE, KL150SAD, KL150MIN, KL151MID, KL152MMD)`；
5. source contract 隔离 `mm_init()`，验证
   `mem_init -> kmem_cache_init -> kmemleak_init -> pgtable_init ->
   debug_objects_mem_init -> vmalloc_init -> ioremap_huge_init ->
   init_espfix_bsp -> pti_init -> KL152MMD`，并要求 marker 是函数最后一条
   真实语句；
6. 扫描 `head.S` 与两份 HBI ROM，拒绝新 progress value 被预填；
7. console 仅作为 secondary；正例保留既有四 anchors，并增加真实 SLUB
   初始化锚点。`-serial none` 使用同一 Image，QMP 完整而 console
   verdict=false；
8. wrong-mode 必须保持
   `(0, KL149BAD, 0, 0, 0, 0, 0)` 并 shutdown；
9. 每个中间 carrier 修复都必须由 runner 在对应 pre-fix detached worktree
   重建并复现，写入 `carrier_fix_evidence`；最终 blocker 需在 positive 与
   `-serial none` 两场景一致；
10. summary 绑定 runner 和最终 Image/vmlinux/QEMU，artifact manifest
    覆盖本轮 evidence 目录全部非循环产物并逐项校验；失败不得保留旧 PASS；
11. 最终明确 `PASS 3/3, FAIL=0, SKIP=0`，两个 component clean，临时
    worktree/output 全部清除。

## 非声明

本任务只声明 `mm_init()` 的真实完成及首个 post-`mm_init` 边界。它不声明
`sched_init()` 完成、上下文切换、Linux trap/syscall、timer/IRQ、用户页表、
initramfs `/init`、TTY/login 或用户态 hello。

## 实施记录

### 组件提交与 patch queue

Linux 从 KL-151a frozen HEAD
`8f0b11da8346dc46402974e7a6a8626cff103ed3` 开始，以普通 detached-worktree
commit 逐项推进到
`e054a68cc86b045881afdc26a028ee4d16c3d217`。新增 queue 如下：

| patch | Linux commit | stable patch-id |
| --- | --- | --- |
| `0011-dadao-complete-K3-mm_init-progress.patch` | `4f32b2dd26662ed48cbca155792edd88dd3e9e52` | `93fd5b7cde954b7f8f1635a1d4182f10f0f910e0` |
| `0012-dadao-widen-zone-watermark-result-for-K3-O0.patch` | `ba60ea713bbca2224acbd5332bb265ff26afb64d` | `b6ca6ffa3c4be423704abd4e94dc31a851a7cf77` |
| `0013-dadao-widen-fallback-steal-result-for-K3-O0.patch` | `1aae897eb20cad2cc856bb082cf713d186a8e1d8` | `7a2593c7ae9521ebe9badd2245cb1a7d0c40491b` |
| `0014-dadao-widen-rmqueue-fallback-result-for-K3-O0.patch` | `0f822ec071294067d3827c82bd7b331a974fb251` | `3c2fc71c815f10fd0d28586fc9bda7e71dd94ce5` |
| `0015-dadao-widen-new-PCP-check-result-for-K3-O0.patch` | `ee9ed8174efb893c7c48d85cd27ef9264cac6c66` | `dc2e7aff85a34cba68bb17f33056cb3d0e0ff12e` |
| `0016-dadao-widen-SLUB-pfmemalloc-result-for-K3-O0.patch` | `2aad5665523d56f829b516ac919203953cf87a69` | `a36d5f2cc8513586d1d487852f88be8357c02712` |
| `0017-dadao-widen-SLUB-cmpxchg-result-for-K3-O0.patch` | `8d49b7e041970743bb39e9dab94091a9036faeae` | `c7d2521a92bea303bb963fb332dfd548f269d623` |
| `0018-dadao-widen-SLUB-init-on-free-result-for-K3-O0.patch` | `8f84618d05c9e413946ed5b8fb6e265cb56f449d` | `5b48eb0027964ba7157114f2c28aef4957f6f468` |
| `0019-dadao-widen-SLUB-init-on-alloc-result-for-K3-O0.patch` | `bd10b11e2780d392e57f1b18f0e9dc8c2db28ed4` | `6fdc09201d10ee41897de53117b4128651560cde` |
| `0020-dadao-separate-M1-progress-from-O0-compatibility.patch` | `e054a68cc86b045881afdc26a028ee4d16c3d217` | `876cc96f3a6221d74739eab84fb9d0d47835f9e2` |

0011 在 `prepare_alloc_pages` 上关闭 KL-151a 冻结缺陷，并在 `pti_init()`
返回后的 `mm_init()` 最后一条真实语句写入 `KL152MMD`。0012–0019 分别只
处理运行继续暴露的 `zone_watermark_fast`、`can_steal_fallback`、
`__rmqueue_fallback`、`check_new_pcp`、`pfmemalloc_match`、
`__cmpxchg_double_slab`、`slab_want_init_on_free` 和
`slab_want_init_on_alloc` carrier。所有 generic carrier 都受
`CONFIG_DADAO_K3_O0_LINK_COMPAT` 约束，普通配置仍使用原 `bool`；跨翻译
单元声明/定义已同步，直接 bitmask 返回已规范化为 `0/1`。

0020 不新增 carrier workaround。它新增专用
`CONFIG_DADAO_M1_PROGRESS`（`depends on DADAO_M1`，由
`dadao_defconfig` 显式启用），并将 `setup_arch`、`mem_init`、`mm_init`
五个 M1 progress writes 与相应 include 统一置于该观测配置下。
`init/main.c` 不再用 `CONFIG_DADAO_K3_O0_LINK_COMPAT` 控制 progress。
0020 payload 为 4,413 bytes，SHA256
`7f4aff01fef94e5fb6ffc9216603ef25d97ebfafa9b8e477d0a0e7b00c555d39`。

QEMU 未修改，HEAD 固定为
`dfc7842229c139cc606141b82845ecf20086e657`；重建 binary SHA256 为
`2326a4b69f3f8dc3e0c1b5c2f335d0df4c71182a481dd7f6071e4a38f6ac8240`。
根仓没有创建 commit。

### Historical carrier evidence

runner 为九个修复分别从对应 pre-fix Linux HEAD 创建 detached worktree，
执行 `mrproper`、defconfig/olddefconfig、`KCFLAGS=-O0` Image 重建和 QMP
运行，并保存 Image、raw、trace、symbol、disassembly、PC/slot、命令日志
及 size/SHA256。复现位置依次为：

1. `prepare_alloc_pages+0x1c8`，PC `0x8027985c`，`rb1+71`；
2. `zone_watermark_fast+0xe8`，PC `0x80284840`，`rb1+71`；
3. `can_steal_fallback+0xac`，PC `0x80276380`，`rb1+15`；
4. `rmqueue_bulk+0x4b8` 内联 `__rmqueue_fallback` return，PC
   `0x80285e1c`，`rb1+247`；
5. `check_new_pcp+0x68`，PC `0x80285f60`，`rb1+15`；
6. `pfmemalloc_match+0x60`，PC `0x802b7294`，`rb1+23`；
7. `__cmpxchg_double_slab+0x108`，PC `0x802b7bb0`，`rb1+71`；
8. `slab_want_init_on_free+0xcc`，PC `0x802b3e18`，`rb1+31`；
9. `slab_want_init_on_alloc+0xec`，PC `0x802af63c`，`rb1+23`。

每个位置均实证为 byte store 后由 `ldo` 读取的 O0 stack-slot MALIGN。
worktree remove 命令、路径消失和 Git worktree 注册表都逐项检查；最终没有
临时 worktree 或 output 残留。

### 最终 runner 与 evidence

最终命令：

```sh
cd /home/holight/DADAO-0628
python3 tests/scripts/run_kl152a_mm_init_completion.py
```

结果为 `PASS: KL-152a mm_init completion (3/3, FAIL=0, SKIP=0)`。runner
SHA256 为
`4c3275a6e01f81a590ccf8b6c0fdc877fb52f9f7300b7e3d4a0a6238ad980aac`；
summary 位于
`.work/evidence/kl152a-mm-init-completion/summary.json`，SHA256 为
`d36592267f91c35f6770012d95ab1c697aa190bcc908c1c501b360c080f219e5`；
223-item manifest SHA256 为
`2d40540503b89723eb5e8597da4af1368197889a98c1ad605cae597ed78fca2b`。
runner 从根提交 `81b21dd6a58ba668309d09b619f79e93c67121bd` 和 KL-151a
frozen summary/85-item manifest 起步，并绑定当前 task commit
`cb0e9ccf5357f9386a3310d84b5eb2c736c4e600`、完整二十项 Linux queue、
QEMU identity、runner、最终 Image/vmlinux 和本轮全部非循环 artifacts。
summary 还绑定 Linux/QEMU `series` 及每个 patch payload 的 size/SHA256；
Linux series 为 1,121 bytes，SHA256
`7e7d6678eecc9624ef006d991943171049f47244df386190a78cc26a2cfd2ab8`。

fresh build 的 Image 为 7,655,516 bytes，SHA256
`4f01cd4865a3a1a04e4d6ce594e0e00dd0d427db962f997f57d5c25338bbe40f`；
vmlinux 为 8,381,144 bytes，SHA256
`7eb600d092ebf2569bba5d46633b67620d32680d819a661920fa345118f992fd`。
`cont` 前 56 bytes 全零；正例和同一 Image 的 `-serial none` 最终都得到
`(KL149AHE, 0, KL150SAE, KL150SAD, KL150MIN, KL151MID, KL152MMD)`。
正例五个 console anchors 各出现一次且有序；`-serial none` console
verdict=false。wrong-mode 精确保持
`(0, KL149BAD, 0, 0, 0, 0, 0)` 并 shutdown。

source contract、`head.S` 与两份 HBI ROM no-prefill 扫描均通过。runner
代码契约要求 evidence 目录外 `fcntl.flock(LOCK_EX|LOCK_NB)` 覆盖整轮运行
与发布；外部 current-state 先原子写入 `RUNNING` 使旧 PASS 失效。manifest
和 summary 在 canonical evidence 的 `RUNNING.json` 仍存在时原子发布并
逐项复验，随后才删除 `RUNNING.json` 并原子提交 matching-run-id 的外部
`PASS`。失败路径删除 summary/manifest 并发布 `FAILED`；强制终止则
current-state 保持 `RUNNING`，不能接受旧 PASS。最终 current-state
SHA256 为
`bf494ea1bb951acbeb2e1e3d90adb66b43e390e3614f0a841d49593c59fd2fe6`，
成功目录不存在 `RUNNING.json` 或 `FAILED.json`。

首个 post-`mm_init` 阻塞在 positive 与 `-serial none` 中身份一致：
`EXCP_MALIGN`，PC `0x8063d868`，
`lib/radix-tree.c::node_tag_get+0xc4`，`rb1+31` byte store 后由 `ldo`
读取。该阻塞冻结为 KL-153a 输入，未在本任务中扩修。

最终 Linux/QEMU component worktree 均 clean；顶层既有未跟踪
`gcc-torture-results.json` 未纳入修改或提交。本任务仍只声明真实
`mm_init()` 完成，不扩展任何“非声明”能力。

## Review

独立只读 reviewer 给出 `Accepted`，同时要求关闭 2 Medium 和 3 Low：

1. Medium：M1 progress 被错误耦合到 O0 carrier compatibility；
2. Medium：runner 缺少 evidence 目录外排他锁，发布窗口不足以排除并发与
   强制终止后的旧 PASS；
3. Low：summary 只有 stable patch-id，没有 series/patch 字节级身份；
4. Low：实施记录声称“真实失败验证”，但最终 evidence 未绑定该历史事件；
5. Low：roadmap 未明确 KL-153 应停止继续增加 Linux carrier workaround。

修复分别落在 Linux 0020、runner 外部 lock/current-state 发布协议、
series/patch size+SHA256 summary 字段、改为可直接审计的代码契约表述，以及
KL-153 LLVM 根因路线。完整 runner 重跑结果为
`PASS 3/3, FAIL=0, SKIP=0`，二十项 Linux queue、223-item manifest、
current-state 与全部 artifacts 逐项一致，两个 component clean。

**最终结论：Accepted；2 Medium + 3 Low 全部关闭。**
