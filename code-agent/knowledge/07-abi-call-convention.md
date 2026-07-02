# §7 ABI 调用约定（M1 非变参标量）

**来源**：DL-002a, DL-018a review（2026-07-02）  
**交叉验证**：contracts/abi/spec.md, contracts/isa/spec.md §5

---

## §7.1 寄存器角色

### RD（数据寄存器）
| 寄存器 | ABIname | 角色 | Callee-saved |
|--------|---------|------|-------------|
| rd0 | rdzero | 硬连接零 | Immutable |
| rd1 | rderrno | 错误码（M1 不可分配，volatile） | — |
| rd2–rd7 | — | 保留（编译器不得分配） | — |
| rd8–rd15 | rdt0–rdt7 | 临时 | No |
| rd16–rd31 | rda0–rda15 | 参数 / 临时 | No |
| rd32–rd63 | — | 通用 | **Yes** |

### RB（基址寄存器）
| 寄存器 | ABIname | 角色 | Callee-saved |
|--------|---------|------|-------------|
| rb0 | rbip | 指令指针（只读） | — |
| rb1 | rbsp | 栈指针 | **Yes** |
| rb2 | rbfp | 帧指针（可选） | **Yes** |
| rb3 | rbgp | 全局指针（M1 不可分配） | — |
| rb4 | rbtp | 线程指针（M1 不可分配） | — |
| rb5–rb7 | — | 保留 | — |
| rb8–rb15 | rbt0–rbt7 | 临时 | No |
| rb16–rb31 | rba0–rba15 | 参数 / 临时 | No |
| rb32–rb63 | — | 通用 | **Yes** |

## §7.2 参数传递

三 bank 独立计数（RD/RB/RF），从寄存器 16 起始：

| 参数类型 | Bank | 寄存器 |
|---------|------|--------|
| 整数/标量 | RD | rd16–rd31 |
| 指针/地址 | RB | rb16–rb31 |
| 浮点 | RF | rf16–rf31（M1 排除） |

窄类型（<8 字节）符号/零扩展至完整 64 位。寄存器溢出时，剩余参数按声明顺序入栈。

## §7.3 返回值

| 类型 | 寄存器 |
|------|--------|
| 标量整数 | **rd31** |
| 指针/地址 | **rb31** |
| 多返回值 | 逆序：首值→rd31, 次值→rd30, 等等到 rd16 |

## §7.4 栈帧

- SP = rb1（向下增长）
- FP = rb2（可选，若使用则指向保存的旧 FP）
- Red zone = 128 字节（rbsp 下方，信号处理不触碰）
- SP 在 call 前须 8 字节对齐

## §7.5 RegRAS 约定（call/ret）

- `call`：自动将返回地址 push 到 ra[63]（M1 阶段简单实现，无堆栈移位）
- `ret`：从 ra[63] 弹出返回地址 → PC
- RA 寄存器不属于 caller/callee-saved 框架
- 软件无需显式保存/恢复 RA（同一 TU 内 leaf 和非 leaf 函数均如此）

## §7.6 sret（结构体返回）

- 聚合 > 64 位：caller 预分配空间，地址通过 **rb16** 传入（隐藏首参数）
- 聚合 ≤ 64 位：通过 rd31 返回
- M1 BasicCodeGen 仅处理标量返回值，sret 为 M2 scope

## §7.7 FP 序言/尾声（RB 高 16 位安全模式）

**序言**（使用 rb2rb 保持高位复制，而非 addi 算术）：
```asm
rb2rb rb2, rbsp, 1      # 完整 64 位复制（rbfp = incoming_sp）
addi  rb2, rb2, -8       # 在自己的 RB bank 内调整（高 16 位稳定）
```

**尾声**（使用 ldo 加载完整 64 位，而非 addi 算术）：
```asm
addi  rbsp, rbsp, frame_size
ldo   rbfp, rbsp, -8     # 从内存覆盖所有 64 位（不清零高 16 位）
ret   rd0, 0
```

关键：`addi` 仅影响低 48 位，RB 算术保留高 16 位。从 rbsp 复制到 rbfp 时须使用
rb2rb 或 ldo（全覆盖操作）以保证高 16 位正确传输，而非依赖保留语义。
