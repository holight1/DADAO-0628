# DL-071a Worker Report：DADAO MC 立即数范围校验

日期：2026-07-23  
角色：Worker  
结论：Worker complete，等待独立 reviewer

## 1. 结果

DADAO 汇编器现在会在 matcher 阶段拒绝所有显式立即数字段的越界常量，
并给出包含合法上下界、指向实际 operand 的 diagnostic。修复不是
`addi 4096` 特判；同一机制覆盖算术、访存、wyde、shift、trap、
branch/call 等格式。

LLVM 普通 commit：

```text
72cb112b4c1eb4f00cb8e8facc78e5185edb1244
DADAO: diagnose out-of-range MC immediates
```

## 2. 系统审计

### 2.1 operand 与范围

| TableGen operand | 合法常量范围 | 代表性使用 |
|---|---:|---|
| `imms12` | -2048..2047 | `addi`、`cmps`、load/store、寄存器 jump/call |
| `immu12` | 0..4095 | `cmpu` |
| `imms18` | -131072..131071 | `swym`、`unimp`、`rela`、`ret` |
| `immu16` | 0..65535 | `orw`、`andnw`、`setzw`、`setow` |
| `immu6` | 0..63 | shift、extend、bank copy、indexed memory |
| `imms24` | -8388608..8388607 | direct `call` |
| `wydepos` | 0..3 | wyde position |
| `cfxcode6` | 0..63 | `trap` CFX code，复用 `immu6` matcher |
| `brtarget12` | -2048..2047 | `breq`、`brne` |
| `brtarget18` | -131072..131071 | 单寄存器条件 branch |
| `brtarget24` | -8388608..8388607 | direct `jump` |

`i64imm` 只出现在 CodeGen-only pseudo 的 frame-index 辅助 operand，
不是可由 DADAO AsmParser 输入的编码字段，因此不属于本次 MC 常量字段。

### 2.2 修复前行为

当前任务开始时，AsmParser 内虽然已有 `isImms12()` 等 helper，但 operand
没有设置 `ParserMatchClass`，因此 matcher 从未调用这些 predicate。
MCCodeEmitter 随后把值转为无符号数并由 TableGen 位域截取，造成静默截断。

基线实测以下越界样本全部 `rc=0`：

```text
addi rd8, rd0, -2049 / 2048
cmpu rd8, rd0, -1 / 4096
swym -131073 / 131072
orw rd8, 0, -1 / 65536
shlu rd8, rd0, -1 / 64
jump -8388609 / 8388608
orw rd8, -1, 0 / orw rd8, 4, 0
trap -1, 0 / trap 64, 0
breq rd1, rd2, -2049 / 2048
```

## 3. 实现

### 3.1 TableGen matcher

在 `DADAOInstrInfo.td` 中增加参数化 `DADAOImmAsmOperand`，为每种字段绑定：

- predicate；
- `addImmOperands` render method；
- 独立 diagnostic type。

同位宽、同语义的 branch target 与普通立即数共用 matcher class，避免范围漂移。
`cfxcode6` 与 `immu6` 同为无符号六位，也共用 matcher。

### 3.2 常量表达式和符号表达式

`DADAOOperand::isImmInRange<Bits, Signed>()` 使用
`MCExpr::evaluateAsAbsolute`：

- 普通常量和 `(2047 + 1)` 这类可求值表达式必须满足位宽；
- 含未解析 symbol 的表达式不在 parser 阶段误拒绝，继续进入原有 fixup。

正测试实际以 object 模式覆盖了：

```text
rela rb8, target
addi rb8, rb8, target
breq rd1, rd2, target
brz rd1, target
jump target
call target
```

### 3.3 Diagnostic

自定义 matcher result 在 `matchAndEmitInstruction` 中映射到精确范围，例如：

```text
error: immediate must be an integer in the range [-2048, 2047]
error: immediate must be an integer in the range [0, 65535]
```

错误位置取 `ErrorInfo` 对应 operand 的 `StartLoc`；缺 operand 仍走
“Too few operands”路径。

## 4. 测试证据

### 4.1 构建与新增 MC 测试

```text
$ ninja -C .work/build/llvm llvm-mc FileCheck
[5/5] Linking CXX executable bin/llvm-mc
```

合法边界文件 object 汇编 `rc=0`。负测试：

```text
llvm-mc rc=1 FileCheck rc=0
```

覆盖：

- 所有字段的上下边界；
- 每个字段上下各一越界；
- ML-024a 原始 `addi ..., 4096`；
- `jump/call` 寄存器 12 位形式；
- branch 12/18/24 位形式；
- 可求值常量表达式；
- 符号/fixup 表达式。

项目原有 MC suite：

```text
Total Discovered Tests: 14
Passed: 14 (100.00%)
```

LLVM 原生：

```text
$ .work/build/llvm/bin/llvm-lit -sv .work/llvm/llvm/test/MC/DADAO
fatal: Could not run .../.work/build/llvm/bin/llvm-config
rc=2
```

这是已有构建树配置限制。新增两项已直接执行其 RUN 命令，不能据此声称完整
LLVM MC 或 LLVM suite 通过。

### 4.2 E2E 暴露并消除旧截断依赖

第一次完整 E2E：

```text
Total Discovered Tests: 66
Passed: 65
Failed: tp_probe.test

tp_probe.test:85:21: error: immediate must be an integer in the range [-2048, 2047]
    addi rd16, rd0, 0x5A5A
```

该测试要把 `0x5A5A` 作为无关 sentinel；旧汇编器实际只编码低 12 位，
源码意图从未成立。最小测试修正为：

```text
setzw rd16, 0, 0x5A5A
```

两处均修正后：

```text
tp_probe.test: 1/1 PASS
E2E: 66/66 PASS
```

### 4.3 Differential 与门禁

```text
AGREE(3-way)=200
AGREE(interp+QEMU, gem5-SKIP)=2
DIVERGE=0
SAIL AGREE(4-way)=200
Sail-SKIP(out-of-slice)=2
SAIL-DIVERGE=0
```

```text
manifest validation: PASS
ISSUE REGISTRY: PASS
```

`check-issues` 为只读检查，未修改 issues。

## 5. Patch series 可复现性

导出：

```text
components/llvm/patches/0049-dadao-mc-immediate-range-validation.patch
SHA-256 a2611309ddfc9804246a85593c04e5815de8a233b0964d5728785a244538bc74
stable patch-id 41721c9276c69392ac3f2720aea034b4c9b61620
```

LLVM commit 的 stable patch-id 同为
`41721c9276c69392ac3f2720aea034b4c9b61620`。

从 manifest pin
`ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` 在临时 clone 中执行
plain `git am`：

```text
APPLIED=49
replay HEAD=07d5bc165c2659f624d20ece8938fe5abe0f4bb4
replay tree=214c454ff1fcf163d95e0d72f5c7743b69374dcf
current HEAD=72cb112b4c1eb4f00cb8e8facc78e5185edb1244
current tree=214c454ff1fcf163d95e0d72f5c7743b69374dcf
```

commit hash 因 `git am` 元数据不同而不同，tree 完全一致。`.work/llvm`
当前 clean。

## 6. 修改边界

主仓未提交。Worker 修改：

- `components/llvm/patches/0049-dadao-mc-immediate-range-validation.patch`
- `components/llvm/patches/series`
- `tests/lit/E2E/tp_probe.test`
- 本 task 完成区
- 本 worker report

组件修改只存在于上述 LLVM commit。未修改 QEMU、gem5、musl、spec、wiki、
issues、manifest 或 roadmap。
