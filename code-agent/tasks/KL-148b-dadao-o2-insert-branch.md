# KL-148b：DADAO Linux `-O2` insertBranch compiler gap

**状态**：待执行  
**日期**：2026-07-29  
**前置**：KL-148a  
**阻塞对象**：恢复 Linux 默认 `-O2` 构建；不阻塞当前 `-O0` K3 基本链路

## 问题

KL-148a 在头文件与语义检查全部通过后，以 Linux 5.4 默认 `-O2` 编译
upstream `init/main.c`，DADAO 后端在 `setup_command_line` 的
Control Flow Optimizer 中触发：

```text
Target didn't implement TargetInstrInfo::insertBranch!
UNREACHABLE executed at llvm/include/llvm/CodeGen/TargetInstrInfo.h
Running pass 'Control Flow Optimizer' on function '@setup_command_line'
```

同一源文件固定 `KCFLAGS=-O0` 后可生成 DADAO relocatable object，因此
KL-148a 按项目既定“先保证基本链路，暂不处理 `-O X`”约束继续。

## 后续任务要求

1. 从 KL-148a evidence 保存的完整 clang 命令提取最小 IR/MIR repro；
2. 为 DADAO `TargetInstrInfo` 正确实现 `insertBranch`/相关 CFG 接口，不得
   仅关闭 Control Flow Optimizer；
3. 增加 LLVM CodeGen 回归，覆盖 unconditional、conditional 和
   conditional+fallthrough 分支插入；
4. 重建 assertions-on LLVM，复跑 DADAO lit/E2E 与 Linux
   `init/main.o` 默认 `-O2`；
5. 独立 review 检查 CFG successor、branch polarity 和 fallthrough，
   防止只消除断言却生成错误控制流。

## Non-claim

本记录不是修复，也不声称 `-O1/-O2/-O3` 中只有这一处 Linux blocker。
