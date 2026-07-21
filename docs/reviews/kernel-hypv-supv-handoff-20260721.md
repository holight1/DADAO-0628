# KL-101a：reset→hypv→supv 移交核对报告

**日期**：2026-07-21  
**范围**：本地只读调研；未修改 QEMU、gem5、LLVM、kernel、contracts 或 wiki，未运行测试。  
**证据标签**：`[正式契约]`=HBI/SEE 或仓库 contracts；`[已有实现]`=当前源码/patch；`[推断]`=据此给出的任务拆分或尚待架构确认的结论。

## 结论先行

当前双后端都没有实现真实的 reset→hypv→supv 移交。QEMU 已有 `trap cfx_smon` 的 host-side syscall responder；gem5 的对应 patch 也直接在 `TrapInst::execute()` 中读寄存器并调用 host/SE API。这些路径没有 `inner_run_mode`、`inner_cfx_mask`、`inner_cfx_code`、异常现场、`cfx2rc` 或 `escape`，不能证明特权移交。

此外，正式 HBI/SEE 与当前 M1 测试机入口存在明确边界：HBI/SEE 要求硬件复位先到 hypv 向量；ADR-0004 将测试机 reset PC 固定为 `0x00100000`，并明确偏离 SEE 向量。因此 KL-101a 的最小交付物应是先冻结/实现一个可观测的 hypv 桩，而不是把现有 `-kernel` 裸加载或 syscall 通过当作已完成移交。

## 1. 正式要求、状态和顺序

### 1.1 reset 初态

- `[正式契约]` SEE 定义四种模式：user=`00`、jail=`01`、supv=`10`、hypv=`11`（`DADAO-wiki/DADAO-12-SEE-主管系统运行环境.md:7-18`）。`inner_*` 是每 hart 的硬件内部状态；`inner_run_mode`、`inner_cfx_mask` 等用于异常路由和现场保存（同文件 `:44-52`）。
- `[正式契约]` HBI §3 规定复位后：`inner_run_mode=hypv`、`inner_cfx_code=cfx_power`、`inner_cfx_mask=全1`；所有 `global_cfx_mask=全1`；PC 跳到 `cfx_power_hypv_excp_vector`，初值 `0xffff_ffff_0000`（`DADAO-wiki/DADAO-23-HBI-超管系统二进制接口.md:21-27`）。SEE 的对应核内地址说明在 `DADAO-12-SEE...:60-73`。
- `[正式契约/仓库边界]` `contracts/isa/spec.md:50-51` 只冻结 `rb0` 的 SEE reset vector，完整硬件 reset 仍列为 C-18 open（`:79-80,1146-1150`）；`contracts/isa/spec.md:947-957` 将 `trap/escape/cfx2rd/cfx2rc/cfxld/cfxst` 列为 M1 excluded。`contracts/exception/README.md:4` 也明确完整 cfx routing/masking/nesting/escape deferred。
- `[已有仓库策略]` ADR-0004 `:58-61` 把测试机 reset PC 固定为 `0x00100000`，并声明这偏离 ISA/SEE 的 `cfx_power_hypv_excp_vector`；这是测试机入口约定，不是 HBI 真实 reset 语义。

### 1.2 hypv→supv 正式顺序

`DADAO-23-HBI-超管系统二进制接口.md:29-64` 给出的最小桩顺序是：

1. `setrd rd2,0`。
2. 依次对 umon、jmon、smon、ptw、tlb、cache、hart、llc、pmem、timer、uart、power 执行 `cfx2rc cfx_*_hypv_cg_reg_deleg, rd2`，清除 delegation；cg3（hypv）本身硬件忽略 bit3 写入（`:31-45`）。
3. 写 `cfx_power_excp_prev_run_mode=2`（supv，`:47-50`）。
4. 写 `cfx_power_excp_prev_cfx_mask=全1`（`:51-53`）。
5. 写 `cfx_power_excp_cause_ip=target_addr`，此时 PTBR 尚未开启，按物理地址解释（`:55-57`）。
6. 将设备树/硬件信息指针放入 `rb16`，无则为 0（`:59-60`）。
7. 执行 `escape cfx_power,0`（`:62-64`），由 SEE escape 语义恢复 `excp_prev_cfx_mask`、`excp_prev_run_mode`，并跳到 `cause_ip + 0`（`DADAO-12-SEE...:813-844`）。

SEE 的一般异常进入顺序是：确定目标 cfx → 检查不可屏蔽/inner mask/global mask/cause mask → 计数 → 保存 prev mode/mask → 切换 mode/mask/code → 保存 cause → 跳异常向量（`DADAO-12-SEE...:678-706`）。异常退出是 `escape`，恢复 mask、mode、计数和返回 PC（`:813-844`）。

**注意事项**：`escape` 伪代码没有显式写 `inner_cfx_code` 的恢复/更新；同时 HBI 样例把返回 mask 设为全 1，而 reset 的 global mask 也为全 1。故“移交后立即 `trap cfx_smon` 是否可达”不能凭直觉假定为可达，必须由 KL-102a 冻结 `inner_cfx_code` 生命周期及 mask/delegation 的可用配置；这是当前正式文字的待决语义，不是已有实现事实。

## 2. QEMU/gem5 实现核对

### QEMU

`[已有实现]` 当前 `.work/source/qemu` 的直接证据：

- `target/dadao/cpu.c:40-57` 的 `dadao_cpu_reset_hold()` 只清 RD/RB/RF/RA，设置 `env->pc=0x00100000` 和 exception index；没有 mode/cfx 内部状态，也没有 HBI 向量入口。
- `target/dadao/translate.c:452-464` 仅把 `trap` 翻译成 helper，并预先写入下一条 PC。
- `target/dadao/helper.c:99-108` 仅把 cfxcode/function 放入 `trap_*` scratch，设置 `EXCP_CFXTRAP` 后退出 CPU loop。
- `target/dadao/cpu.c:124-205` 的 `EXCP_CFXTRAP` 分支在 `cfxcode==2` 时直接读取 `rd16..rd19`，在 C 代码中处理 write/exit/brk/mmap 等 syscall；`:145-162` 直接写 host stdout/请求 host shutdown，`:173-205` 是 host backing 的 mmap 记账。
- `components/qemu/patches/series:14-18` 仍只显示现有 trap/syscall 及其配套
  的 PC、brk、mmap patch；未见 cfx2rc/cfx2rd/escape 或 hypv/supv 状态 patch。

因此 QEMU 的判定是：**有 host-side `EXCP_CFXTRAP` dispatch 和 cfx_smon
shortcut；无 SEE 级 cfx 路由、权限检查、现场保存、模式切换、guest 异常向量
和 escape 移交**。这里的“无真实移交”不是说没有 `EXCP_CFXTRAP` 路径，而是
说该路径没有实现 SEE 规定的 guest-side 特权状态机。

### gem5

`[已有实现]` 当前仓库 patch 的直接证据：

- `components/gem5/patches/0001-dadao-arch-skeleton.patch:6-16` 自述这是“minimal skeleton”，指令语义尚未完整实现，初始 syscall-emulation workload 可直接启动/退出。
- `components/gem5/patches/0010-dadao-trap-syscall.patch:19-43` 在 `src/arch/dadao/decoder.cc` 定义 `TrapInst`；`:24-40` 对 `cfxcode==2` 直接读 `RD_BASE+16..19`，执行 `std::cout`、`exitSimLoop`、host-side brk，并写回 `RD_BASE+31`；`:52` 只增加 opcode `0x76` 解码。
- `components/gem5/patches/series:11-12` 只列 trap-syscall 和 cfx_smon mmap patch；没有 `escape`、`cfx2rc/cfx2rd`、inner state 或 HBI handoff patch。当前 `.work/source/gem5` 也没有可由 `rg --files -uu .../src/arch/dadao` 找到的已应用 DADAO 源文件，故此处以仓库 patch 作为 gem5 实现证据。

因此 gem5 的判定是：**与 QEMU 同样只有 host/SE syscall shortcut，不实现真实移交**。两边的 syscall 输出/退出一致性不能替代特权状态一致性。

可复核的短命令（只读，不运行模拟器）：

```bash
rg -n -i 'inner_run_mode|inner_cfx|cfx2rc|cfx2rd|escape|cfx_smon|reset_hold|run_mode' \
  DADAO-0628/.work/source/qemu/target/dadao \
  DADAO-0628/components/gem5/patches \
  DADAO-0628/components/qemu/patches
rg --files -uu DADAO-0628/.work/source/gem5 | rg '(^|/)src/arch/dadao/'
```

## 3. 最小状态图与三个 oracle

### 3.1 状态图

```text
RESET
  mode=hypv, cfx=power, mask=ALL-1, PC=power_hypv_vector
       |
       | hypv stub: cfx2rc delegation ×12
       | set power.prev_mode=supv
       | set power.prev_mask=ALL-1
       | set power.cause_ip=entry; rb16=fdt/0
       v
HYPV_READY -- escape power,0 --> SUPV_ENTRY
                                  mode=supv, PC=entry
                                  (cfx/mask restoration per SEE §5)
       |
       | legal enabled operation: trap/cfx access
       v
SUPV_SERVICE -- escape current cfx,N --> SUPV_RETURN/continuation
```

### 3.2 Oracle O1：成功移交

`[推断的可执行测试]` 准备一个放在 HBI reset vector 可取指区域的 handoff stub 和一个物理 `supv_entry`：执行完整 12 个 delegation 写、prev mode/mask、cause IP、rb16，再 `escape cfx_power,0`；supv entry 写唯一 marker 并停止。

- 双后端预期：QEMU/gem5 都到同一 marker；可观测 trace 必须显示 reset `hypv → escape(power) → supv`，PC 为 `supv_entry`，而非仅显示进程退出或 host syscall 成功。
- 当前结果：两后端均应判为 **未实现/不能通过**；QEMU reset PC 已是 `0x00100000`，gem5 patch 没有这些指令/状态语义。

### 3.3 Oracle O2：非法顺序/权限（[推断/验收草案]）

构造一个有直接契约依据的负例：未清 delegation 就从 hypv 访问被 delegation
的 cg，或从 supv 对未授权/被 mask 的 cfx 执行 `cfx2rc/trap`。按 SEE §5，
非法/被 mask 的同步路径应进入当前 mode monitor 并产生 ILLI/相应异常，不得
跳到 supv marker。另将“在未建立 `power.excp_prev_*`/`cause_ip` 前执行
`escape cfx_power,0`”列为**语义待冻结的附加负例**：当前 SEE escape 文字
规定了恢复和跳转流程，但没有证明该前置状态缺失必然产生 ILLI，不能提前断言。

- 双后端预期：相同 fault class、相同 faulting PC、相同“未写 marker”；差异只允许在调试输出格式。
- 当前结果：两后端都没有 cfx 权限检查、异常向量或 escape，因此不能把现有 host exit 当作 O2 通过。

### 3.4 Oracle O3：移交后最小受控操作（[推断/验收草案]）

在 O1 的 `supv_entry` 中先按冻结后的 mask/delegation 规则使 `cfx_smon` 可达，再执行 `trap cfx_smon,0`，由 guest-side smon handler 做一个无副作用最小动作（例如读取固定 ABI 参数、写回 `rd31=0`、`escape cfx_smon,1` 返回），随后写 marker。禁止直接调用 QEMU/gem5 的 host syscall API。

- 双后端预期：均出现一次真实 `cfx_smon` trap、mode/inner cfx 状态切换、guest handler 返回，marker 和 `rd31` 相同。
- 当前结果：QEMU `cpu.c:130-162` 与 gem5 patch `0010:24-40` 会直接处理 syscall；它们可作为 legacy shortcut smoke test，但不是 O3。

## 4. KL-102a/103a 前置依赖与拆分

仓库当前没有独立的 `KL-102a`/`KL-103a` task 文件；以下是 `[推断]` 的最小下一步拆分：

### KL-102a：SEE cfx 状态/指令语义最小实现

前置：KL-101a 把 HBI 顺序、reset 入口与 O1/O2/O3 观测字段冻结；同时解决上文所述 `inner_cfx_code` 与返回 mask 的文字歧义。

范围：双后端共同建模 `inner_run_mode`、`inner_cfx_mask`、`inner_cfx_code`、`cfx_*_excp_prev_*`/cause；实现最小 `cfx2rc` delegation、权限/mask 检查、`escape` 恢复和 reset→hypv vector；先完成 O1/O2，不接完整 MMU/中断。

### KL-103a：真实移交后的最小 guest monitor 操作

前置：KL-102a O1/O2 在 QEMU+gem5 一致通过；明确 `cfx_smon` 的 supv trap mask、异常向量和 `escape cfx_smon` 返回约定。

范围：提供最小 guest-side `cfx_smon` handler 与 O3，验证 `trap→CFXTRAP→smon handler→escape` 的状态/PC/返回值；再把现有 QEMU/gem5 host-side syscall shortcut 标成兼容性路径或隔离掉，不能继续把它计入真实 handoff gate。

**最终判定**：KL-101a 当前结论为“契约已规定最小移交序列，QEMU/gem5 均未实现；现有 syscall 通过是 host-side shortcut”。KL-102a 是状态机与权限/escape 基础，KL-103a 才是移交后的真实受控操作验证。
