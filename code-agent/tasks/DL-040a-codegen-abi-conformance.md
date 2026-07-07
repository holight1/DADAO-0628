# DL-040a: CodeGen 验证分支 — abi.yaml facts + 后端一致性检查（ADR-0009 C2+C3）

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行

**依据**: ADR-0009 §CodeGen/ABI 验证分支（Accepted）

---

## 背景

验证链目前只覆盖 **ISA 执行侧（QEMU）**：`spec → opcodes.yaml → 向量 → harness`。**CodeGen 侧断链**：`contracts/abi/spec.md → CallingConv.td / RegisterInfo.td / DataLayout → ∅`——没有任何 oracle 校验 LLVM 后端是否符合 ABI 契约。Phase 5 CodeGen spike 疑因建在这段未验地基上而难诊断（架构师手工比对发现 spike 的 CallingConv 恰与 ABI 一致，但**无任何东西验证过**）。

本任务补两个机制（C2/C3），给 spike 一个静态 oracle + 验证过的地基。

---

## 目标

1. **C2**：从 `contracts/abi/spec.md` 派生机器可读 `tools/abi.yaml`（参数/返回/callee-saved 寄存器、DataLayout、栈对齐、`[OPEN]` 项）。
2. **C3**：`scripts/check_codegen_abi.py` 机械比对 LLVM 后端与 `abi.yaml`，报告不一致。
3. 跑首轮报告：**当前 spike 后端是否符合 ABI 契约**（直接给 spike 诊断依据）。

---

## 接口说明书

### C2 — `tools/abi.yaml`（从 ABI 契约派生，勿臆造）

从 `contracts/abi/spec.md` 提取结构化事实（对应章节已在下方参考指针）：

- **整数参数寄存器**：rd16–rd31（§传参）
- **指针参数寄存器**：rb16–rb31
- **整数返回**：rd31（§返回值）；**指针返回**：rb31
- **callee-saved**：rd32–rd63、rb32–rb63
- **non-allocatable / reserved**：rd0(zero)、rd1`[OPEN]`、rd2–rd7(reserved)、rb0(PC)、rb1(sp)、rb2(fp)、rb3`[OPEN]`、rb4`[OPEN]`、rb5–rb7(reserved)
- **DataLayout**：从 ABI 推出应有的串（大端 LP64；栈对齐 = ABI 的"8 字节对齐"）
- **`[OPEN]` 项显式标注**：凡 ABI 契约标 `[OPEN]` 的（rd1/rb3/rb4 callee-saved 未定义等），yaml 里显式标 `status: open`，供 C3 区分"后端在 OPEN 项上做了选择"。

每条 fact 带 `abi_cite`（§章节）。**契约没写的不要编，标 open。**

### C3 — `scripts/check_codegen_abi.py`

比对 LLVM 后端与 `abi.yaml`：

- **CallingConv.td**（`.work/source/llvm/llvm/lib/Target/DADAO/DADAOCallingConv.td`）：`CC_DADAO` 参数寄存器序列 == abi.yaml 整数参数；`RetCC_DADAO` == abi.yaml 整数返回。
- **RegisterInfo**（`DADAORegisterInfo.cpp` getReservedRegs + `DADAORegisterInfo.td` allocatable order）：reserved/non-allocatable 集合 == abi.yaml。
- **DataLayout**（`TargetDataLayout.cpp` 的 `case Triple::dadao` 串）：== abi.yaml DataLayout。**特别报出 `S128`(16B 栈对齐) vs ABI"8 字节对齐"是否冲突。**
- **输出**：`MATCH` / `MISMATCH`（明细：项 + 后端值 + 契约值）/ `OPEN-COMMIT`（后端在 abi.yaml 标 open 的项上做了选择——警告非错误，但须可见）。
- 有 MISMATCH → 非零退出（fail-closed 能力）。
- **make 目标**：`make check-codegen-abi`（**独立，暂不并入 `make check`**——spike 后端是 WIP，其一致性可能未过；本任务目的是**暴露**，非阻塞）。

### 首轮报告

跑一次，报告当前 spike 后端 vs ABI 契约：哪些 MATCH、哪些 MISMATCH、哪些 OPEN-COMMIT。这份报告是 spike 的诊断输入。

---

## 约束

- **abi.yaml 只从 ABI 契约派生**，契约没定的标 `open`，不编造。
- C3 是**只读比对**，**不改 LLVM 后端**（后端问题另行处理）。
- **不并入 `make check`**（spike 后端 WIP）；仅独立 `make check-codegen-abi`。
- 不碰 QEMU、不碰已工作的 MC 层。

---

## 过程要求（reviewer 见 reviewer.md）

1. 完成区**粘贴 `make check-codegen-abi` 真实终端输出 + 首轮报告**，不许重写/估算。
2. 交付前自己跑通，退出码符合预期。
3. reviewer 须**独立重跑** check-codegen-abi，核对 abi.yaml 每条 fact 有 `abi_cite` 且未臆造 open 项，判决带自己的输出。**不写自评 Accepted 之外**——按 reviewer.md 写 `## Codex Review`。

---

## 验收（架构师亲自复跑）

```bash
cd ~/DADAO-0628
python3 scripts/check_codegen_abi.py 2>&1 | tail -30; echo "exit=$?"
make check-codegen-abi 2>&1 | tail -20      # 独立目标存在可跑
grep -c "check-codegen-abi" <(sed -n '/^check:/p' Makefile)   # 应为 0（未并入 check）
# abi.yaml 每条 fact 有 abi_cite：
python3 -c "import yaml,sys; d=yaml.safe_load(open('tools/abi.yaml')); print('facts:',len(d) if isinstance(d,list) else 'dict')"
make check 2>&1 | tail -3                     # make check 不受影响、仍全绿
```

---

## 参考指针

- ADR-0009 §CodeGen/ABI 验证分支（C1/C2/C3 定义 + 射程）
- `contracts/abi/spec.md`：§寄存器规范（rd/rb 角色表）、§传参（rd16–31/rb16–31）、§返回值（rd31/rb31）、`[OPEN]` 项（rd1、rb3/rb4）
- 后端文件：`DADAOCallingConv.td`、`DADAORegisterInfo.td/.cpp`、`TargetParser/TargetDataLayout.cpp`（`case Triple::dadao`）
- `scripts/check_wiki_refs.py`（同类审计工具风格参考）
- `tools/opcodes.yaml`（机器可读契约的先例，abi.yaml 类比它）

---

## 完成区

**状态**：已完成

**修改文件**：
- `tools/abi.yaml`（新增，C2）——从 `contracts/abi/spec.md` 派生的机器可读 ABI facts；每条带 `abi_cite`；`[OPEN]` 项（rd1、rb3、rb4）标 `status: open`，未臆造。
- `scripts/check_codegen_abi.py`（新增，C3）——只读比对 LLVM 后端与 abi.yaml。
- `Makefile`（改）——新增独立目标 `check-codegen-abi`（**未并入 `check`**）。
- 后端源码（`.work/source/llvm/...` DADAOCallingConv.td / DADAORegisterInfo.{td,cpp} / TargetDataLayout.cpp）**未改动**（只读解析）。

**验收结果**（真实终端输出）：

`python3 scripts/check_codegen_abi.py; echo exit=$?` → `exit=1`：

```
========================================================================
CodeGen/ABI conformance (C3) — backend vs tools/abi.yaml
========================================================================
[MISMATCH   ] DataLayout   STACK ALIGNMENT CONFLICT: backend S128 (= 16B) vs ABI S64 (= 8B, 'abi §4.2 (SP must be 8-byte aligned before call)'). The backend mandates a STRICTER stack alignment than the ABI requires.
[OPEN-COMMIT] Reserved     rd1 is [OPEN] in ABI; backend chose to RESERVE it [abi §1.1]
[OPEN-COMMIT] Reserved     rb3 is [OPEN] in ABI; backend chose to RESERVE it [abi §1.2]
[OPEN-COMMIT] Reserved     rb4 is [OPEN] in ABI; backend chose to RESERVE it [abi §1.2]
[MATCH      ] CallingConv  integer params rd16..rd31 [abi §2.1]
[MATCH      ] CallingConv  integer return rd31 [abi §3.1]
[MATCH      ] Reserved     rd0 reserved [abi §1.1]
[MATCH      ] Reserved     rd2 reserved [abi §1.1]
[MATCH      ] Reserved     rd3 reserved [abi §1.1]
[MATCH      ] Reserved     rd4 reserved [abi §1.1]
[MATCH      ] Reserved     rd5 reserved [abi §1.1]
[MATCH      ] Reserved     rd6 reserved [abi §1.1]
[MATCH      ] Reserved     rd7 reserved [abi §1.1]
[MATCH      ] Reserved     rb0 reserved [abi §1.2]
[MATCH      ] Reserved     rb1 reserved [abi §1.2]
[MATCH      ] Reserved     rb2 reserved [abi §1.2]
[MATCH      ] Reserved     rb5 reserved [abi §1.2]
[MATCH      ] Reserved     rb6 reserved [abi §1.2]
[MATCH      ] Reserved     rb7 reserved [abi §1.2]
[MATCH      ] Allocatable  GPRD_Allocatable=r8..63; non-allocatable rd0..rd7 agrees with getReservedRegs
[MATCH      ] Allocatable  GPRB_Allocatable=r8..63; non-allocatable rb0..rb7 agrees with getReservedRegs
[MATCH      ] DataLayout   endianness E (big-endian) [isa §2.1 (data big-endian; abi appendix cites wiki §数据表示)]
[MATCH      ] DataLayout   i64:64 (LP64) [abi §2.2 (long/long long are 64-bit)]
[MATCH      ] DataLayout   n64 native width [abi §2.2]
[INFO       ] CallingConv  pointer params rb16..rb31 / pointer return rb31 not implemented in spike (GPRD-only); contract defines them [abi §2.1]
[INFO       ] DataLayout   backend string  = E-m:e-i64:64-n64-S128
[INFO       ] DataLayout   contract string = E-m:e-i64:64-n64-S64 [abi §2.2 + §4.2, isa §2.1]
------------------------------------------------------------------------
MATCH=20  OPEN-COMMIT=3  INFO=3  MISMATCH=1
RESULT: FAIL (backend diverges from ABI contract on fixed fact(s))
exit=1
```

`make check-codegen-abi` → `Error 1`（fail-closed 生效，脚本非零退出被 make 传播）。
`grep -c check-codegen-abi <(sed -n '/^check:/p' Makefile)` → `0`（未并入 check）。
`make check … | tail` → `repository checks: PASS`（不受影响，仍全绿）。

**首轮一致性报告（spike 后端 vs ABI 契约）**：

| 面 | 结论 |
|----|------|
| CallingConv 整数参数 rd16–rd31 | **MATCH** |
| CallingConv 整数返回 rd31 | **MATCH** |
| Reserved 固定项（rd0, rd2–7, rb0, rb1, rb2, rb5–7） | **全 MATCH** |
| Allocatable order（GPRD/GPRB = r8..63）与 getReservedRegs 一致性 | **MATCH** |
| DataLayout 端序 E / i64:64 / n64 | **MATCH** |
| **DataLayout 栈对齐 S128(16B) vs ABI S64(8B)** | **MISMATCH** —— 后端强制的栈对齐比 ABI（§4.2 8 字节）更严；唯一硬失败项，导致非零退出 |
| rd1 / rb3 / rb4（ABI [OPEN]） | **OPEN-COMMIT** —— 后端在 ABI 未定的 callee-saved 项上选择「保留(reserved)」；警告非错误 |
| 指针 ABI（rb16–31 参数、rb31 返回） | **INFO** —— spike 为 GPRD-only，未实现；契约有定义 |

**遗留问题**：
1. **S128 vs 8B 冲突需架构师定夺**：后端 DataLayout 的 `S128` 要求 16 字节栈对齐，而 ABI §4.2 只要求 8 字节。二者不冲突「正确性」（16B 满足 8B），但后端多出了契约未要求的约束——若 ABI 意图即 8B，应把后端改为 `S64`；若确需 16B，应回写 ABI 契约。**本任务只暴露不修**（C3 只读）。
2. rd1/rb3/rb4 的 callee-saved 语义在 wiki 仍 `[OPEN]`；后端已事实上选择「reserved」。需在 ABI 契约定稿时确认该选择或改判。
3. 指针传参/返回、callee-saved 保存恢复在 spike 未实现（GPRD-only，frame lowering `llvm_unreachable`）——属 spike 已知射程，非本任务范围。

---

## Codex Review

Reviewer 独立重跑（不采信完成区，以下为我自己终端的真实输出/退出码）。

### 重跑记录

```
### R1  python3 scripts/check_codegen_abi.py ; echo $?      -> exit=1
### R2  make check-codegen-abi ; echo $?                    -> make_exit=2 (脚本 exit 1 经 make 传播为 2，fail-closed 生效)
### R3  sed -n '/^check:/p' Makefile | grep -c check-codegen-abi   -> 0  (未并入 check)
        check: manifest-check validate-encoding validate-vectors check-wiki-drift check-wiki-refs check-issues
### R4  abi.yaml 每条 fact 有 abi_cite                       -> facts-without-cite: NONE
        open reserved                                       -> ['rd1', 'rb3', 'rb4']  (与 ABI [OPEN] 一致，未臆造值)
### R5  git diff --name-only                                 -> Makefile(+ 无关既有改动); 新增 scripts/check_codegen_abi.py, tools/abi.yaml
        git diff 触及 Target/DADAO|TargetParser              -> NONE（.work 被 .gitignore，后端只读未改）
### R6  make check ; echo $?                                 -> check_exit=0（仍全绿：repository checks: PASS）
```

脚本首轮报告我自己重跑复现一致：`MATCH=20 OPEN-COMMIT=3 INFO=3 MISMATCH=1`，唯一 MISMATCH 为 DataLayout 栈对齐 `S128(16B)` vs ABI `S64(8B, §4.2)`；OPEN-COMMIT 为 rd1/rb3/rb4（后端在 ABI [OPEN] 项上选择 reserved）；CallingConv 整数参数 rd16–rd31 与返回 rd31 均 MATCH。完成区粘贴的输出与我实跑逐行一致，无美化/估算。

### 约束核验（逐条）

1. **abi.yaml 只从 ABI 契约派生、不臆造** —— 通过。对照 `contracts/abi/spec.md`：整数参数 rd16–31(§2.1)、返回 rd31/rb31(§3.1)、reserved 集合(§1.1/§1.2) 均可溯源；`[OPEN]` 三项 rd1/rb3/rb4 标 `status: open` 且未赋 callee-saved 值。端序 `E` 引 isa §2.1（ABI 附录明确引 wiki §数据表示），非编造。R4 证实无缺 cite 的 fact。
2. **C3 只读、不改 LLVM 后端** —— 通过。R5 证实 backend 文件零改动（`.work` gitignore，diff 无 Target/DADAO 或 TargetParser）。
3. **不并入 `make check`** —— 通过。R3=0；`check:` 依赖未含 `check-codegen-abi`；R6 `make check` 仍 PASS。
4. **不碰 QEMU / 已工作 MC 层** —— 通过。改动仅 `tools/abi.yaml`、`scripts/check_codegen_abi.py`、`Makefile`（纯新增 `.PHONY` + 独立目标，见 diff）。
5. **fail-closed（有 MISMATCH 非零退出）** —— 通过。R1 exit=1、R2 make 因错误退出，非「把冲突降级为警告绕过」。S128 冲突被实打实报为 MISMATCH 并触发非零退出，符合 reviewer.md 对「规避」的红线。
6. **首轮报告即诊断输入** —— 通过。S128 vs 8B 冲突被显式命名并高亮，正是本任务要暴露的地基缺陷。

### 判决

**Accepted** —— 验收命令块在我自己的重跑下全部符合预期（R1 exit=1、R2 make 失败、R3=0、R4 无缺 cite、R5 后端未改、R6 make check 绿），四条硬约束无违反。MISMATCH 的存在是本任务的预期产物（暴露 spike 地基问题），非交付缺陷。S128 vs 8B 冲突需架构师终审定夺（改后端 `S64` 或回写 ABI），C3 已正确「暴露不修」。
