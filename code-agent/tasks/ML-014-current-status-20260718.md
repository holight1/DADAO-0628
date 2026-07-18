# ML-014 mallocng 当前状态（2026-07-18 收口）

## 结论

基本启动与 brk backing 链路已推进到可审计状态，但真实 mallocng 的 pointer/
read-write 链路仍未完成；本轮停止继续下实现任务。

## 已完成并有独立 review 的部分

- ML-014m：DADAO `RELA_PAGE` 修复，TLS startup blocker 关闭；root linker patch
  已集成，常规 E2E/differential 基线保持通过。
- ML-014o/p：gem5 `SYS_brk` 改走 `MemState::updateBrkRegion`/VMA/fault-in，
  初始 brk 从 `0x90000000` 对齐到 ELF/QEMU 的 `0x87e00000`；direct brk
  断言在 ML-014q/r 收口，查询、页内/跨页增长和第二页 backing 有 PASS/42 及
  负向 FAIL-5/5 证据。
- ML-014t：不调用 malloc 的显式 `p=base+16`、`q=p+131051` probe 在当前
  clang/lld ELF 中生成完整大偏移，QEMU/gem5 均 exit 42；独立 reviewer
  Accepted（`3a21274`）。这排除了“一般大偏移 codegen/EA 全局损坏”，但不
  证明 mallocng 返回值路径使用同样的 lowering。

## 当前 mallocng 结果

| probe | QEMU | gem5 | 当前解释 |
|---|---:|---:|---|
| `mallocng_real` | 42 | 42 | 仅表示该 probe 返回成功，不是 allocator 完成证明 |
| `malloc_pointer_after` | 13 | 13 | probe 显式比较返回指针与 `0x100000000` 不相等；gem5 的 `0x100000010` 由 rw probe 直接观测，pointer probe 自身 raw 指针尚未独立 dump |
| `malloc_rw_after` | 14 | 134 | QEMU 走到末端读回失败；gem5 在后续末端 store 的 fault VA 为 `0xfffffffb` |

已确认的 gem5 细节：首字节 payload store 的实际 EA 为 `0x100000010`，没有再
出现旧的 `0x90001000` brk fault；末端 ELF 指令呈现 `stb ... -21`，
`0x80000160`/`p-21` 是结合反汇编和 fault VA 的高置信度重建，不是 ExecAll 尾部
直接寄存器快照。因而当前不能单独归因到 LLVM、QEMU 或 gem5。

## 未完成与边界

- ML-014s 独立 review 为 Needs-fix（证据层级），建议下一步把 mallocng 返回值
  保存、pointer-GEP/末端访问与 ML-014t 的显式 p/q 形态逐条对齐，再决定实现组件。
- `ML-014a` 保持用户原始未完成文件，未修改；ML-014f 仍 Blocked/Not Accepted。
- 尚未把 gem5 brk 修复提交进 root `components/gem5` patch series；完整 clean
  replay、QEMU 重跑、全量 E2E/differential 和 `make check` 尚未针对这轮外部
  gem5 source commit 重跑。此前基线结果继续有效但不冒充本轮验证。
- `-O X`、puts、free、varargs、pointer ABI 总体修复暂不展开。

## 建议 roadmap

1. 下一轮只做 mallocng-specific address/return probe：直接保存并观测 malloc
   返回值，逐条比较其 IR/ELF 与 ML-014t 的 `p+131051`；不先改 LLVM/backend。
2. 若确认 mallocng 专属 lowering 形成 `p-21`，再开 LLVM 专项修复与独立 review；
   若 ELF 正确而 simulator 仍在 `0xfffffffb` 分歧，再开 backend 专项任务。
3. 实现接受后，再做 gem5 root patch export/integration、完整回归，之后才回到
   puts/varargs/`-O X` 和 ML-014a 收尾。
