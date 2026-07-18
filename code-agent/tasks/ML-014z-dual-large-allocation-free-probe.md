# ML-014z：双大块并存分配与反序 free probe

**执行环境**：本地 subagent worker；承接 Accepted ML-014y

**状态**：Needs-isolation/Not Accepted（2026-07-19，按既有产物收口）

## 目标

验证两个不同尺寸、均走 mallocng mmap 阈值路径的大块能够同时存在、地址区间不
重叠、各自首中尾 sentinel 不串扰，并按反序调用真实 free。成功返回 42，不引入
输出依赖。

## Ownership

- worker 只写 `.work/ML-014z-*` probe/runner/产物与本 task MD。
- 使用尺寸 `131052` 与 `262144`；沿用当前锁定 toolchain/libc 和双后端。
- 不修改实现、root tests、patch series、issues、contracts、manifests 或 ML-014a；
  不做 use-after-free，不使用 printf/puts/varargs。
- 外部架构资料不在 worker scope；多人共享仓库，不回滚他人改动。

## 执行阶梯

1. 分配 a/b，检查非空、对齐、区间不重叠；每项失败码独立。
2. 对两块按 page stride 写 marker，再写首/中/尾 sentinel；完整读回并确认互不覆盖。
3. `free(b); free(a);`，以独立全局 marker 确认控制流返回，无 UAF。
4. 核对 map/archive/反汇编和 gem5 可得 syscall trace，证明两次 mmap 与两次
   munmap；同一产物跑 QEMU/gem5。
5. 更新记录、自审并等待独立 review。

## 验收

- 双后端 exit 42，无 timeout/fault；两块读写与反序 free 都在条件成功路径内。
- 证据能区分两次 mmap/munmap，不把地址偶然值或单后端结果冒充 allocator 总体。
- 不宣称复用、small-size/brk、输出或 ML-014f/ML-014a 完成。

## 完成区

### Finding：双后端未满足 exit 42，当前产物不能验收

本次收口没有运行新实验，也没有重编译或改写 `.work`；以下结论只来自既有
`.work/ML-014z-dual-large-allocation-free-probe/` 产物。根仓库中除本 task MD
外没有由本次收口修改其他文件。

#### 1. 真实结果与判决

`result.txt`、各退出码 sidecar 和原始输出给出的结果为：

| 项目 | 既有结果 | 可作出的判定 |
|---|---:|---|
| compile / link / objcopy | `0 / 0 / 0` | probe 成功生成 ELF 与 flat BIN |
| QEMU | `130`，`no-timeout` | 不是规定的成功码 42，且不属于 probe 的 10--26 失败分流 |
| gem5 | `0`，`no-timeout` | stdout 为 `SIM_END: halt code=0`，不是 `trap-exit code=42` |
| locked/runtime tool hash compare | `0 / 0` | 本次既有运行前后锁定输入和运行工具未变 |
| validation | `1` | 验收失败 |

因此验收要求的双后端 exit 42 未成立，判决为
**Needs-isolation/Not Accepted**。QEMU stdout 只有 monitor banner，stderr 和
`qemu.fault-focus.txt` 为空；这只能排除既有文本证据中的 timeout 和已匹配 fault，
不能把 130 解释为任一 guest 阶段成功。gem5 的 host exit 0 也只表示模拟器以
halt 结束，不能替代 probe 的 guest exit 42。

#### 2. 已证明边界：只到构建与静态可达性

- Probe C 的合同完整存在：两次请求分别为 `131052`、`262144`，包含非空、16-byte
  对齐、区间溢出/重叠、page-stride 与首中尾 sentinel 检查，并在无 UAF 的源码
  路径上执行 `free(b); free(a);`，成功码为 42。object undefined 恰为 `malloc`
  和 `free`。
- 既有 `main.disassembly.txt` 静态显示两次 malloc call（`0x8000011c`、
  `0x80000180`，目标 `malloc@0x80004c08`）以及反序两次 free call
  （`0x8000051c` 对 b、`0x80000570` 对 a，目标 `free@0x80001930`）。map、nm 与
  `--why-extract` 证明最终 ELF 拉入真实 mallocng `__libc_free` 和 `munmap.o`；
  `munmap@0x80003090` 的反汇编含 syscall trap，不是 free stub/no-op。
- `locked-hash-cmp.rc=0`、`runtime-tools-hash-cmp.rc=0` 只证明既有 runner 记录的
  before/after identity 一致。上述反汇编和 archive 证据证明代码已链接且静态
  可达，不证明运行时实际执行了这些调用。

#### 3. 未定位边界：尚未进入 allocator 动态结论

- gem5 的既有 Exec trace 没有命中 `main@0x80000110`、`malloc`、`free` 或
  `munmap`。trace 在 `__libc_start_main+100` 的 `0x80000c70` call 后转到
  `0x7ffffc80 @__fini_array_end+3200` 并执行 halt；因此在该产物上，已观测边界
  止于 startup 到 main 的交接异常，不能声称第一或第二次 malloc 已执行。
- QEMU 只有 rc 130，且该值不属于源码定义的阶段码；没有 PC trace、guest marker
  或 syscall trace 可将它归因于 startup、任一次 malloc、page/sentinel 访问、
  `free(b)` 或 `free(a)`。QEMU 的首个偏离阶段仍未定位。
- `gem5.free-munmap-runtime-focus.txt` 只有从 nm 取得的三个静态地址，没有 runtime
  trace 命中；现有证据没有证明一次、更没有证明两次 mmap/munmap，也没有证明两块
  同时存活、互不重叠、完整读写或反序 free 返回。
- `validation.rc=1` 的首要原因是双后端均非 42；同时 runner 的静态校验仍硬编码了
  ML-014y 的旧 PC（例如 `0x80000200`、`0x80001404`、`0x80002b88`），与本 ELF
  实际地址不符，输出依赖正则还把本地 helper `write_pages` 误匹配为 `write`。
  因而 validation=1 是正确的总体验收失败信号，但不能单独用于判定具体运行阶段
  或输出依赖。

最窄结论是：该 ELF 的双大块检查与真实 free/munmap 链在源码和静态产物中存在，
但既有运行结果为 QEMU=130、gem5=0，动态执行边界尚未越过可证明的 main 入口；
本任务不接受，也不外推 allocator 总体、复用、small-size/brk、ML-014f 或
ML-014a 完成。

#### 4. 下一条最小阶段定位任务

建议新开 **ML-014aa：dual-large startup/main-entry staged isolation**，只定位首个
动态偏离阶段，不修改 allocator、QEMU 或 gem5 实现：

1. 从本 probe 派生单一源码，在保留完整后续 body 和同一锁定链接输入的前提下，
   用独立 volatile selector 在 `main` 入口先返回专用正向阶段码；双后端未共同命中
   main-entry 码时立即停止，不运行 allocator 阶段变体。
2. 若 main-entry 双端成立，再按“一次只放行一个边界”依次设置停止点：第一次
   malloc 返回、第二次 malloc 返回、双块写读检查完成、`free(b)` 返回、`free(a)`
   返回。每个停止点使用互不重叠的正向退出码，并保留 gem5 PC/syscall trace；
   首个不一致点即为下一轮实现定位边界。
3. 同步把 validator 改为按 symbol 加相对位置或实际 nm 地址核对，并将输出依赖
   匹配限定为 undefined/最终外部符号，避免旧绝对 PC 和 `write_pages` 假阳性；
   该修正只服务证据判读，不把本任务翻转为 Accepted。

该任务的第一道门仅是 startup 到 `main` 入口，符合当前证据所支持的最小前移；
在这道门闭合前，不继续声称或定位双大块 allocator 语义。

### Independent review（2026-07-19）

**判决：同意 Needs-isolation/Not Accepted；该判决准确。** 本 review 仅复核本
task MD 与既有 `.work/ML-014z-dual-large-allocation-free-probe/`，未修改实现、未
重跑 probe，也未新增实验。

- `QEMU=130`、`gem5=0` 均不是合同成功码 42，`validation=1` 因而足以否决验收。
  其中 validation 还受旧绝对 PC 和 `write_pages` 假阳性影响，所以只能作为总失败
  信号，不能反推具体 guest 阶段。
- QEMU 现有证据只有 host rc 130、`no-timeout` 和 monitor banner；没有 guest PC、
  marker 或 syscall trace。130 不在源码的 10--26/42 分阶段码中，故 QEMU 连
  `main` 是否进入都不能判定。
- gem5 Exec trace 可支持到更窄的 startup 交接边界：执行到
  `__libc_start_main+100@0x80000c70` 的间接 call，下一条却是
  `0x7ffffc80` 的 halt；它没有命中 `main@0x80000110`，也没有命中本 probe 的
  `malloc/free/munmap`。gem5 host rc 0 与 `SIM_END: halt code=0` 只描述该错误 halt，
  不构成 guest probe 成功。
- 源码、main 反汇编、map/why-extract、free 与 munmap 反汇编能证明两次分配、条件
  检查、反序 `free(b); free(a);` 以及真实 free→munmap syscall 链被编入且静态
  可达；不能证明任一分配、双块并存读写或任一次 free/munmap 在运行时发生。

因此当前动态证据上限是：gem5 定位到 startup 调用 `main` 的交接点发生偏离；
QEMU 尚未定位到任何源码阶段。下一最小阶段只应隔离 **startup → main-entry**：用
不含 allocator 的最小 main-entry 专用返回码先要求双后端共同命中。该门未闭合前，
不进入第一次 malloc 及其后的分阶段变体；原“第一次 malloc 返回至 free(a) 返回”
序列只能作为 main-entry 双端成立后的后续阶段，不能并入当前最小定位边界。
