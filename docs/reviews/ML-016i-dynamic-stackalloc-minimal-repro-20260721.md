# ML-016i dynamic_stackalloc minimal repro review

日期：2026-07-21  
状态：worker complete；仅诊断，未修改 LLVM、musl、主 build/archive 或测试。

## 结论

最小且不依赖内存访问、调用或返回值的失败形状是：

```llvm
define void @dynamic_void(i64 %n) {
entry:
  %p = alloca i8, i64 %n, align 1
  ret void
}
```

这个 probe 在 O0/O3 的 `llc -mtriple=dadao` 都以 `rc=134` 失败，stderr 的首个 DAG 诊断均为 `Cannot select ... dynamic_stackalloc`。因此 VLA、指针逃逸、调用、load/store、动态对齐都不是该失败的必要条件。对应原始 IR、argv、rc、stderr 和（成功项的）asm 输出位于 [probes/ir/dynamic_void.ll](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/ir/dynamic_void.ll)、[logs/llc](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/logs/llc) 和 [probes/asm](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/asm)。

成功边界是固定大小 alloca：`fixed_alloca.ll` 的 O0/O3 frontend IR、clang asm 和 llc asm 均成功（rc=0）。其 asm 只展示静态 frame 调整，例如 `rb1 -= 32`、访问 `rb1/rb8`、`rb1 += 32`；这不能外推到动态 frame lowering。

## 完整矩阵

矩阵由 `/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/run-matrix.sh` 运行，所有命令均保存逐参数 argv、原始 stdout/stderr 和 rc；编译器崩溃诊断的 `TMPDIR` 也限制在该 task 目录。

| 阶段 | 命令数 | rc=0 | 非零 rc | 说明 |
|---|---:|---:|---:|---|
| 9 个 C probe frontend IR，O0/O3 | 18 | 14 | 4 | 两个显式 `__builtin_stack_save/restore` C 文件被 frontend 判为 unknown builtin；这不是 backend 证据 |
| 9 个 C probe 直接 clang asm，O0/O3 | 18 | 2 | 16 | 仅 fixed alloca 两个优化级别成功；动态形状均进入 backend 失败 |
| 10 个显式 IR llc，O0/O3 | 20 | 2 | 18 | fixed alloca 成功；dynamic alloca 类为 rc=134 |
| 7 个 ML-016f representative frontend IR，O0/O3 | 14 | 14 | 0 | frontend-only 成功不等于 backend 成功 |
| 7 个 representative 直接 clang asm，O0/O3 | 14 | 0 | 14 | 全部 rc=1，stderr 保留 backend 诊断 |
| 7 个 representative IR llc，O0/O3 | 14 | 0 | 14 | 全部 rc=134 |

显式 IR 的对照结果：

| 形状 | O0/O3 llc | 失败节点 |
|---|---|---|
| fixed alloca | 0/0 | 成功 |
| `alloca i8, i64 %n`, `ret void` | 134/134 | `dynamic_stackalloc` |
| `alloca i8, i64 %n`, 纯栈 store/load，返回 i32 | 134/134 | `dynamic_stackalloc` |
| 动态 alloca 返回指针 | 134/134 | `dynamic_stackalloc` |
| 动态 alloca 后传给外部调用 | 134/134 | `dynamic_stackalloc` |
| VLA 等价 IR | 134/134 | `dynamic_stackalloc` |
| 动态大小 + `align 32` | 134/134 | `dynamic_stackalloc`，DAG 对齐操作数为 32 |
| `stacksave` + fixed alloca + `stackrestore` | 134/134 | `stackrestore` |
| `stacksave` + dynamic alloca + `stackrestore` | 134/134 | `stackrestore`（该 probe 的 selector 先撞到 restore） |

C VLA 的优化级别还改变了最先暴露的节点：O0 直接 clang 诊断为 `stackrestore`，O3 诊断为 `dynamic_stackalloc`；两者都失败。C frontend 生成的 VLA O0 IR 同时含 `llvm.stacksave`、动态 alloca、`llvm.stackrestore`，O3 IR 保留动态 alloca。这个顺序差异不能作为根因优先级证明。

## 7 个原始失败对象对照

ML-016f 原始 `.record/.stderr` 已只读复制到 [raw-ml-016f](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/raw-ml-016f)，对应 source 副本和 O0/O3 frontend IR 在 [representatives](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/representatives)。7 个对象均为 frontend IR rc=0、直接 clang backend rc=1、llc rc=134；O0/O3 都复现。

| object / function | source 形状 | IR 中的动态 frame 形状 |
|---|---|---|
| `locale/dcngettext.o` / `dcngettext` | `char name[...]`，大小由 `dirlen/loclen/modlen/catlen/domlen` 合成 | `llvm.stacksave` + `%vla = alloca i8, i64 %add76` + restore |
| `network/res_msend.o` / `__res_msend_rc` | `pfd[nqueries+2]`、`qpos[nqueries]`、`apos[nqueries]`、`alen_buf[nqueries][2]` | 多个由 `nqueries` 派生的动态 alloca，带 stacksave/restore |
| `process/execl.o` / `execl` | varargs 计数后的 `char *argv[argc+1]` | `%vla = alloca ptr, i64 %4, align 8`，调用 `execv` 后 restore |
| `process/execle.o` / `execle` | 同一 VLA，另取 `envp` | `%vla = alloca ptr, i64 %4, align 8`，调用 `execve` 后 restore |
| `process/execlp.o` / `execlp` | 同一 VLA，调用 `execvp` | `%vla = alloca ptr, i64 %4, align 8`，调用后 restore |
| `process/execvp.o` / `__execvpe` | `char b[l+k+1]`，PATH/file 长度派生 | `%vla = alloca i8, i64 %add16, align 1`，循环中多次 restore |
| `unistd/getcwd.o` / `getcwd` | `char tmp[buf ? 1 : PATH_MAX]` | `%vla = alloca i8, i64 %2, align 1`，大小为 select(1,4096) |

原始 ML-016f 的共同 stderr 仍保存完整 DAG，例如 `dcngettext` 的动态大小由多个 frame slot load 相加后对齐，`getcwd` 的大小由参数 `buf` 参与的 select 产生；这些复杂表达式不是最小触发条件，而是代表性 caller 形状。

## ABI/frame 尚未闭合的假设

本任务没有证明以下后端契约，不能把 probe 结果升级为 ABI 修复结论：

- 动态 frame 的增长方向、`size` 的字节单位、向下取整/对齐规则，以及动态调整后 frame index 如何重新物化。
- DADAO stack pointer、frame/base pointer 的实际寄存器约定，以及动态调整期间固定 alloca、callee-saved 寄存器和 epilogue 的关系。成功静态 asm 只观察到 `rb1/rb8`，不足以确认动态路径契约。
- `llvm.stacksave/stackrestore` 返回值的表示、restore 的 chain/ordering 语义、嵌套/循环 restore 和异常路径；独立 fixed-allocation IR 已表明 `stackrestore` 自身也没有 selector。
- 动态 alloca 指针作为返回值、外部调用参数、varargs `argv` 或 `getcwd` 返回值时的 ABI、生命周期和寄存器分配规则。`dynamic_void`/`pure_stack` 说明这些不是 `dynamic_stackalloc` 的必要触发条件，但没有验证它们修复后的 ABI 行为。
- O0 与 O3 在 frame lowering、stack lifetime intrinsic 消除和 selector DAG 构造上的差异；本次仅记录失败边界，没有修改或验证 backend 修复。

所以后续 backend 修复至少应分别覆盖 dynamic alloca selection/frame lowering 与 `stacksave/stackrestore` selection，并用 static-allocation success、`dynamic_void`、VLA O0/O3、动态对齐、escape/call 和上述 7 个 representative 做 CodeGen 回归；不能以 frontend-only、单个 llc 成功或 link 成功作为 libc/runtime 验收。

## 原始证据索引

- probe source：[/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/c](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/c)
- explicit IR：[/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/ir](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/ir)
- source frontend/backend argv、rc、stdout、stderr：[/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/logs/compile](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/logs/compile)
- explicit IR and representative llc argv、rc、stdout、stderr：[/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/logs/llc](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/logs/llc)
- representative source/IR/backend evidence：[/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/representatives](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/probes/representatives)、[/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/logs/representatives](/tmp/ml-016i-dynamic-stackalloc-minimal-repro-20260721/logs/representatives)
