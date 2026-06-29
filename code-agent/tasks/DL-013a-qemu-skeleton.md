# DL-013a: QEMU Target Skeleton（Phase 3 骨架）

**执行环境**：本地 DS · DADAO-0628

---

## 目标

在 QEMU 10.0.0 基线上创建 DADAO target 骨架（`target/dadao/` + `hw/dadao/`），
使 `make build-qemu` 能真实编译出 `qemu-system-dadao`（可运行，任何指令均触发
ILLI/illegal instruction，不做 unimplemented 静默忽略）。

Phase 3 后续任务（DL-014a~018a）在此骨架上逐步实现具体指令和机器外设。

---

## 交付物

### 1. Patch 文件（放入 `components/qemu/patches/`）

命名：`0001-dadao-target-skeleton.patch`（单 patch 或多 patch 均可，`git am` 干净应用）。

#### 1.1 CPU 状态结构体（`target/dadao/cpu.h`）

必须包含以下字段，寄存器宽度和数量按 `contracts/isa/spec.md §1`：

```c
/* 按 ISA §1 — 4 个寄存器 bank */
uint64_t rd[64];    /* RD bank: rd0 固定为 0 */
uint64_t rb[64];    /* RB bank: rb0[63:48] 固定为 0 */
uint64_t rf[64];    /* RF bank */
uint64_t ra[64];    /* RA bank: ra1..ra63 = RegRAS */

uint64_t pc;        /* 程序计数器（字节地址，8字节对齐） */
```

复位值（`cpu_reset()`）按 `docs/adr/0004-test-machine.md §D2` 和 `contracts/isa/spec.md §1`：
- `rd[*] = 0`（rd0 恒为 0，reset 后也是 0）
- `rb[*] = 0`
- `rf[0] = 0x7FF800007FC00000`（QNaN，per `contracts/isa/spec.md §1.2`）；`rf[1..63] = 0`
- `ra[*] = 0`（per ISA spec §1）
- `pc = 0`（ROM trampoline 由 hw/dadao/machine.c 的 loader 设置，见 §D2）

#### 1.2 QOM / CPU 注册（`target/dadao/cpu.c`）

- TypeInfo：`.name = DADAO_CPU_TYPE_NAME("any")`
- 实现 `dadao_cpu_do_interrupt()`（存根，写 exit port 0x82 —— ILLI 行为，per ADR-0004 §D5）
- 实现 `dadao_cpu_tlb_fill()`（存根，Phase 3 scope 仅使用物理地址）
- CPUClass 的 `disas_set_info`：设置 bfd_arch（或 return 不实现均可，Phase 2 disasm 覆盖）

#### 1.3 TCG 翻译骨架（`target/dadao/translate.c`）

- `gen_intermediate_code()` 骨架：读取一条 32-bit 大端指令字
- 所有指令分派默认调用 `gen_exception_illegal()`（ILLI），不做任何具体实现
- DADAO 指令固定 32-bit 宽（per `contracts/isa/spec.md §2.1`），fetch 步进为 4

```c
/* 提示：QEMU 10.x 大端 fetch 示例（32-bit） */
uint32_t insn = translator_ldl_swap(env, &ctx.base, ctx.base.pc_next, false);
/* false = big-endian swap (已是大端内存，不需要额外 swap) */
/* — 具体 API 以 target/riscv/translate.c 实现为参考 */
```

#### 1.4 Helper 骨架（`target/dadao/helper.c` + `helper.h`）

- `DADAO_helper_raise_exception()`：将 exception index 写入 CPUState 并 raise
- `DADAO_helper_illegal()`：调用 raise_exception(EXCP_ILLI)
- exception index 定义在 `cpu.h`：`EXCP_ILLI = 0`，`EXCP_UNDI = 1`

#### 1.5 `target/dadao/meson.build`

参考 `target/riscv/meson.build`；列出 `cpu.c`、`translate.c`、`helper.c`；
不链接 decodetree 生成文件（DL-014a 任务）。

---

### 2. 裸机机器模型骨架（`hw/dadao/`）

#### 2.1 内存映射（`hw/dadao/dadao-machine.c`）

按 `docs/adr/0004-test-machine.md §D1` 实现：

| 区域 | 起始地址 | 大小 | 类型 |
|------|---------|------|------|
| ROM | 0x00000000 | 64 KB | ROM（load trampoline.bin） |
| RAM | 0x80000000 | 128 MB | RAM（load test binary） |
| Exit Port | 0x10000000 | 8 B | MMIO |

**loader 逻辑**：
- `-bios <file>` → ROM 区域（0x00000000）；无 `-bios` → 报错退出（per ADR-0004）
- `-kernel <file>` → RAM 区域（0x80000000）；无 `-kernel` → 报错退出
- CPU 复位后 `pc = 0x00000000`（ROM entry）

**Exit Port MMIO（per ADR-0004 §D3）**：
- 写 8 字节（`std`）→ 读取低字节作为 exit code，调用 `qemu_system_shutdown_request()`
- 写非 8 字节（`stb/stw/stt`）→ ILLI（per ADR-0004 §D5：宽度违规）
- 读操作 → 未定义（可 ignore 或 return 0）

#### 2.2 QEMU machine 注册

`.name = "dadao-baremetal"`，`MachineClass.default_cpu_type = DADAO_CPU_TYPE_NAME("any")`

#### 2.3 `hw/dadao/meson.build`

注册机器；链接 `dadao-machine.c`。

---

### 3. QEMU 构建系统集成（patch 内包含）

| 文件 | 改动 |
|------|------|
| `configs/targets/dadao-softmmu.mak` | 新建（或按 QEMU 10.0 实际机制添加 target） |
| `default-configs/targets/dadao-softmmu.mak` | 同上 |
| 顶层 `meson.build` 或 `Kconfig` | 添加 dadao-softmmu target |

> **注意**：QEMU 10.0 使用 meson 构建；target list entry 格式参考
> `configs/targets/riscv64-softmmu.mak`（或 QEMU 10.0 的对应路径）。

---

### 4. `Makefile` — `build-qemu` 替换为真实构建

```makefile
QEMU_SRC   := .work/qemu
QEMU_BUILD := .work/build/qemu

build-qemu: manifest-check
	cd $(QEMU_SRC) && ./configure \
	  --target-list=dadao-softmmu \
	  --enable-tcg \
	  --disable-werror \
	  --prefix=$(CURDIR)/.work/install/qemu
	$(MAKE) -C $(QEMU_SRC) -j$$(nproc)
	@echo "build-qemu: PASS"
```

---

### 5. 最小冒烟测试（`tests/lit/QEMU/Dadao/`）

**`tests/lit/QEMU/Dadao/smoke-boot.sh`**（shell script，非 lit）：

```bash
#!/bin/bash
# 使用 ADR-0004 ROM trampoline 协议启动，验证机器模型不崩溃
# 准备：trampoline.bin（全 0，即 swym NOP 循环）；test.bin（单条 addi rd1, 0, 0 + exit）
# 预期：qemu-system-dadao 正常退出（不 SIGSEGV）
```

完整脚本内容由 DS 决定；冒烟测试目标是"机器启动不崩溃"，不验证指令语义（语义在 DL-015a~018a）。

---

## 约束

1. **不实现任何指令语义**：所有指令统一走 `gen_exception_illegal()`，DL-014a 开始引入 decodetree
2. **大端**：指令 fetch 和数据访问均为大端（per `contracts/isa/spec.md §2.1`），TCG 标志 `IS_LITTLE_ENDIAN = false`
3. **exit port 宽度检查**：宽度≠8 必须触发 ILLI，不得静默忽略（ADR-0004 §D5 明确）
4. **patch 干净 apply**：`git am` 到 `.work/qemu/` 后 `make qemu-system-dadao` 成功编译
5. **`make prepare` 先运行**：完成区须注明 DS 已执行 `make prepare` fetch 源码
6. **CPUState 字段命名**：`rd[64]`、`rb[64]`、`rf[64]`、`ra[64]`（后续任务直接引用这些名称）
7. **rf[0] 复位值**：`0x7FF800007FC00000`（必须与 `contracts/isa/spec.md §1.2` 一致）

---

## 验收步骤（DS 完成区写出以下输出）

```
make prepare           →  llvm + qemu fetched, patches applied
make build-qemu        →  meson + ninja dadao-softmmu: PASS
qemu-system-dadao --machine dadao-baremetal --help  →  不报错，显示机器选项
smoke-boot.sh          →  启动不崩溃（exit 0 或预期的 exit code）
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `target/riscv/cpu.h`, `cpu.c` | CPU state 和 QOM 注册参考 |
| `target/riscv/translate.c` | TCG 翻译骨架、大端 fetch 示例 |
| `hw/riscv/sifive_e.c` | 裸机 machine 实现参考 |
| `docs/adr/0004-test-machine.md` | 内存映射、exit port 协议、reset 值权威来源 |
| `contracts/isa/spec.md §1` | 寄存器 bank、宽度、reset 值 |
| `contracts/isa/spec.md §2.1` | 大端指令 fetch、4-byte 对齐 |
| `code-agent/designs/0002-detailed-roadmap.md` §Phase 3 | exit gates |

---

## 完成区

<!-- DS 在此填写 -->
