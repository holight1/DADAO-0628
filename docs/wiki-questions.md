# Wiki 待确认问题清单

来源：`contracts/isa/spec.md §Appendix C`
版本：spec.md 0.4.0（2026-06-29，基于 Wiki `13a414d`）
状态：绝大多数问题已由 Wiki 0.4.1 解决；C-14 已由架构决策关闭；3 项仍需 Wiki 确认。

---

## 仍待确认

### 1. ~~rd2ra/ra2rd M1 Scope（C-14）~~ → **已关闭（架构决策 2026-06-29）**

Excluded：M1 scope 决策；ISA 语义清楚（SimRISC-02 §RA↔RD）但非变参标量 ABI 所需。
见 Scope Matrix 和 `docs/open-spec-issues.md`。

### 2. 条件赋值重叠 snapshot（C-27）

spec.md §3.12 断言：csn/csz/csp/cseq/csne 在 src/dst 重叠时所有源寄存器先读后写。
**Wiki 来源未找到**；现有 Wiki C-12（SimRISC-01 L203）仅明确 muls/mulu/divs/divu 的 snapshot，不覆盖条件赋值。

需确认：SimRISC-01 是否对 rrrr-format 条件赋值有同等 snapshot 规定。
阻断：条件赋值 src=dst 重叠测试向量无法定论。

### 3. SBZ 字段非零 fault 类型

spec.md §2.6.4 未确定 non-zero SBZ 触发 ILLI 还是 UNDI。
需确认：Wiki 是否在任何地方声明 SBZ 的 fault 类型。
阻断：QEMU 诊断模式 SBZ 处理。

### 4. 硬件复位初值（C-18）

Wiki 已明确：
- `rb0` 复位初值 = `cfx_power_hypv_excp_vector`（SEE §2.1）
- `rb0[63:48]` 恒为 0
- RA process-entry 初始化 = 全零
- RB 高 16 位初值 = 全 0

未明确：
- RD `rd1`–`rd63` 硬件复位值
- RB `rb1`–`rb63` 硬件复位值
- RA `ra0`–`ra63` 硬件复位值（process-entry 初始化 ≠ 硬件复位）
- RF `rf1`–`rf63` 硬件复位值（如 M1 需要）

---

## 附：已确认（Wiki 0.4.1 / commit 13a414d 已明确）

| 编号 | 事项 | Wiki 来源 |
|------|------|----------|
| C-01 | 指令大端序 | SimRISC-00 §指令设计 L15 |
| C-02 | 保留编码 → UNDI 异常 | SimRISC-00 §SimRISC QFC 表头注 |
| C-03 | RB 高 16 位分类规则表 | SimRISC-02 L7–L21 |
| C-04 | 存取类 RB → 全 64 位覆盖写 | SimRISC-02 L13 |
| C-05 | 算术类 RB → 低 48 位，高 16 位不变 | SimRISC-02 L16 |
| C-06 | 控制流 PC 48 位，rb0[63:48]=0 | SimRISC-02 L168 |
| C-07 | RASOF/RASUF 精确异常，RA 不提交 | DADAO-11-AEE L183 |
| C-08 | 除零 → ILLI | SimRISC-01 L199 |
| C-09 | divs truncate-toward-zero，remainder = dividend 符号 | SimRISC-01 L200 |
| C-10 | INT64_MIN ÷ -1 → ILLI | SimRISC-01 L201 |
| C-11 | fault 时 rdha/rdhb 无写入 | SimRISC-01 L202 |
| C-12 | 操作数重叠 → source snapshot | SimRISC-01 L203 |
| C-13 | RA process-entry 全零初始化 | DADAO-11-AEE L185 |
| C-15 | swym 除 PC 外无架构副作用 | SimRISC-04 L30 |
| C-16 | 多寄存器超界 → ILLI（不环绕） | SimRISC-01 L65 |
| C-17 | immu6=0 → ILLI | SimRISC-01 L64 |
| C-19 | 有效地址 = 低 48 位 mod 2^48 | SimRISC-02 L7 |
| C-20 | rb0[63:48] 恒为 0 | DADAO-11-AEE §基址寄存器 |
| C-21 | rela 高 16 位保持不变 | SimRISC-02 L161 |
| C-23 | PC[1:0]≠00 → IALIGN | SimRISC-00 L13 |
| C-24 | MALIGN 精确异常（SEE 确认所有同步异常精确） | SEE §2.4 |
| C-25 | rd0 为目的触发 ILLI（双目的有例外） | SimRISC-01 L7 |
| C-26 | 双目标同一非 rd0 → ILLI | SimRISC-01 L147 |
