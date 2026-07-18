# ML-014v：合法化 DADAO load/store 越界常量地址

**执行环境**：本地 subagent worker；承接 Accepted ML-014u

**状态**：Completed awaiting independent review（2026-07-18）

## 目标

修复 LLVM DADAO DAG selector 对 load/store 地址的非法常量折叠：signed-12
范围内继续使用 RRII 立即数，范围外保留完整 `ADD(base, constant)`，让已有大常量
物化与 RB/RD 地址加法形成完整地址，再以 0 偏移访存。添加 LLVM in-tree CodeGen
回归，覆盖 load/store、访问宽度和 signed-12 边界。

## Ownership

- worker 负责外部 LLVM source tree：
  - `llvm/lib/Target/DADAO/DADAOISelDAGToDAG.cpp`
  - `llvm/test/CodeGen/DADAO/load-store-offset-range.ll`
  - 必要的 `llvm/test/CodeGen/DADAO/lit.local.cfg`
  - 本 task MD 完成区与本任务 `.work/ML-014v-*` 证据。
- 本任务在 LLVM source tree 产生一个普通 commit；暂不导出 root `0040` patch，
  patch export/integration 另开任务。
- 不修改 QEMU、gem5、musl、root tests、patch series、issues、contracts、manifest
  或用户原始 ML-014a；不处理 MC parser 的越界诊断。
- 外部架构资料不在 worker scope；多人共享仓库，不得回滚他人改动。

## 执行阶梯

1. 先用测试固化修复前行为，至少覆盖 `2047/2048/-2048/-2049/131051`，包含
   i8 load/store，并至少抽样 i16/i32/i64，证明不是仅特判本例。
2. 在 selector 中使用 LLVM 通用 signed-width 判断；仅对可编码 signed-12 常量
   拆出 `GEPOff`，越界地址留给已有 constant/add selection。
3. 增量构建 `llc`/必要测试工具；运行 FileCheck 或单条 llvm-lit，保留真实命令
   和退出码。检查修复后越界值完整物化、memory immediate 为 0，边界内仍折叠。
4. 运行已有相关 DADAO CodeGen/最小 smoke；记录未验证项和 source commit。
5. 更新完成区并等待不同 subagent 独立 review。

## 验收

- source diff 仅限最窄 selector 修复和 in-tree regression；无 silently masked
  compiler-generated memory immediate。
- `2047/-2048` 直接折叠，`2048/-2049/131051` 形成完整地址并以合法立即数访存。
- build 与最小回归通过；失败不得标完成。
- 不宣称 mallocng、ML-014f 或 ML-014a 完成。

## 完成区

### 完成：signed-12 地址折叠门控与 in-tree 边界回归

在 detached、初始 clean 的 LLVM source 基线
`92dd91c67c08f6b680d11c7b713f87c496cd5d94` 上完成最小修复，并创建普通 source
commit：

```text
1697be42b5b1 DADAO: legalize out-of-range memory offsets
```

source diff 仅有以下 3 个 ownership 内文件：

- `llvm/lib/Target/DADAO/DADAOISelDAGToDAG.cpp`：在从通用 `ADD` 地址拆出
  `GEPOff` 前使用 LLVM `isInt<12>`；`[-2048, 2047]` 继续折叠，越界时保留完整
  `ADD(base, constant)`，沿用已有 `CONST_WYDE`、地址 `add` 与 memory offset 0
  路径；
- `llvm/test/CodeGen/DADAO/load-store-offset-range.ll`：i8 load/store 均覆盖
  `2047/2048/-2048/-2049/131051`，并以自然对齐 i16 load、i32 store、i64 load
  越界样本确认不是宽度或 opcode 特判；
- `llvm/test/CodeGen/DADAO/lit.local.cfg`：仅在构建 DADAO target 时启用该目录。

#### 回归先行与验证结果

修复前先运行测试的 `llc | FileCheck` 等价命令，退出码为 `1`；诊断直接显示旧
输出仍包含 `ldbu/stb ..., 2048/-2049/131051`，证明回归能抓住非法 RRII 折叠。
修复后结果：

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `cmake --build .work/build/llvm --target llc count -j2` | `0` | selector 增量编译及 `llc` 链接成功 |
| `cmake --build .work/build/llvm --target not -j2` | `0` | 补齐单测初始化所需的最小工具 |
| `llc -mtriple=dadao < test.ll \| FileCheck test.ll` | `0` | 默认 CodeGen 级别边界回归通过 |
| `llc -O0 -mtriple=dadao < test.ll \| FileCheck test.ll` | `0` | `-O0` 边界回归通过 |
| `llc -mtriple=dadao ML-014u/minimal_direct.ll -o /dev/null` | `0` | 既有相关最小 IR smoke 通过 |
| `git diff --check` | `0` | 无 whitespace error |

FileCheck 逐函数确认：`2047/-2048` 直接作为 load/store immediate；
`2048/-2049/131051`（及宽访问越界样本）完整 `setzw/orw` 物化后参与地址 `add`，
最终 load/store immediate 为 `0`。

#### 受限项与范围自审

单条 `llvm-lit -v llvm/test/CodeGen/DADAO/load-store-offset-range.ll` 在该 target-only
构建中退出 `2`，发生于测试执行前的 lit 初始化：即使增量补建 `count`、`not`，
构建目录仍无 `llvm-config`，lit 无法查询 assertion/build mode。按最小范围不继续
构建整套测试工具；上表两条 RUN-line 等价的真实 `llc | FileCheck` 均已通过，完整
命令与退出码记录在
`.work/ML-014v-llvm-large-offset-address-legalization/run-summary.txt`。

没有改 MC parser、QEMU、gem5、musl、root tests、patch series、issues、contracts
或 manifests；没有触碰原始未跟踪 ML-014a，没有导出 root patch，也不宣称
mallocng、ML-014f 或 ML-014a 完成。本任务为 **Completed awaiting independent
review**。
