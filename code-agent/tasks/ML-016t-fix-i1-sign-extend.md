# ML-016t：修复 i1 sign_extend_inreg lowering

**日期**：2026-07-21

**状态**：Audit-accepted-with-findings（ML-016 新 30-task run：20/30）

## 背景

ML-016l 将 `puts.o` 唯一失败定位为 `sext i1 -> i8/i32/i64` 的
`sign_extend_inreg`；zext、bool return、branch/select、volatile 和 i8/i32 sign
extension 对照均通过。ML-016s 新 matrix 仍保留该单例。需要实现最小 legalize/lowering
修复，不影响其它整数或 f64 路径。

## 目标与 ownership

worker 只负责 DADAO i1 sign-extension 的最小修复与回归：

1. 阅读当前 DADAO target 的 `SIGN_EXTEND_INREG`/integer legalization、MVT i1/ch/i32
   处理，选择最小实现位置；不要修改 calling convention、AsmPrinter、inline asm hook
   或其他 failure cluster。
2. 只修改必要的 DADAO lowering 文件（优先
   `.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp/.h`），记录精确
   diff 和实现依据。
3. 实际重编 clang/llc，运行 ML-016l 的 sext i1、zext i1、bool/branch/select、
   i8/i32 对照，以及 fresh/旧 `puts.o` 可用的 source/IR probe；保存修复前后 rc、
   stderr、IR/MIR/asm。若原 puts source 受 header 阻塞需单独报告。

## 约束

- 只写本 task 完成区、必要的 DADAO lowering 文件和
  `docs/reviews/ML-016t-fix-i1-sign-extend-20260721.md`；临时证据放
  `/tmp/ml-016t-fix-i1-sign-extend-20260721/`。
- 不修改 musl、主 libc archive、contracts、vectors、issues、wiki、ML-014a、QEMU/gem5；
  不访问或引用 `~/toolchain`、`~/knowledge-graph`。
- 不使用 `|| true`；必须确认使用新编译器产物。不要扩大修改到 f64/libcall、RB31、
  dynamic_stackalloc、tail-call 或 SelectionDAG illegal-result。
- worker 不是独自在仓库工作，不得回滚已有改动；完成后列出修改文件。

## 完成区

### worker 交付（2026-07-21）

状态：已完成，待独立 review。

实现只修改了
`.work/source/llvm/llvm/lib/Target/DADAO/DADAOISelLowering.cpp`：在 `ADD/SUB`
legal action 附近增加

```cpp
setOperationAction(ISD::SIGN_EXTEND_INREG, MVT::i1, Expand);
```

并附带说明。`LegalizeDAG` 对 `SIGN_EXTEND_INREG` 按 operand 1 的 inner type 查询
action；DADAO 原先对 `i1` 继承默认 `Legal`，但没有对应 selector pattern。现在明确
请求 LLVM 通用 i1 expansion（先 `and 1` 再 `sub 0`），得到 false→0、true→-1，未
改 TableGen、AsmPrinter、inline-asm hook、calling convention 或其他 failure cluster。
精确 before/after diff 保存在
[`DADAOISelLowering.before-after.diff`](/tmp/ml-016t-fix-i1-sign-extend-20260721/build/DADAOISelLowering.before-after.diff)。

实际执行 `ninja -C .work/build/llvm clang llc` 重编；修复后工具为 clang/llc
22.1.8、LLVM revision `40bc313742b00848d341e77e1a38441211971729`，clang SHA-256
为 `d1c6e0026741e45f7ae98f13d4057a6838f9ef049d6b9d110152a2f90ce94bdc`，llc SHA-256
为 `ac7a71404061254b68f7d43cd343f4b121952af77b0ef7cb2428a15231ad2f9c`；版本、路径、
hash 和最终 ninja verify rc=0 见 `/tmp/ml-016t-fix-i1-sign-extend-20260721/after/metadata.txt`
与 `build/ninja-final-verify.*`。

回归结果：

- IR singleton 18 probes × O0/O3：修复前 clang 28/36、llc 28/36、MIR 28/36
  成功；8 条失败均为 `sext i1`/`bool_neg_use`，clang rc=1、llc/MIR rc=134，stderr
  为 `Cannot select ... sign_extend_inreg ... ValueType:ch:i1`。修复后 clang、llc、
  MIR 均 36/36 rc=0。
- C matrix 12 probes × O0/O3：修复前 clang/llc 各 20/24 成功，失败仅
  `bool_neg`、`bool_select_neg`（clang rc=1、llc rc=134）；使用新 clang 重新生成
  fresh IR 后 frontend、clang、llc、MIR 均 24/24 rc=0。保留了 bool return、branch、
  select、volatile i1 以及 i8/i32 对照。
- 带隔离 musl include 路径的 original `puts.c`：修复前 frontend O0/O3 rc=0，
  clang/source object 各 rc=1，llc rc=134；修复后 frontend、clang、llc、object、
  MIR O0/O3 全部 rc=0。`puts` IR、MIR、asm、stderr 和 argv 均在临时证据目录。
- 无 header/include 路径的 original `puts.c` 仍单独为 host-header 边界：O0/O3
  均 rc=1，`fatal error: 'stdio_impl.h' file not found`；这不是 backend 修复失败。
  standalone `puts-equivalent.c` 的 O0/O3 frontend、clang、llc、MIR 全部 rc=0；O0
  保留 zext+sub 形状，O3 被优化为等价整数逻辑。

修复前后完整 raw evidence（rc、stderr、IR、MIR、asm、argv）集中在
[`/tmp/ml-016t-fix-i1-sign-extend-20260721/`](/tmp/ml-016t-fix-i1-sign-extend-20260721/)，
包括 `before/results.tsv`、`after/results.tsv`、fresh C 记录、`puts-equivalent` 记录、
`complete.txt` 和 `evidence-sha256.txt`。未打包或替换 archive，未做 link/runtime、
QEMU/gem5 验收。仓库内本 task 写入的文件为本完成区、指定 review 文档和上述一个
DADAO lowering 文件；既有协作者改动未回滚。

独立 reviewer James the 2nd 的结论为 **Accepted-with-findings**，见
`docs/reviews/ML-016t-independent-review-20260721.md`。review 确认实现 diff 只
增加 `SIGN_EXTEND_INREG/i1 -> Expand`，36/36 singleton、C matrix 和隔离 include
puts 链路通过；finding 是 evidence hash 清单包含自身 hash，导致全量校验 rc=1，
其余 2454 项通过，不影响编译结果。
