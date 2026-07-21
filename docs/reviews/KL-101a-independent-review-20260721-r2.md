# KL-101a 独立 review r2（2026-07-21）

## 结论

**Accepted**。对照上一轮 review、`contracts/isa/spec.md` 以及 SEE/HBI 引用，上一轮提出的三项阻断问题均已解决；未发现新的阻断问题。

## 核对证据

1. **O2/O3 标签已补齐。** 修订报告 §3.3 和 §3.4 分别将 O2、O3 标为 `[推断/验收草案]`，并保留“当前不能通过/不是 O3”的实现状态；没有把验收预期写成当前观测结果（`kernel-hypv-supv-handoff-20260721.md:105-122`）。

2. **QEMU 的 CFXTRAP 表述已准确。** 修订报告明确写为有 host-side `EXCP_CFXTRAP` dispatch / `cfx_smon` shortcut，但无 SEE 级 cfx 路由、权限检查、现场保存、模式切换、guest 异常向量和 `escape` 移交（`:46-54`）。源码相符：`helper.c:99-108` 设置 `EXCP_CFXTRAP` 并退出 CPU loop；`cpu.c:124-205` 在 host 侧直接处理 `cfxcode==2` 的 syscall。修订稿同时将 patch series 引用收窄为 `:14-18`，与实际 18 个条目一致（`components/qemu/patches/series:14-19`）。

3. **early escape 已降级为语义待冻结的附加负例。** O2 现在先采用有直接 SEE 依据的未授权/被 mask 的 `cfx2rc/trap` 负例；early escape 被明确标为“语义待冻结的附加负例”，并说明 SEE escape 流程没有证明缺失 `excp_prev_*`/`cause_ip` 时必然产生 ILLI（`:107-115`）。这与 SEE 异常进入的 mask/ILLI 规则（`DADAO-12-SEE-主管系统运行环境.md:678-706`）和 escape 伪代码（`:813-844`）一致。

## 其他引用交叉核对

- HBI 启动初态及 hypv→supv 最小顺序与 HBI §3（`DADAO-23-HBI-超管系统二进制接口.md:21-64`）一致。
- `contracts/isa/spec.md` 对 `rb0` reset vector、C-18 未决项及 M1 排除的 system cfx 指令（`:50-52, 947-957, 1146-1150`）的边界表述未被修订稿混淆。
- M1 测试机 `0x00100000` 入口与 SEE/HBI reset vector 的区别有 ADR-0004 依据（`docs/adr/0004-test-machine.md:58-69`）。

本轮仅做只读复核；未访问 `~/toolchain` 或 `~/knowledge-graph`，未修改原报告及其他既有文件。
