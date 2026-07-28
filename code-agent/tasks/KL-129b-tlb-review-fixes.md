# KL-129b：TLB range invalidate 对齐修复与边界探针（QEMU + gem5）

**执行环境**：远端 Codex（本仓库），QEMU 源码改动
（`.work/source/qemu`）+ gem5 源码改动（`~/DADAO-gem5`，独立仓库）

**依赖**：`KL-129a` 已完成；本任务是其独立 review 后续修复，不扩展
架构范围。执行时还必须保留已经落地的 `KL-131a`、`KL-133a` 改动。

## 背景与已复现问题

`KL-129a` 最终提交为 QEMU
`599efb6c19f66b2846e4be8ab8084890e5e65679`、gem5
`1092fa331b29b80b95bee93df9d0a09a12a7b1e5`。后续独立 review 发现，
两端 `invalidate-by-range` 都直接把
`cfx_tlb_addr_start[41:0]` 当作字节起点；冻结契约实际只使用
`addr_start[41:16]`，因此低 16 位必须忽略，区间起点按 64 KiB 对齐。

判别反例：先缓存同一集合的 page13/page14，写
`addr_start = page13 + 0xf000`、`addr_size = 0x2000` 后执行 range
invalidate。当前实现会把区间当作 `[page13+0xf000,page14+0x1000)`，
错误地同时清 page13/page14；正确区间应为
`[page13,page13+0x2000)`，只清 page13。原 KL-129a runner 没覆盖非零
低16位，所以两端一致地返回成功，属于双实现同错。

## 目标

### 1. 修正两端 range invalidate

- 集合仍由 `addr_start[47:42]` 选择。
- 集合内起点只取 `addr_start[41:16] << 16`，明确忽略低16位。
- `addr_size == 0` 必须是 no-op。
- 区间末端计算不能无符号溢出；超过当前 4 TiB 集合边界时钳制到集合
  末端，不能误清下一个集合。
- superpage/normal-page entry 仍按半开区间相交判断；不改变
  invalidate-all、enable bypass、fill 或 true-LRU 的既有语义。

### 2. 扩充持久探针

在 KL-129a runner 基础上增加至少以下判别场景，QEMU/gem5 必须分别
执行并给出一致结果：

1. 非零低16位的起点对齐反例：只清 page13、不清 page14。
2. `addr_size=0`：目标 entry 保持命中。
3. 集合尾部跨界/超大 size：只清当前集合匹配 entry，不影响下一集合。
4. fault-hit 也必须 touch LRU：构造16路满组，命中一个会产生权限故障的
   entry 并由 handler 返回，再填第17路；验证 fault-hit entry 没被当成
   LRU 淘汰。
5. `cfx_tlb_enable` disable→enable：明确验证 disable 仅绕过架构 TLB，
   不隐式清除既有 entry；重新 enable 后旧缓存是否恢复命中应与现有冻结
   语义及双端实现一致。若规范材料不能支持该声明，记录为 non-claim，
   不凭空发明。

探针必须通过 guest 内部逐值判定后才能 halt 到成功码，不能只检查模拟器
退出码或日志中出现过某个字符串。

## 约束

- 不重写 KL-129a；以新的 follow-up commit/patch 落地，保留审计历史。
- 不修改 PTW walk、A/D、fault cause、异步分派或 timer 语义。
- QEMU/gem5 算法和 runner 预期需要独立对照冻结契约，不能以“两端一致”
  代替正确性。
- 完整 patch-series bare-pin replay（tree-hash 比对），QEMU/gem5 分别
  执行。
- 现有 KL-127a/129a/131a/133a 探针、全量 lit E2E、differential、
  manifest/issues 检查零回归。
- 完成后填写完成区、自审、最终提交/patch-id/replay；再交由独立
  subagent review。

## 验收

- 上述四个强制边界场景（1-4）双后端全部通过；第5项要么形成有规范依据
  的通过证据，要么明确记录 non-claim。
- 原 KL-129a 13/13 仍通过。
- QEMU/gem5 构建通过；既有 K1 探针无回归。
- patch series 从 manifest pin plain `git am` 全量成功，replay tree 与
  各自开发树一致。

## 参考指针

- `code-agent/tasks/KL-129a-tlb-cache-and-delegation.md`
- `tests/scripts/run_kl129a_tlb_probes.py`
- QEMU `target/dadao/cpu.c` 的 `dadao_cfx_tlb_invalidate_range()`
- gem5 `src/arch/dadao/isa.cc` 的 `ISA::cfxTlbInvalidateRange()`

---

## 完成区

**状态**：PASS；实现、主验收与独立 reviewer 均已通过。

### 实现

- QEMU `dadao_cfx_tlb_invalidate_range()` 与 gem5
  `ISA::cfxTlbInvalidateRange()` 仍从 `addr_start[47:42]` 选择集合，但
  集合内起点改为
  `addr_start & (((1ULL << 42) - 1) & ~0xffffULL)`，即只采用
  `addr_start[41:16] << 16`，明确忽略低16位。
- 既有 `size == 0` 提前返回保持不变。
- 既有 `size > set_limit - set_start` 判定在对齐后的集合内起点上执行；
  因而不做可能溢出的 `start + size`，而是钳制到当前 4 TiB 集合末端。
  entry 仍以半开区间相交判定，且只遍历所选集合。
- 未改 PTW、A/D、fault cause、enable bypass、fill/LRU、异步分派或 timer
  语义；KL-129a 历史提交未改写。

### 新增持久 guest 判别探针

新增 `tests/scripts/run_kl129b_tlb_review_fixes.py`。脚本复用 KL-129a 的
二进制生成和双后端启动基础设施，但四个场景均由 guest 内部逐值比较，
只有所有比较成功才 halt 42：

1. `low16-alignment`：先缓存 page13/page14 并修改页表，再写
   `start=page13+0xf000,size=0x2000`。正确结果是 page13 重新 walk
   读到新值、page14 保持旧缓存值；旧实现会错误清除两页。
2. `zero-size-noop`：缓存两页并修改页表后执行 size0 range invalidate，
   两页都必须保持旧缓存值。
3. `set-end-clamp`：同时缓存 set6 最后一页与 set7 一页，从 set6 最后一
   页以 `UINT64_MAX` size 失效；set6 读到新值而 set7 保持旧缓存值。
4. `fault-hit-lru`：填满16路后，以缺失 fragment 命中 way0 并进入
   `cfx_tlb` handler；handler 返回后更新内存 PTE，再填第17路。随后
   二次访问仍必须命中 way0 的旧缓存并再次进入 handler，证明首次
   fault-hit 更新了 LRU，而不是把 way0 当作最旧项淘汰。

最终输出：

```text
low16-alignment: qemu=42 gem5=42
zero-size-noop: qemu=42 gem5=42
set-end-clamp: qemu=42 gem5=42
fault-hit-lru: qemu=42 gem5=42
PASS: 4 guest-decided KL-129b probes; ...; QEMU=gem5
```

证据写入 `.work/evidence/kl129b-tlb-review-fixes/`。

### disable→enable 口径

对照冻结合同 `contracts/isa/spec.md` §8.5.3、DADAO-12 SEE 的 TLB
查找步骤及寄存器表，材料只规定 enable 位为关闭/开启、位为1才查 TLB；
未规定关闭时清空表项，也未明确承诺重新开启后恢复旧表项。当前 QEMU
写 enable 时只额外清 host softmmu TLB、gem5 只更新 enable 位，两端均
不主动清架构 TLB entry，但这不足以成为架构依据。因此本任务将
disable→enable entry lifetime 明确保留为 **non-claim**，不新增一个
可能把实现偶然行为冻结成 ISA 的验收 probe。

### 构建与回归

- QEMU `ninja -C build qemu-system-dadao`：PASS；仅有既有
  `-Wmissing-prototypes` warning。
- gem5 `scons build/DADAO/gem5.opt -j4`：PASS；仅有既有宿主可选依赖
  png/HDF5/protoc/capstone warning。
- KL-129b 4/4 双端连续 **10/10** 轮稳定 PASS；KL-129a 原 13/13 PASS。
- KL-127a：30 fault + 10 A/D 全部 QEMU=gem5=42。
- KL-131a：scenario-A=131/131、scenario-B=132/132；KL-133a：
  cycle/retire-fault/one-shot/zero/periodic/mask/relatch 全部 PASS。
- KL-113a/117a/120a/122a/124a/125a/126a 全部保持既有结果。
- `.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/`：**81/81 PASS**。
- `python3 tools/run_differential.py`：
  `AGREE(3-way)=200, gem5-SKIP=2, DIVERGE=0`；
  `AGREE(4-way)=200, Sail-SKIP=2, SAIL-DIVERGE=0`。
- manifest PASS；issues `Open=24 Closed=43 Total=67` PASS；
  ISA/ABI wiki refs PASS（ISA 3 条既有 UNPARSEABLE warning）；
  wiki drift 3/3 PASS。
- 根仓、QEMU、gem5 `diff --check` PASS。

### 组件提交、patch-id 与 bare-pin replay

- QEMU：
  - commit
    `46c11a492a4c34122209cf1a0e2d079d77f36aa6`；
  - patch
    `components/qemu/patches/0035-target-dadao-align-TLB-range-invalidation-start-KL-1.patch`；
  - stable patch-id
    `a33016ce272dd6335673fb221ec8886ea9af1599`；
  - manifest pin `385b0a7d9785c8f3ac7b116d7f31d61502b55183`
    plain `git am` **35/35**，replay/dev tree 均为
    `91586a0c3672a973f47ed2183bf3c77d443e6c31`。
- gem5：
  - commit
    `04e1d85f7766de1068eb606e553bc14effa33b70`；
  - patch
    `components/gem5/patches/0028-arch-dadao-align-TLB-range-invalidation-start-KL-129.patch`；
  - stable patch-id
    `d63dbed93288c7023b1fcb6f2b3c17ed6f93f3cd`；
  - manifest pin `c8222cc67a399bfc01e8658dd14b30d5bfd634f9`
    plain `git am` **28/28**，replay/dev tree 均为
    `f86160498917260bd911a68370859e49360d29e3`。

### Worker 自审

- 两端算法逐项对齐：集合选择、64 KiB 起点掩码、size0、无溢出钳制、
  super/normal 半开区间相交均一致，且规范正确性由 guest 反例判断，
  不是以双端一致代替。
- `fault-hit-lru` 使用更新后的内存 PTE作为反事实：若 fault-hit 未 touch，
  way0 被第17路淘汰，二次访问会 walk 成功且 handler marker 缺失，guest
  必然返回失败码；当前双端 42 证明测试有判别力。
- patch 只含各组件一处范围起点修复；根仓只纳入 KL-129b task/runner、
  两个新 patch、series、README 与 roadmap。未触碰 KL-137a/KL-139a
  task MD 或 `gcc-torture-results.json`。
- 按用户本次派发要求，worker 不启动 reviewer；根仓保持未提交，交回
  主 agent 后再决定独立 review。

### 独立 subagent review

**结论：PASS，无阻塞、高或中严重度问题。**

- 独立逐项确认两端 set 选择、`addr_start[41:16] << 16`、size0、
  overflow-safe set-end clamp 与半开区间相交算法正确且对称。
- 四个 guest probe 均被确认具有实际反向判别力，尤其旧实现会打红的
  low16 反例，以及依靠二次 handler marker 区分 fault-hit 是否 touch
  LRU 的第17路淘汰场景。
- disable→enable entry lifetime 保持 non-claim，没有把两端当前偶然
  行为误写成架构保证。
- 组件提交只修改 QEMU `cpu.c` 与 gem5 `isa.cc` 的一处 range 起点，
  未触碰 PTW/A-D、异步分派或 timer。
- reviewer 独立验证 KL-129b 连续 10/10、KL-129a 13/13、KL-127a
  30 fault + 10 A/D、KL-131a/KL-133a、E2E 81/81、三/四方差分 200
  零分歧；QEMU 35/35、gem5 28/28 replay 与 patch-id/tree hash 均匹配，
  manifest/issues/wiki/diff checks 全部 PASS。
- 仓库总 `make check` 仍报告既存 vector coverage 缺口
  （ldmo-ra/stmo-ra/cfx2rd/cfx2rc/escape）；该问题早于且独立于
  KL-129b，不由本任务扩张处理。
