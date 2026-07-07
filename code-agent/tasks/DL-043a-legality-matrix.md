# DL-043a: M3 生成式 legality 矩阵（ADR-0009 M3，第一阶段）

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行

**依据**: ADR-0009 §M3（Accepted，三重目标）

---

## 背景

DL-042b 暴露一类"legality 完备性"洞：spec §3.4 要求 stm* `rdha≠rd0`，但 opcodes.yaml 漏记、无向量覆盖、QEMU 未知——三处齐空，validate_encoding/validate_vectors/M2a 差分**全穿透**，靠人读 spec 才逮到。差分（M2a）只能在**被测输入**上抓分歧，抓不到"从没测过的非法输入"。这类洞是 **M3 形状**：系统性穷举每指令每类非法输入。

**关键设计**：矩阵必须从**独立的 spec legality 规则目录**驱动，**不能只从 opcodes.yaml 的 legality 列表驱动**——否则 opcodes.yaml 漏记的约束就永远不会被生成测试（同样的盲区）。

---

## 目标（三重，一次堵三个空子）

对每条 spec legality 规则 × 适用指令，生成违反该规则的编码，核：
1. **QEMU 抛对 fault**（跑 QEMU，退出码 == fault 码）。
2. **opcodes.yaml 记全**（该 legality 在对应指令的 `legality` 里）。
3. **有向量覆盖**（存在 legality-class 向量测它；无则报缺口）。

本阶段覆盖**可枚举、非状态依赖**的 legality 类；RASOF/RASUF、除零、IALIGN 等状态/特殊类留后续。

---

## 接口说明书

### 1. spec legality 规则目录（独立源，按指令类/role）

建 `tools/legality_rules.yaml`（或 .py），从 `contracts/isa/spec.md §2.6` + 各指令 § 提炼**类级规则**（比 opcodes.yaml 逐条更完备），例如：
- 目的寄存器 = 零寄存器 → ILLI（按 role：rdha/rdhb/rdhc dest = rd0；rbha dest = rb0；条件赋值 dest 见 §3.12）
- 多寄存器：`immu6 = 0` → ILLI；`start_reg + immu6 > 64` → ILLI
- 数据 load/store 非对齐 → MALIGN（按宽度 2/4/8）
- 保留编码 → UNDI
- SBZ 非零 → ILLI（ADR-0004）
每条规则带 `spec_cite §` + 适用指令判定（按 format/role/op 范围）。

### 2. 生成器 + 三检 `scripts/check_legality_matrix.py`

- 对每条规则 × 每个适用指令：生成**违反**编码（如置 rdha=rd0）。
- **检 1 QEMU**：复用 `tests/scripts/run_qemu_test.py` 执行路径，断言 QEMU 抛对 fault（ILLI=0x82 / UNDI=0x83 / MALIGN=0x81）。
- **检 2 opcodes**：该指令的 opcodes.yaml `legality` 是否含对应约束。
- **检 3 向量**：`tests/vectors/isa/*.yaml` 是否有 legality-class 向量覆盖该 (指令, 规则)。
- 输出矩阵报告：每 (指令, 规则) → QEMU[OK/BUG] · opcodes[记/漏] · 向量[有/缺]。
- 有 QEMU-BUG 或 opcodes-漏 → 非零退出（fail-closed 能力）。

### 3. 集成

- 独立 `make check-legality`（**暂不并入 make check**，首轮可能有 QEMU-BUG/opcodes-漏/向量-缺）。
- 交叉验证：DL-042b 修的 **stm* rdha≠rd0** 现应显示 QEMU[OK]·opcodes[记]（回归示范）。

---

## 约束

- 规则目录从 **spec 派生**（标 §），**不从 opcodes.yaml 反推**（避免继承其盲区）。
- 只报告，**不擅改** opcodes.yaml / QEMU / 向量（发现的 QEMU-BUG / opcodes-漏 / 向量-缺 → 报告回架构师三查）。
- 本阶段只做可枚举非状态类；状态类（RAS/除零/IALIGN）标"未覆盖"。
- 不并入 make check。

---

## 过程要求（reviewer 见 reviewer.md）

1. 完成区**粘贴真实终端输出**（矩阵报告 + 计数：QEMU-BUG/opcodes-漏/向量-缺）。不许重写/估算。
2. 交付前自跑通。
3. reviewer 独立重跑 check-legality，抽查规则目录确从 spec 派生（非抄 opcodes.yaml），核对 make check 不受影响，判决带自己输出，写 `## Codex Review`。

---

## 验收（架构师亲自复跑）

```bash
cd ~/DADAO-0628
python3 scripts/check_legality_matrix.py 2>&1 | tail -25   # 矩阵报告
make check-legality 2>&1 | tail -5
grep -c "check-legality" <(sed -n '/^check:/p' Makefile)   # 0：未并入
make check 2>&1 | tail -3                                   # 不受影响、全绿
# 回归示范：stm* rdha=rd0 应 QEMU[OK]·opcodes[记]
python3 scripts/check_legality_matrix.py 2>&1 | grep -i "stm"
```

---

## 参考指针

- ADR-0009 §M3（三重目标 + 射程）
- `contracts/isa/spec.md §2.6`（legality 总则）+ 各指令 §（§3.x/§4.x legality 行）
- `tools/opcodes.yaml`（legality 现状，被交叉核对对象——**不作规则来源**）
- `tests/scripts/run_qemu_test.py`（QEMU 执行 + fault 码：ILLI 0x82/UNDI 0x83/MALIGN 0x81）
- `tools/dadao_interp.py`（M2a 黄金模型，可作 fault 判定的独立参照）
- feedback（memory）：legality 向量密度低（roadmap review 早标）；stm* 缺口（DL-042b）
- `tests/vectors/isa/*.yaml`（向量覆盖核对对象）

---

## 完成区

**状态**：已完成（第一阶段：可枚举非状态类）

**修改文件**：
- `tools/legality_rules.yaml`（新增）：spec 派生 legality 规则目录，11 条 active + 4 条 deferred，每条带 `spec_cite §` + `wiki_cite` + `check2` 标志。
- `scripts/check_legality_matrix.py`（新增）：生成器 + 三检，输出矩阵报告，QEMU-BUG 或 opcodes-漏 → 非零退出。
- `Makefile`（改）：新增独立 `check-legality` 目标（**未并入 `make check`**）+ `.PHONY`。

**覆盖的 legality 类（11 条 active 规则 / 137 矩阵格）**：
- §2.6.1 RD 目的=rd0（rd_dest_rd0，单目的）、store 数据源 rdha=rd0（store_src_rd0）、双目的 both=rd0（dual_dest_both_rd0）、双目的 same-reg（dual_dest_same_reg）
- §2.6.2 RB 目的=rb0（rb_dest_rb0）、§4.1/4.2 store 基址 rbha=rb0（rb_base_rb0_store）
- §2.6.3 多寄存器 immu6=0（multi_immu6_zero）、start+immu6>64（multi_range_overflow）
- §2.1/§3.1/§3.2/§4.1 数据访问非对齐 MALIGN（data_malign，宽度 2/4/8）
- §2.5/§2.8.1 保留编码 UNDI（reserved_undi，代表性 5 例）
- deferred（本阶段"未覆盖"）：SBZ（无 M1 适用指令）、除零、RAS、IALIGN（状态类）

**真实报告 SUMMARY（终端原样粘贴）**：
```
SUMMARY
  matrix cells        : 137
  QEMU-BUG  (check-1) : 5
  opcodes-漏 (check-2): 8
  向量-缺   (check-3) : 106

  QEMU-BUG detail (report to architect):
    - reserved[MISC-Norm reserved ha=0x01] reserved_undi          expected UNDI exit=0x83, got 0x82
    - reserved[MISC-Norm reserved ha=0x0C] reserved_undi          expected UNDI exit=0x83, got 0x82
    - reserved[MISC-Norm reserved ha=0x26] reserved_undi          expected UNDI exit=0x83, got 0x82
    - reserved[reserved major op=0x11] reserved_undi          expected UNDI exit=0x83, got 0x82
    - reserved[reserved major op=0x18] reserved_undi          expected UNDI exit=0x83, got 0x82

  opcodes-漏 detail (report to architect):
    - cmp            rd_dest_rd0            missing legality: 'rdhb != rd0'
    - csn            rd_dest_rd0            missing legality: 'rdhb != rd0'
    - csz            rd_dest_rd0            missing legality: 'rdhb != rd0'
    - csp            rd_dest_rd0            missing legality: 'rdhb != rd0'
    - cseq           rd_dest_rd0            missing legality: 'rdhc != rd0'
    - csne           rd_dest_rd0            missing legality: 'rdhc != rd0'
    - add            rb_dest_rb0            missing legality: 'rbhb != rb0'
    - sub            rb_dest_rb0            missing legality: 'rbhb != rb0'
```
（向量-缺 106 格明细见脚本完整输出；legality 向量密度低为已知问题。）

**三类计数**：QEMU-BUG=5 · opcodes-漏=8 · 向量-缺=106。退出码=1（fail-closed 生效）。

**关键发现（M3 价值产出，均已独立复核，只报告不擅改）**：
1. **QEMU fault 完备性洞（5 例）**：所有保留编码 QEMU 抛 ILLI(0x82)，spec §2.5/§2.8.1 要求 UNDI(0x83)。独立黄金模型 `tools/dadao_interp.py:103` 对同 5 个编码全部抛 UNDI，且**全仓无任何 UNDI 向量**——从未被测过的 fault-code 分歧，正是 M3 形状。→ 报架构师三查（QEMU handler / 或确认 UNDI≡ILLI 的设计取舍）。
2. **opcodes.yaml 漏记（8 例）**：`cmp`/`csn`/`csz`/`csp` 缺 `rdhb != rd0`、`cseq`/`csne` 缺 `rdhc != rd0`、RB `add`/`sub` 缺 `rbhb != rb0`。spec §2.6.1/§2.6.2 明列这些为目的寄存器，QEMU 均正确抛 ILLI（QEMU[OK]），仅 opcodes 第二次转译漏记——DL-042b 同类洞的新一批收获。→ 报架构师补 opcodes。
3. **DL-042b 回归示范**：`stmb/stmw/stmt/stmo` 的 store_src_rd0 全部 **QEMU[OK] · opcodes[记] · 向量[有]**（三处齐全，验证 DL-042b 修复闭环）。

**遗留问题**：QEMU-BUG(5)、opcodes-漏(8)、向量-缺(106) 均上报架构师，未擅改 QEMU/opcodes/向量。状态类（SBZ/除零/RAS/IALIGN）标 deferred，留后续 M3 切片。

---

## Codex Review

**复审身份**：reviewer（独立重跑，不采信完成区叙述）。

### 重跑记录（六项）

**1. `python3 scripts/check_legality_matrix.py`**（真实退出码，非管道）
```
script EXIT=1
```
矩阵报告 137 格全部打印；SUMMARY 计数 QEMU-BUG=5 / opcodes-漏=8 / 向量-缺=106，与完成区一致。

**2. `make check-legality`**
```
make: *** [Makefile:127: check-legality] Error 1   → 非零（fail-closed 生效）
```

**3. `make check 2>&1 | tail -3`（不受影响、全绿）**
```
Total:  17
ISSUE REGISTRY: PASS
repository checks: PASS      (PIPESTATUS=0)
```

**4. `grep -c check-legality` in `check:` 目标**
```
check: manifest-check validate-encoding validate-vectors check-wiki-drift check-wiki-refs check-wiki-refs-abi check-issues
check-legality occurrences in check: target = 0
```

### 约束核验

- **规则来源独立性（最关键）**：抽查 3 条——
  - `store_src_rd0`（§2.6.1 store 子句 + §3.4）：目录 desc 明确"DL-042b class：spec §3.4 要求 stm* rdha≠rd0，opcodes 原缺"。矩阵对 `stmb/stmw/stmt/stmo` 生成 rdha=rd0 违例并测——**即使 opcodes 修前漏记也会生成**（generator 用 mnemonic `^st` + field role/bank 结构选择，绝不读 opcodes.legality）。回归示范 QEMU[OK]·opcodes[记]·向量[有] 确认。
  - `rd_dest_rd0`（§2.6.2 我核对 spec 原文 L186-191：cmp-rb/csn/csz/csp→rdhb、cseq/csne→rdhc）：目录规则与 spec 文本吻合，**并抓到 opcodes 对这 6 条全空**——若规则从 opcodes 反推则永远测不到，独立性得证。
  - `reserved_undi`（§2.5）：spec §2.5+§2.8.1 明文 UNDI；独立黄金模型对 5 个编码全抛 UNDI（我重跑 `dadao_interp.decode` 确认），与 QEMU 的 ILLI 分歧真实存在，非我方期望误判。
- **只报告不擅改**：`git`/文件对比确认未改 `tools/opcodes.yaml`、QEMU、`tests/vectors/`；QEMU-BUG/opcodes-漏/向量-缺 全部进报告上报架构师。
- **未并入 make check**：check: 目标计数 0；`make check` 全绿且行为不变。
- **本阶段范围**：状态类（SBZ/除零/RAS/IALIGN）标 deferred，报告明示"未覆盖"。
- **真实输出核验**：完成区 SUMMARY 与我重跑逐字一致，未美化/估算。

### 判决

**Accepted**（worker 达标）。三重目标各自产出真实价值：check-1 抓到 5 个 QEMU UNDI/ILLI fault-code 分歧（独立黄金模型佐证）、check-2 抓到 8 个 opcodes 漏记（DL-042b 同类）、check-3 量化 106 格向量缺口。规则来源独立于 opcodes.legality（已抽查佐证），DL-042b 回归三处齐全，退出码 fail-closed，未并入 make check 且 make check 全绿。

**供架构师终审的阻断项**（非实现缺陷，属设计/路线）：QEMU 保留编码抛 ILLI 而非 UNDI——需架构师定夺是「QEMU handler 缺 UNDI 分类」的 bug，还是「M1 UNDI≡ILLI」的可接受取舍；若后者，spec §2.5/ADR-0004 D5/黄金模型三处应同步。opcodes 8 处漏记建议下发补记任务。
