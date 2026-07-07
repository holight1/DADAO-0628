# Wiki 团队 Review 交接包（验证链导出）

**日期**：2026-07-07
**来源**：ADR-0009 验证链 M1（ISA）+ C1（ABI）审计的机械导出结果
**给谁**：DADAO wiki（SimRISC）维护团队

---

## 这份文件是什么

DADAO-0628 的 `contracts/{isa,abi}/spec.md` 是对 wiki（SimRISC 0.4.1，commit `13a414d`）的人工翻译。验证链（`check_wiki_refs`）已机械保证：**spec 中每条规范断言，要么有 `[wiki §…]` 引用、要么显式标 `[spec-decision]`/`[OPEN]`**。因此本 review 的范围**不是"读整个 spec"**，而是下面这份**有界、机械导出的清单**——spec 断言里 wiki 未背书的部分。请对每项做：**定义 / 确认 / 否决**。

**射程诚实说明**：审计只保证引用"解析到真实 wiki 章节"，**不保证 wiki 章节真说了 spec 声称的内容**（散文所限）。故除下面 A/B 外，另有 C（引用语义抽查）需人工。

---

## A. 需 wiki **定义**（spec 断言 / 后端已依赖，但 wiki 沉默）— M1 相关

| 项 | spec 位置 | 现状 | 请 wiki 团队 |
|----|----------|------|-------------|
| **整数除零 / `divs INT64_MIN÷-1` → ILLI** | isa §3.7（L483/484） | spec 断言 ILLI，但 wiki `§乘除操作` 只定义除法操作数布局、**未定义除零 fault**（DADAO-11-AEE 的 DZ 位仅浮点）| 确认整数除零/溢出的 fault 语义，或补入 wiki |
| **rd1 (rderrno) callee-saved** | abi §1.1 `[OPEN]` | wiki 未定义 rd1 是否 callee-saved；后端已选 **reserved（非分配）** | 定义 rd1 的 callee-saved 归属 |
| **rb3 / rb4 callee-saved** | abi §1.2 `[OPEN]` | 同上，后端已选 reserved | 定义 rb3/rb4 归属 |
| **C-27 条件赋值 overlap 快照**（csn/csz/csp/cseq/csne，src=dst） | isa（C-27） | wiki：非重叠行为确定，**重叠 OPEN**；阻塞 overlap 测试向量 | 定义 src=dst 重叠时的快照语义 |

## B. 需 wiki **确认** spec 的自主决策（wiki 沉默，spec 已按 ADR 定）— M1 相关

| 项 | spec 位置 | spec 决策（依据） | 请 wiki 团队 |
|----|----------|------------------|-------------|
| **SBZ 非零 → ILLI** | isa §（L118/223/1149） | wiki 定义 SBZ 字段但未定 fault 类型；spec 选 ILLI（ADR-0004 D5） | 确认或改判 fault 类型 |
| **算术无溢出检测**（软件自查） | isa（L461） | ADR-0004 | 确认 |

## C. 引用语义抽查（审计只证"解析到"，未证"wiki 真这么说"）

- ISA：103 处 `[wiki §…]` 引用全 RESOLVED；ABI：10 处全 RESOLVED。
- 建议 wiki 团队**抽样**核对：spec 的断言与所引 wiki 章节内容是否一致（尤其高风险：RB 48-bit 规则、RAS push/pop 方向、精确异常约定、对齐/red zone）。
- 引用索引：`grep -o "\[wiki §[^]]*\]" contracts/{isa,abi}/spec.md`。

## D. 延后（post-M1 / 系统域，本轮不阻塞，仅告知）

`issues.yaml` 中 open：Varargs、Multiple-returns（mixed-bank 顺序）、TLB-fault-retry、PTW-SBI-ABI、VA2PA-result、Cross-cfx-escape、Hardware-reset。这些属 system/advanced 域，M1 不触及，待相应阶段再交 wiki。

---

## 不在本包内（非 wiki 问题）

- **DataLayout `S128`(16B) vs ABI §4.2 `S64`(8B)**：这是 **DADAO 后端 bug**（后端栈对齐比 ABI 严），由 CodeGen spike 修（S128→S64），与 wiki 无关。

---

## 溯源

- 审计工具：`scripts/check_wiki_refs.py`（`--profile isa|abi`）、`scripts/check_codegen_abi.py`
- 登记：`docs/issues.yaml`、`docs/open-spec-issues.md`
- 决策依据：`docs/adr/0004-test-machine.md`（SBZ）、`docs/adr/0007-testing-methodology.md`
- 相关任务：DL-039a/b/c（ISA 审计）、DL-040a/b/c（ABI 审计 + CodeGen 一致性）
