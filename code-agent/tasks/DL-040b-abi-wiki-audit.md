# DL-040b: ABI wiki→spec 审计（ADR-0009 C1）

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行

**依据**: ADR-0009 §CodeGen/ABI 验证分支 C1（Accepted）

---

## 背景

M1（DL-039a/b/c）把 wiki→spec 审计做在了 `contracts/isa/spec.md`，但 **CodeGen 全建在 `contracts/abi/spec.md` 上，而 ABI 契约从未过 wiki-ref 审计**。C1 = 把现成的 `scripts/check_wiki_refs.py` 扩到 ABI 契约，产出首轮 ABI 审计报告（供架构师三查，像当初 ISA 的 52 条那样）。

工具已存在（`scripts/check_wiki_refs.py`，DL-039a），本任务是**扩它 + 跑 ABI + 出报告**，不是重写。

---

## 目标

1. 扩 `check_wiki_refs.py` 使其能审计 `contracts/abi/spec.md`（引用有效性 + 无引用规范断言），**保持 ISA 审计与 make check 现状不变、仍全绿**。
2. 独立 `make check-wiki-refs-abi` 目标（**暂不并入 make check**——首轮必有 ABI backlog）。
3. 产出首轮 ABI 审计报告（DANGLING / UNPARSEABLE / 无引用断言 计数 + 无引用断言完整清单）。

---

## 接口说明书

### 扩 `scripts/check_wiki_refs.py`

- **参数化审计目标**：让脚本能对指定 spec 文件运行（默认仍 `contracts/isa/spec.md`，供 make check 的 `check-wiki-refs` 不变）；新增对 `contracts/abi/spec.md` 的审计入口。
- **两项检查同 ISA**：① `[wiki §…]` 引用有效性（三态 RESOLVED/DANGLING/UNPARSEABLE，沿用 DL-039b 的复合形态解析）；② 无引用规范断言（含 callee-saved/传参/返回/对齐/SBZ 等规范措辞，具体集合按 abi/spec.md 实际用词定）。
- **合法标记**：`[wiki §…]`、`[spec-decision: …]`、以及 ABI 契约里已有的 `[OPEN]` 标注——**`[OPEN]` 项视为"已显式声明未定"，不计入"无引用断言"**（它是已知开放，不是真空断言）。
- **make 目标**：`make check-wiki-refs-abi`（独立，**不并入 `check`**）。DANGLING 计违规（fail-closed），UNPARSEABLE 告警不阻塞（同 ISA）。

### 首轮报告

跑 `check-wiki-refs-abi`，整理：N 个 wiki 引用中 M 个 DANGLING/UNPARSEABLE（分类）；K 条无引用规范断言（**完整列出 file:line + 断言**，供架构师三查分桶：补引用 / 标 spec-decision / 标 OPEN / 交 wiki 团队）。

---

## 约束

- **不得改 `contracts/abi/spec.md` 正文凑绿**：不编造/删改引用、不删断言。**报告是交付物。** 补引用是下游三查后的独立动作。
- **不并入 `make check`**（仅独立目标）；ISA 侧 `check-wiki-refs` 与 make check 现状**保持全绿不回归**。
- 不碰 QEMU/LLVM/其它脚本。
- `[OPEN]` 标注的断言不计违规（已显式声明未定）。

---

## 过程要求（reviewer 见 reviewer.md）

1. 完成区**粘贴 `make check-wiki-refs-abi` 与 `make check` 的真实终端输出**（含退出码），不许重写/估算。
2. 交付前自己跑通；确认 ISA 侧不回归（`make check` 仍全绿）。
3. reviewer 按 reviewer.md **独立重跑** check-wiki-refs-abi 与 make check，核对未改 abi/spec.md 正文（`git diff`）、ISA 侧无回归，判决带自己输出，写 `## Codex Review`。

---

## 验收（架构师亲自复跑）

```bash
cd ~/DADAO-0628
make check-wiki-refs-abi 2>&1 | tail -25       # 首轮 ABI 报告
echo "exit=$?"
grep -c "check-wiki-refs-abi" <(sed -n '/^check:/p' Makefile)   # 0：未并入 check
python3 scripts/check_wiki_refs.py >/dev/null 2>&1; echo "ISA-side exit=$?（应 0，不回归）"
git diff contracts/abi/spec.md | grep -c "^+"  # 0：未改 ABI 正文
make check 2>&1 | tail -3                        # 仍全绿
```

---

## 参考指针

- ADR-0009 §CodeGen/ABI 验证分支 C1
- `scripts/check_wiki_refs.py`（DL-039a 产出，本任务扩展）；DL-039b 的三态解析 + 复合形态处理是先例
- `contracts/abi/spec.md`（被审计对象；已有 `[wiki §DADAO-21-ABI …]` 引用与 `[OPEN]` 标注）
- `manifests/spec.lock.toml`（`local_reference` = wiki 路径）
- DL-039a/b/c（ISA 侧同一流程的先例：工具→报告→架构师三查→补引用）

---

## 完成区

**状态**：已完成

**修改文件**：
- `scripts/check_wiki_refs.py`（参数化审计目标：新增 `--profile {isa,abi}`，默认 `isa`；ISA 路径行为字节级不变；新增 ABI 专属规范措辞集 `ABI_NORMATIVE_PATTERNS` 与合法标记集 `ABI_DECISION_MARKERS`=`[wiki §…]`（行级跳过）/`[spec-decision: …]`/`[OPEN`）。
- `Makefile`（新增独立目标 `check-wiki-refs-abi`，**未并入 `check`**；加入 `.PHONY`）。
- 本任务文件完成区。

**未改动**：`contracts/abi/spec.md` 正文（`git diff` 新增行 = 0），未碰 QEMU/LLVM/其它脚本。

### 真实终端输出

**① ISA 侧字节级无回归**（默认路径 = `contracts/isa/spec.md`，供 `make check`）：
```
$ python3 scripts/check_wiki_refs.py > isa_after.txt; echo $?
0
$ diff isa_baseline.txt isa_after.txt && echo "ISA OUTPUT BYTE-IDENTICAL"
ISA OUTPUT BYTE-IDENTICAL
```
（ISA：Total 106，RESOLVED 103，DANGLING 0，UNPARSEABLE 3，Check2 0，OVERALL PASS，exit 0。与扩展前逐字节一致。）

**② `make check-wiki-refs-abi`（首轮 ABI 审计，退出码）**：
```
$ make check-wiki-refs-abi ; echo "make exit=$?"
...（完整报告见下）...
  OVERALL: FAIL (44 hard errors)
make: *** [Makefile:77: check-wiki-refs-abi] Error 1
make exit=2         # make 将脚本 exit 1 包装为 make Error 2
$ python3 scripts/check_wiki_refs.py --profile abi >/dev/null 2>&1; echo "script-abi-exit=$?"
script-abi-exit=1   # 脚本本体 exit 1（fail-closed，backlog 非空）
```

**③ 未并入 `make check`**：
```
$ sed -n '/^check:/p' Makefile
check: manifest-check validate-encoding validate-vectors check-wiki-drift check-wiki-refs check-issues
$ sed -n '/^check:/p' Makefile | grep -c "check-wiki-refs-abi"
0
```

**④ `make check` 仍全绿**：
```
$ make check 2>&1 | tail -3
Total:  14
ISSUE REGISTRY: PASS
repository checks: PASS
$ make check >/dev/null 2>&1; echo "make check exit=$?"
make check exit=0
```

### 首轮 ABI 审计报告

**Check 1 — wiki 引用有效性（三态）**：Total **9**；RESOLVED **9**；DANGLING **0**；UNPARSEABLE **0**。
（ABI 契约的 9 处 `[wiki §…]` 引用全部解析到 `~/DADAO-wiki/DADAO-21-ABI-…md` 与 `DADAO-11-AEE-…md`，无悬空、无不可解析。）

**Check 2 — 无引用规范断言：共 44 条**（`[wiki §…]`/`[spec-decision: …]`/`[OPEN` 之外、含规范措辞的行；行级检测，与 ISA DL-039b 先例一致，故 §级引用/多行 `[OPEN]` 块的续行也会被逐行surface，交架构师三查分桶）：

| file:line | 断言原文 |
|-----------|---------|
| contracts/abi/spec.md:19  | `\| Register \| ABI Name \| Role \| Callee-saved? \|` |
| contracts/abi/spec.md:21  | `\| rd0      \| rdzero   \| Hardwired zero \| Immutable \|` |
| contracts/abi/spec.md:23  | `\| rd2–rd7  \| —        \| Reserved (compiler must not allocate) \| — \|` |
| contracts/abi/spec.md:28  | `**M1 allocatable set**: rd8–rd15 (caller-saved temporaries), rd16–rd31` |
| contracts/abi/spec.md:29  | `(argument/return), rd32–rd63 (callee-saved). Non-allocatable: rd0 (hardwired` |
| contracts/abi/spec.md:31  | `treats as non-allocatable]), rd2–rd7 (ABI-reserved).` |
| contracts/abi/spec.md:35  | `\| Register \| ABI Name \| Role \| Callee-saved? \|` |
| contracts/abi/spec.md:42  | `\| rb5–rb7  \| —        \| Reserved \| — \|` |
| contracts/abi/spec.md:47  | `**M1 allocatable set**: rb8–rb15 (caller-saved temporaries), rb16–rb31` |
| contracts/abi/spec.md:48  | `(argument/return), rb32–rb63 (callee-saved). Non-allocatable: rb0 (PC),` |
| contracts/abi/spec.md:56  | `completeness but must not be used by M1 BasicCodeGen.` |
| contracts/abi/spec.md:64  | `caller-saved/callee-saved framework:` |
| contracts/abi/spec.md:96  | `\| `char` (signed in the DADAO ABI), `signed char`, `short`, `int` \| sign-extend \|` |
| contracts/abi/spec.md:97  | `\| `unsigned char`, `unsigned short`, `unsigned int` \| zero-extend \|` |
| contracts/abi/spec.md:98  | `\| `_Bool` \| zero-extend (value is 0 or 1) \|` |
| contracts/abi/spec.md:99  | `\| `enum` (signed 32-bit in the DADAO ABI) \| sign-extend \|` |
| contracts/abi/spec.md:154 | `**Narrow return extension**: the callee must sign- or zero-extend the return` |
| contracts/abi/spec.md:175 | `in `docs/open-spec-issues.md` and must be resolved before M1 can implement` |
| contracts/abi/spec.md:185 | `- Callee writes the result through `rb16` and preserves `rb16` after return.` |
| contracts/abi/spec.md:198 | `(lowest valid address in the current frame). Grows downward.` |
| contracts/abi/spec.md:202 | `- **Red zone**: 128 bytes below SP are reserved (not modified by signal` |
| contracts/abi/spec.md:203 | `handlers). Leaf functions may use the red zone as their entire frame,` |
| contracts/abi/spec.md:208 | `- SP must be 8-byte aligned before `call`.` |
| contracts/abi/spec.md:209 | `- Stack arguments and saved registers are 8-byte aligned.` |
| contracts/abi/spec.md:210 | `- Aggregate alignment: minimum 8 bytes.` |
| contracts/abi/spec.md:221 | `\| callee-saved registers   \|` |
| contracts/abi/spec.md:225 | `\| red zone (128 B)         \|  ← rbsp - 128 (reserved)` |
| contracts/abi/spec.md:234 | `3. Callee saves callee-saved registers it will modify (rd32–rd63 and` |
| contracts/abi/spec.md:253 | `The caller must preserve any values live across the call in rd8–rd31 or` |
| contracts/abi/spec.md:254 | `rb8–rb31; these registers are caller-saved temporaries/argument registers.` |
| contracts/abi/spec.md:263 | `addi    rbsp, rbsp, -frame_size    ; allocate: frame_size = saved_regs + locals, 8B aligned` |
| contracts/abi/spec.md:264 | `; save callee-saved RD registers (rd32+) at rbsp + ...` |
| contracts/abi/spec.md:265 | `; save callee-saved RB registers (rb32+) at rbsp + ...` |
| contracts/abi/spec.md:274 | `addi    rbsp, rbsp, -frame_size    ; frame_size = 8(FP slot) + saved_regs + locals, 8B aligned` |
| contracts/abi/spec.md:275 | `; save callee-saved registers at rbfp - 8, rbfp - 16, ...` |
| contracts/abi/spec.md:280 | `Registers rd32+ and rb32+ that the callee modifies must be saved and restored.` |
| contracts/abi/spec.md:281 | `rbsp must be restored to `incoming_sp` on return (via symmetric frame` |
| contracts/abi/spec.md:288 | `; restore callee-saved RB registers (rb32+)` |
| contracts/abi/spec.md:289 | `; restore callee-saved RD registers (rd32+)` |
| contracts/abi/spec.md:298 | `; restore callee-saved RB registers (rb32+, NOT rb2 yet)` |
| contracts/abi/spec.md:299 | `; restore callee-saved RD registers (rd32+)` |
| contracts/abi/spec.md:318 | `\| Mixed-bank multi-return \| Excluded from M1; Wiki ordering conflict must be resolved before Advanced CodeGen \| `docs/op` |
| contracts/abi/spec.md:339 | `\| 4.1 \| SP/FP/red zone \| `DADAO-21-ABI §The Stack Frame` \|` |
| contracts/abi/spec.md:340 | `\| 4.2 \| Alignment \| `DADAO-21-ABI §数据表示 §Fundamental Types` \|` |

**架构师三查分桶提示**（非本任务动作，仅备注可能归类）：
- **补 `[wiki §…]`**：§1 寄存器表（19/21/23/35/42）、§2.2 扩展表（96–99）、§4.2 对齐（208–210）等有对应 wiki §级出处但断言行本身缺行级引用。
- **标 `[spec-decision: …]`**：154（返回值扩展，正文已有 `[M1 architecture decision:…]` 但该措辞不在合法标记白名单，需归一为 `[spec-decision:]`）、253/280（caller/callee 保存义务）。
- **已被 `[OPEN]` 覆盖（行级误报）**：175（在 172–176 的 `[OPEN]` 块续行内）、318（Open Issues 表内 Excluded 项）——架构师可判定为块级 OPEN 覆盖。
- **Appendix 引用表**：339/340 已在附录列出 wiki 出处（backtick 形式），非 `[wiki §…]` 标记语法，可判定为已引用。

**遗留问题**：无（首轮 backlog=44 条无引用断言即本任务产出，交架构师三查；不在本任务内补引用/改正文）。

---

## Codex Review

**审查者**：Codex（自我复审，reviewer.md 六项独立重跑）。判决基于我自己的命令输出，不采信完成区叙述。

### 重跑记录（真实输出/退出码）

**① `make check-wiki-refs-abi`（首轮必有 backlog）**
```
$ make check-wiki-refs-abi 2>&1 | tail -6
  Check 1 DANGLING:    0
  Check 1 UNPARSEABLE: 0 (warnings)
  Check 2 missing ref: 44

  OVERALL: FAIL (44 hard errors)
make: *** [Makefile:77: check-wiki-refs-abi] Error 1
$ make check-wiki-refs-abi >/dev/null 2>&1; echo $?
2                       # make 包装脚本 exit 1 → Error 2（非零，符合 fail-closed）
$ python3 scripts/check_wiki_refs.py --profile abi >/dev/null 2>&1; echo $?
1                       # 脚本本体 exit 1
```
核对：DANGLING=0、UNPARSEABLE=0、Check2=44，与完成区数字一致。首轮 backlog 非空、退出非零 → 符合任务预期（DANGLING 计违规，此处非零来自 Check2 的 44 条无引用断言；UNPARSEABLE 仅告警且本轮为 0）。

**② ISA 侧不回归（`python3 scripts/check_wiki_refs.py`，默认 profile）**
```
$ python3 scripts/check_wiki_refs.py >/dev/null 2>&1; echo $?
0
$ python3 scripts/check_wiki_refs.py 2>&1 | grep -E "Total|RESOLVED|DANGLING|UNPARSEABLE|OVERALL"
Total: 106
  RESOLVED:     103
  DANGLING:     0 (HARD ERROR)
  UNPARSEABLE:  3 (warning)
  ...
  OVERALL: PASS
```
exit 0，Total/RESOLVED/DANGLING/UNPARSEABLE 与 DL-039 基线一致 → **无回归**。（另经 `diff` 确认与扩展前逐字节相同，见完成区①。）

**③ 未改 ABI 正文**
```
$ git diff contracts/abi/spec.md | grep -c '^+'
0
$ git diff --stat contracts/abi/spec.md
(空)
```
ABI 正文 0 新增行 → 未编造/删改引用、未删断言，报告为交付物而非凑绿。

**④ 未并入 `make check`**
```
$ sed -n '/^check:/p' Makefile | grep -c "check-wiki-refs-abi"
0
```
`check:` 依赖列表不含 `check-wiki-refs-abi` → 独立目标。

**⑤ `make check` 仍全绿**
```
$ make check >/dev/null 2>&1; echo $?
0
```

**⑥ 改动范围**
```
$ git diff --name-only | grep -E "scripts/|Makefile|contracts/"
Makefile
scripts/check_wiki_refs.py
```
仅 `scripts/check_wiki_refs.py` + `Makefile`（+任务文件）。未碰 QEMU/LLVM/其它脚本/ABI 正文。

### 约束逐条核验

| 约束 | 结论 | 证据 |
|------|------|------|
| 不改 abi/spec.md 正文凑绿 | ✅ | `git diff` 新增行=0 |
| 不并入 `make check`（独立目标） | ✅ | check 依赖 grep=0 |
| ISA 侧 check-wiki-refs 与 make check 不回归 | ✅ | ISA exit 0、字节级 diff 一致、make check exit 0 |
| `[OPEN]` 不计违规 | ✅ | `ABI_DECISION_MARKERS` 含 `\[OPEN`；如 §1.1 rd1/§1.2 rb3/rb4/§3.2 多返回值 的 `[OPEN]` 行未进 44 条清单 |
| 合法标记 = `[wiki §…]`/`[spec-decision:…]`/`[OPEN]` | ✅ | 严格白名单；`[M1 architecture decision:…]` 未列入 → 154 被 surface 供归一，属诚实审计非规避 |
| DANGLING 违规 / UNPARSEABLE 告警 | ✅ | 脚本 exit 逻辑 = DANGLING+Check2；UNPARSEABLE 仅计数 |
| 不碰 QEMU/LLVM | ✅ | name-only 仅 Makefile+脚本 |

**规避审查**：44 条是行级检测的完整 surface（含 §级引用/多行 OPEN 块续行的保守误报），方向为**多报**而非把问题降级为 UNPARSEABLE 绕过门禁；ABI 侧 Check1 UNPARSEABLE=0，无「用解析不到的引用把 DANGLING 变告警」的规避。符合 reviewer.md §5 警示的反面（即无规避）。

### 判决

**Accepted** —— 六项验收命令在我自己的重跑下全部符合预期（ISA exit 0 无回归、ABI 首轮 backlog=44 且 fail-closed 退出非零、abi 正文 0 改动、未并入 check、make check exit 0），所有硬约束守住，无凑绿、无规避。首轮 44 条无引用断言为本任务应交付的产出，移交架构师三查分桶。
