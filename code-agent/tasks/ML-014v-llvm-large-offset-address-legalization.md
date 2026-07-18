# ML-014v：合法化 DADAO load/store 越界常量地址

**执行环境**：本地 subagent worker；承接 Accepted ML-014u

**状态**：Ready（30-task run：2/30）

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

（由 worker 填写；完成后由不同 subagent 独立 review）

