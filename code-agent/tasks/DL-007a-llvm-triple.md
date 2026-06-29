# DL-007a: LLVM Triple 注册与最小 Build（Phase 2 骨架）

**执行环境**：本地 DS · DADAO-0628

---

## 目标

在 LLVM 22.1.8 基线上注册 DADAO triple，构建出能通过 cmake/ninja 的最小空
target，使 `llvm-mc --triple=dadao-unknown-elf` 不报 "unknown target" 错误，
并将 `Makefile build-mc` 从 stub 替换为真实 cmake + ninja 构建。

Phase 2 后续任务（DL-008a~012a）均在此骨架上叠加，所以本任务必须保持 API
清晰、不做超出注册和 build 的内容。

---

## 交付物

### 1. Patch 文件（放入 `components/llvm/patches/`）

命名格式：`0001-dadao-triple-registration.patch`（单 patch 或拆多个均可，
保持逻辑独立）。所有 patch 必须能被 `git am` 干净应用到 `.work/llvm/`。

Patch 必须包含以下改动（不限实现方式，以能 build 为准）：

#### 1.1 Triple 注册

| 文件（相对 llvm-project 根） | 必须改动内容 |
|-----------------------------|-------------|
| `llvm/include/llvm/TargetParser/Triple.h` | 在 `ArchType` 枚举中添加 `dadao` |
| `llvm/lib/TargetParser/Triple.cpp` | `getArchTypeName`、`parseArch`、`getDefaultFormat` 等函数补全 dadao 条目 |
| `llvm/lib/Target/CMakeLists.txt` | 添加 `DADAO` 到 `LLVM_ALL_TARGETS` 列表 |

#### 1.2 最小 Target 目录（`llvm/lib/Target/DADAO/`）

以 Lanai 为参考（`llvm/lib/Target/Lanai/`），创建最小可 build 的骨架：

| 文件 | 内容 |
|------|------|
| `CMakeLists.txt` | 最小 LLVM 组件定义；包含 MCTargetDesc 子目录 |
| `DADAO.h` | 空头文件（后续任务填充） |
| `DADAOTargetMachine.h` | 前向声明 DADAOTargetMachine 类 |
| `DADAOTargetMachine.cpp` | 继承 LLVMTargetMachine；注册 triple；实现 `getSubtargetImpl` 存根 |
| `TargetInfo/DADAOTargetInfo.h` | 声明 `getTheDADAOTarget()` |
| `TargetInfo/DADAOTargetInfo.cpp` | 调用 `RegisterTarget`，triple = `"dadao"`，desc = `"DADAO SimRISC"` |
| `MCTargetDesc/CMakeLists.txt` | 最小 MCTargetDesc 组件 |
| `MCTargetDesc/DADAOMCTargetDesc.h` | 空头文件 |
| `MCTargetDesc/DADAOMCTargetDesc.cpp` | 注册 MCAsmInfo（可为空 stub）；后续任务填充 |

#### 1.3 AsmInfo 存根

创建 `MCTargetDesc/DADAOMCAsmInfo.h` + `.cpp`，继承 `MCAsmInfoELF`，设置：
- `CommentString = "#"`
- `SupportsDebugInformation = false`（Phase 2 scope）

不需要正确的 TAB/Section 设置，后续任务补充。

#### 1.4 ELF 文件头存根

创建 `MCTargetDesc/DADAOELFObjectWriter.cpp`，继承 `MCELFObjectTargetWriter`：
- `getOSABI()` → `ELFOSABI_NONE`
- `getEMachine()` → `0x0DA0`（`EM_DADAO`，per `contracts/elf/spec.md §1.3`）
- `needsRelocateWithSymbol()` → false（存根，DL-012a 完善）
- `getRelocType()` → 返回 0（存根）

---

### 2. `components/llvm/patches/series` 更新

将新 patch 文件名逐行写入 `series`（一行一个文件名）。

---

### 3. `Makefile` — `build-mc` 替换为真实构建

将存根替换为：

```makefile
LLVM_BUILD := .work/build/llvm
LLVM_SRC   := .work/llvm/llvm

build-mc: manifest-check
	cmake -G Ninja \
	  -B $(LLVM_BUILD) \
	  -S $(LLVM_SRC) \
	  -DLLVM_TARGETS_TO_BUILD=DADAO \
	  -DLLVM_ENABLE_PROJECTS="" \
	  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
	  -DLLVM_ENABLE_ASSERTIONS=ON
	ninja -C $(LLVM_BUILD) llvm-mc llvm-objdump llvm-lit FileCheck
	@echo "build-mc: PASS"
```

`LLVM_BUILD` 和 `LLVM_SRC` 可以使用 `?=` 语法允许外部覆盖。

---

### 4. 最小 lit 测试（`tests/lit/MC/Dadao/`）

创建一个最小冒烟测试，仅验证 triple 注册成功：

**`tests/lit/MC/Dadao/triple-smoke.s`**：
```asm
# RUN: llvm-mc --triple=dadao-unknown-elf -o /dev/null %s 2>&1 | FileCheck %s
# CHECK-NOT: error: unknown target triple
```

**`tests/lit/MC/Dadao/lit.cfg.py`**：最小 lit 配置，指向已 build 的 `llvm-mc`。

---

## 约束

1. **不实现任何指令**：本任务不写 `DADAOInstrInfo`、`DADAORegisterInfo`、或任何 `.td` 文件；这些属于 DL-008a/009a/010a
2. **patch 必须干净 apply**：`git am` 应用到 `.work/llvm/` 后 `ninja llvm-mc` 成功
3. **不改 musl/linux/qemu 组件**
4. **e_machine 值固定为 `0x0DA0`**（per `contracts/elf/spec.md §1.3`，不使用硬编码数字，用命名常量）
5. **ELF 大端**：AsmInfo 中 `IsLittleEndian = false`（per `contracts/elf/spec.md §1.2`）
6. **triple string 精确**：注册名必须为 `"dadao"`，full triple = `"dadao-unknown-elf"`
7. **`make prepare` 先运行**：任务文件中明确说明 DS 须先 `make prepare` fetch 源码再 build

---

## 验收步骤（DS 在完成区写出以下输出）

```
make prepare           →  llvm + qemu fetched, patches applied
make build-mc          →  cmake configure + ninja llvm-mc: PASS
llvm-mc --version      →  包含 "DADAO" 在支持目标列表（或不报 unknown target）
lit tests/lit/MC/Dadao/triple-smoke.s  →  PASS（或 FileCheck 无 error）
```

---

## 参考指针

| 资源 | 用途 |
|------|------|
| `llvm/lib/Target/Lanai/` | 最简单的完整 LLVM target 骨架参考 |
| `llvm/lib/Target/RISCV/` | 大型 target 可查 MCTargetDesc 结构 |
| `contracts/elf/spec.md §1` | `e_machine`、EI_DATA（大端）、`e_flags` 值 |
| `manifests/components.lock.toml` | LLVM 22.1.8 commit SHA（fetch 用） |
| `scripts/fetch.py` | make prepare 实现细节 |
| `code-agent/designs/0002-detailed-roadmap.md` §Phase 2 | Phase 2 exit gates 和后续任务分工 |

---

## 完成区

<!-- DS 在此填写 -->
