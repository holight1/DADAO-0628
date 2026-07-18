# ML-014m：修复 DADAO RELA_PAGE 页差并恢复 mallocng 启动链路

**执行环境**：本地 subagent worker；承接 ML-014l

**状态**：Fixed（2026-07-18；linker startup 修复完成，mallocng allocator 后续问题仍 Blocked）

## 目标

修复 `.work/source/llvm/lld/ELF/Arch/DADAO.cpp` 中
`R_DADAO_RELA_PAGE` 的页差计算，使 `rela + RELA_LO` 组合符合
`contracts/isa/spec.md §4.8`：

```text
page_imm = ((S+A)>>12) - ((P+4)>>12)
low_imm  = (S+A) & 0xfff
```

目标是让真实 mallocng-linked musl ELF 能完成 TLS startup，进入 `main`，并
为后续 ML-014f 的 malloc 基本链路提供正确前提。本任务不处理 `-O X`、puts、
free、allocator 算法或 ML-014a 整体验收。

## Ownership

- worker 负责：`.work/source/llvm/lld/ELF/Arch/DADAO.cpp` 的最小修复、对应
  构建、临时验证报告，以及必要的最小 linker regression；若需新增仓库测试，
  只改本任务范围内的测试文件。
- 不允许修改 QEMU、gem5、musl 源码、`components/llvm/patches/series`、
  `docs/issues.yaml`、contracts、manifests、ML-014a；不要处理 `-O`/puts。
- 不得把 `~/toolchain` 或 `~/knowledge-graph` 传给 subagent；架构师可自行参考。
- `.work/source/llvm` 可以产生候选 source commit，但在 reviewer 通过前不导出
  root patch series，也不宣称最终交付。

## 执行阶梯

1. 读取 ML-014l 和本任务，确认当前 `R_PC` 的 `val=S+A-P` 以及可用的最终
   symbol/place 信息；选择不会破坏 RELA_LO 的实现方式。
2. 实现最小修复，保留 18-bit overflow 检查和 RB 高位语义；不要用
   `(val+0x800)>>12` 近似页号差。
3. 构建 lld，并用一个跨页/页内偏移敏感的最小链接场景验证：
   - `P+4` 与 `S+A` 在不同页时页 immediate 正确；
   - `P=page_end-4` 时 `P+4` 跨页不多/少算一页；
   - low12 仍为目标绝对低 12 位。
4. 重新链接已有 lite-only 与 mallocng-linked musl probe，至少验证：
   - `main_tls+0x18` 的访问回到真实地址；
   - QEMU/gem5 不再在 `__init_tls` startup 处 `MALIGN=129`；
   - `return42`、真实 mmap 回归保持 42；mallocng probe 至少能进入 main，
     后续 allocator 失败不得伪报为本任务完成。
5. 更新本任务完成区，列出 source commit、验证命令/结果和剩余阻塞；worker
   自审后停止，不修改越权范围。

## 验收

- source fix 有明确公式和实现理由；
- lld 构建通过；跨页最小回归通过；
- 两个 simulator 在 startup 不再因错误 TLS image 地址触发 MALIGN；
- 不把 mallocng malloc+写读+free 或 ML-014a 写成完成；
- 有 subagent 自审，随后由独立 reviewer 做代码和结果复核。

## 完成区

**Finding：Fixed（限定为 linker RELA_PAGE/startup 修复）。**

### 修改

- 仅修改 `.work/source/llvm/lld/ELF/Arch/DADAO.cpp` 的
  `R_DADAO_RELA_PAGE` 分支：由 `rel.sym->getVA(ctx, rel.addend)` 重建
  `S+A`，用 `P=(S+A)-val` 恢复 place，计算
  `page(S+A)-page(P+4)`；保留 18-bit `checkInt`。
- `R_DADAO_RELA_LO` 未修改，仍使用目标绝对地址 low12。
- source commit：`92dd91c67c08 lld: fix DADAO RELA_PAGE page delta`。
- 未导出 root patch series；未修改 QEMU/gem5/musl、docs/issues.yaml、
  contracts、manifests 或 ML-014a。

### 验证命令与结果

- `cmake --build .work/build/llvm --target lld -j2`：通过。
- 最小链接场景：
  - `P=0x80000a1c`、`S+A=0x80006030` → `rela rb8, 6`，low12 `0x30`；
  - `P=0x80000ffc`、`P+4=0x80001000`、`S+A=0x80002030` →
    `rela rb8, 1`，low12 `0x30`；均通过。
- 真实 musl probe（QEMU / gem5）：`return42=42/42`，`mmap_real=42/42`。
  两者均未触发原启动期 `MALIGN=129`。
- `mallocng_real`：QEMU=42；gem5=134，已越过 startup MALIGN，但在
  malloc 路径访问 `0x90001000` 时 page-table fault。
- `malloc_pointer_after`：QEMU=13、gem5=134；`malloc_rw_after`：QEMU=14、
  gem5=134。后续 allocator/backend 仍未通过，未伪报为 mallocng 完成。
- 详细命令和日志：`.work/ML-014m-dadao-rela-page-fix/report.md`。

### Subagent 自审

- 已复核 `val=S+A-P`、`P+4` 页语义、low12 保持和 overflow 检查；没有扩展
  API 或修改越权组件。
- 已执行 lld 构建、普通跨页与 `P=page_end-4` 最小链接、lite-only 与
  mallocng 真实 probe；退出码均按原样记录。
- 自审判定：**Fixed（linker startup 范围）；mallocng allocator 后续为 Blocked**。

独立 reviewer 待补充。

## 审阅记录

（待填写。）
