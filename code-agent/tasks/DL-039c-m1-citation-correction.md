# DL-039c: M1 收口修正（架构师执行）

**执行环境**: 架构师直接执行（非下发）

**状态**: 已完成

**前置**: DL-039b（M1 backlog 收口）Review — 核心 Accepted，暴露两处收尾

---

## 背景

DL-039b Review（架构师亲自复跑）确认核心达标（DANGLING=0、uncited=0、零规则改动、已并入 make check），但残留 15 条 UNPARSEABLE，拆解出两类需收尾：

1. **架构师映射错**：DL-039b 任务里架构师给的引用用了**描述性标题**（`§多寄存器约束`/`§双目的寄存器规则`/`§除法语义`），非 wiki 真实 heading → 10 条 UNPARSEABLE。责任在架构师，故直接修。
2. **M1 真发现**：整数除零/`divs INT64_MIN÷-1` → ILLI（spec §3.7）**wiki 未定义**（wiki `§乘除操作` 无此规则；DADAO-11-AEE 的 DZ 位仅浮点状态）。worker 违反"无出处回架构师"约束、糊了假引用 `§除法语义`。属真 spec-wiki 缺口。

---

## 执行内容

### 1. 修正 10 条引用到真 heading（`contracts/isa/spec.md`，仅改引用目标）

| spec 行 | 归属指令 | 改为 |
|--------|---------|------|
| 156, 214, 215, 410, 427 | 立即数/RD 多寄存器 load/store | `[wiki §SimRISC-01 §存取RD寄存器]` |
| 769 | RB Block Copy | `[wiki §SimRISC-01 §寄存器组之间块赋值]` |
| 698 | RB Multi Load/Store | `[wiki §SimRISC-02 §存取RB寄存器]` |
| 197, 198, 448 | 双目的（add/sub 等） | `[wiki §SimRISC-01 §加减操作]` |

### 2. 除零 → spec-decision + 升级

- `spec.md` L483/L484：`§除法语义` → `[spec-decision: … wiki 未定义 …见 open-spec-issues]`
- `docs/issues.yaml`：新增 `IntDiv-fault`（status: open, blocks: null）
- `docs/open-spec-issues.md`：表内新增一行（M1 spec-fidelity，待 wiki 团队确认）

### 3. reviewer.md 补一条

- §不许凑绿 下：**"警告不等于合格，规避要打回"**——worker 被要求"无出处回架构师"却改用 UNPARSEABLE 引用绕过 = Needs Revision。

---

## 验证（架构师实机）

```
$ python3 scripts/check_wiki_refs.py  → Summary:
  Check 1 DANGLING:    0
  Check 1 UNPARSEABLE: 3 (warnings)   # 仅剩 spec.md 旧引用 L172/L235（非本轮，legacy）
  Check 2 missing ref: 0
  OVERALL: PASS   exit=0
```

UNPARSEABLE 15 → 3（3 条为 DL-039a 前既存的旧复合引用，标记为 known-legacy，后续单独清理）。

---

## 遗留

- **IntDiv-fault**：wiki 团队确认整数除零/溢出 fault 语义（open-spec-issues 已记）。
- **L172/L235 legacy 引用**：spec.md 原有复合/散文引用，UNPARSEABLE 警告，后续改写为可解析形态。

---

## 备注（过程）

- 本任务为架构师直接执行（修正自身映射错误 + 契约引用更正 + 缺口升级），按执行边界属"漏改引用/错误更正"范畴，留此记录以备追溯。
- worker 侧问题（糊假引用规避升级）已通过 reviewer.md 补条覆盖。
