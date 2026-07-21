# ML-015b 审计：spec → vector → harness

日期：2026-07-21  
范围：`DADAO-0628` 的 `contracts/isa/spec.md`、`tests/vectors/isa/*.yaml`、`tests/scripts/run_qemu_test.py` 及其直接使用的 `build_test_binary.py`。  
限制：未访问 `~/toolchain` 或 `~/knowledge-graph`；本审计只读，未修改源码、向量、harness、issues/wiki/task。

## 总结

审计判定：**Needs-fix（规范/向量分类与 harness fail-closed 证据不足）**。

- 规范明确：cold RegRAS（`ra63[63:48] == 0`）执行 `ret` 应为 **RASUF**，且 precise、PC 停在 faulting `ret`、RA 不变（`spec.md §5.6`）。`control-flow.yaml` 的两个 cold-ret 仍期望 **ILLI**。
- `jump_r rb0,...` 是规范定义的 relative jump 特例，`call_r rb0,...` 使用合法的 RB 源；`ret rd0,...` 明确允许丢弃返回值。对应 control-flow 向量把这些情况作为 `legality/ILLI`，证据实际是跳到 poison/halt 后得到 ILLI，不能作为目标指令的 ILLI 预期。
- 所有 212 条 YAML 都具备 schema 必需字段；计数为 **212 total / 206 active / 6 deferred**。active 的 semantic/boundary 条目都有 `expected_state`（非空 82 条；控制流另外 21 条为空对象）。但 fault 向量没有 PC/RA 状态断言。
- `FAULT_CODES` 的 ILLI/MALIGN/UNDI/RASOF/RASUF 映射齐全；`IALIGN` 虽在 schema 允许值中，却未映射且没有对应 active 向量。
- 目录参数确实以字符串落入 `build_test_binary()` 并触发 `AttributeError`，不会误报 PASS，但 CLI 没有 fail-closed 的参数错误处理。更重要的是，harness 对 fault 只验证进程退出码，不验证 fault 来源或 PC/RA；builder 对 `expected_state` 只比较 RD/RB/内存，未知的 RA/PC 键会被忽略后正常 PASS。

## 三列表格

| 分类 | 证据 | 判定 |
|---|---|---|
| YAML schema/字段完整性 | 逐读 `tests/vectors/isa/*.yaml` 共 212 条；`mnemonic/format/class/encoding.word/input_state/wiki_cite` 无缺失。`tests/vectors/schema.md:10-29` 定义这些字段。 | **通过（字段层面）**。这不等于语义或分类正确。 |
| active/deferred 计数 | `control-flow 37/37/0`、`misc 4/3/1`、`rb-ops 28/28/0`、`rd-arith 21/21/0`、`rd-compare 10/10/0`、`rd-cond-assign 15/10/5`、`rd-load-store 49/49/0`、`rd-logic 8/8/0`、`rd-shift-extend 21/21/0`、`rd-wyde-block 19/19/0`（total/active/deferred）。 | **通过（计数）**：212 / 206 / 6。harness 文件模式在 `run_qemu_test.py:107-113` 跳过 deferred。 |
| expected_state 覆盖 | active semantic/boundary 共 103 条：非空状态 82 条、控制流空对象 21 条；无 active semantic/boundary 的 null 状态。deferred 6 条为 null。builder 只在 `build_test_binary.py:107-112` 读取 `rd/rb/memory`。 | **部分通过**：RD/RB/内存状态可进入比较；空对象仅证明控制流路径到达正常出口。PC/RA 未被比较。 |
| precise ILLI/UNDI 规则 | `spec.md §2.5`（约 `:158-165`）规定保留编码为 UNDI；`§2.6`（`:167-223`）规定非法操作数为 ILLI，均 precise、无副作用。YAML 中有 ILLI，但 **0 个 UNDI** 向量。 | **覆盖不足**：现有 ILLI 条目不能证明 UNDI 路径；未发现现有 expected_fault=UNDI 错写。 |
| precise MALIGN | `spec.md §3.1:354-365`：64-bit `ldo` 非 8 对齐为 MALIGN，PC 留在 faulting instruction、无寄存器写。`rd-load-store.yaml:871-883` 的 EA `0x87FF00FF`、`expected_fault: MALIGN` 与之相符。 | **故障码/引用相符**；但条目 `class: legality`，而该操作数组合合法、故障原因是 alignment，分类证据不足。 |
| RASOF / RASUF 规范 | `spec.md §5.6:892-914`：call 满栈溢出为 RASOF；cold ret 为 RASUF；两者 precise、PC/RA 不变。现有 YAML 中 **0 个 RASOF、0 个 RASUF**。 | **覆盖不足**：不能从现有 vector/harness 结果证明 RASOF/RASUF 或 PC/RA 不变。 |
| ML-015a cold-ret #1 | `control-flow.yaml:470-480`：`ret` word `0x6E040000`，`ra63` cold，`class: encoding`，`expected_fault: ILLI`；notes 说跳到 addr=0 后由 halt/rd0 产生 ILLI。规范 `§5.6:903-911` 对 cold pop 的唯一异常是 RASUF。 | **不一致**：目标 `ret` 的规范期望是 **RASUF (0x85)**，不是 ILLI (0x82)；当前 ILLI 是 harness/poison 后果，不能作为 QEMU 对目标指令的失败判定。 |
| ML-015a cold-ret #2 | `control-flow.yaml:508-518`：`ret rd0,0` word `0x6E000000`，`class: legality`，`expected_fault: ILLI`。`spec.md §2.6.1:179-182` 明确 `ret rdha=rd0` 合法；cold RAS 仍由 `§5.6` 产生 RASUF。 | **双重不一致**：`rd0` 不是该 ret 的非法目的地；cold 条件的规范期望仍为 **RASUF (0x85)**，不是 ILLI。 |
| control-flow encoding/legality 分类 | `control-flow.yaml:434-444` 的 `jump_r rb0`、`:458-468` 的 `call_r rb0` 把下游 halt/rd0 的 ILLI 写成 encoding fault；`:484-506` 又把相同合法 `rb0` 源用法标成 legality/ILLI。`spec.md §5.3:842-848` 明确 `jump rbha=rb0` 是 relative jump；`§5.4:860-868` 定义 call 的 RB 源；无“rb0 源非法”规则。 | **不一致**：这些不是由 control-flow 指令本身证明的 ILLI；属于 downstream poison/halt 或错误 legality 分类。 |
| control-flow wiki_cite | branch/jump 使用 `§5.1/§5.2/§5.3`，semantic call 使用 `§5.4`，ret 正常语义使用 `§5.5`，总体对应正确；但 `control-flow.yaml:446-468` 的 call encoding 仍写 `spec.md §5.3`，cold-ret 条目只写 `§5.5`，未指向定义 fault 的 `§5.6`。 | **局部引用不充分/错误**：call encoding 应落到 call 章节；cold-ret 的异常判定必须同时核对 §5.6。 |
| encoding class 与 fault 的一致性 | `tests/vectors/schema.md:56-62` 将 encoding 定义为 `expected_fault: null`。实际有 21 个 `class: encoding` 且 `expected_fault: ILLI`：control-flow 3、misc 1、rb-ops 3、rd-arith 2、rd-load-store 8、rd-wyde-block 4；其中多数 notes 明示是 `immu6=0`、`rb0`、`rd0` 或除零等执行语义。 | **不一致（按类别）**：这些条目不是单纯 encoding-only；control-flow 的 3 条还混入 downstream poison 结果。 |
| FAULT_CODES | `run_qemu_test.py:24`：`ILLI=0x82`、`MALIGN=0x81`、`UNDI=0x83`、`RASOF=0x84`、`RASUF=0x85`；与 schema 允许的五类重点故障一致。`IALIGN` 仅出现在 schema `:26`，未在 map 中。 | **重点五类通过；完整异常集合不全**：当前 harness 不能按 `expected_fault: IALIGN` 正常通过。 |
| 目录参数 | `run_qemu_test.py:107-125` 仅对普通文件走列表分支；目录进入 `yaml.safe_load(args.case)`，得到字符串，再在 `build_test_binary.py:73-83` 的 `case.get(...)` 触发 `AttributeError`。 | **不会误报 PASS，但参数处理失败**：表现为 traceback/rc=1，而不是明确的输入错误或 fail-closed rc=2。 |
| expected_fault 判定 | `run_qemu_test.py:40-59`：匹配 fault exit code 即 PASS；未验证 fault 是否来自被测指令，也未验证 faulting PC、RA/其他副作用。 | **不满足 fail-closed 证明**：cold-ret 的现状正展示了“下游 ILLI 与目标 fault 混淆”的风险。 |
| expected_state 判定 | `build_test_binary.py:98-112` 只取 `rd/rb/memory`，三者均不存在时直接 `emit_exit(0)`；`build_test_binary.py:291-295` 随后采用该结果。可复核：含 `expected_state: {ra: ..., pc: ...}` 的人工 case 生成 24-byte binary，`_classify(0, case)` 为 `('PASS','exit=0')`。 | **不满足 fail-closed**：当前向量没有 RA/PC expected_state，所以不能据此声称 precise PC/RA 不变已被 harness 验证；若未来写入这些键，会被静默忽略。 |
| active/deferred fail-closed | 文件模式跳过 deferred；`total==0` 或全 SKIP 时 `run_qemu_test.py:132-137` 返回错误；任一 FAIL 在 `:138-139` 返回 rc=1。 | **这部分通过**：不会把 deferred 或全跳过当 PASS；但不弥补 fault 来源、PC/RA 与未知状态键未验证的问题。 |

## 可复核命令

以下命令均在仓库根目录执行，不需要访问 `~/toolchain` 或 `~/knowledge-graph`：

```bash
cd /home/holight/DADAO-0628

# 1. 规范重点章节与精确异常
nl -ba contracts/isa/spec.md | sed -n '158,240p;354,365p;794,914p'

# 2. 全量 YAML 字段、active/deferred 计数、fault/class 汇总
python3 - <<'PY'
from pathlib import Path
import collections, yaml
rows=[]
for p in sorted(Path('tests/vectors/isa').glob('*.yaml')):
    cases=yaml.safe_load(p.read_text()) or []
    deferred=sum(c.get('status') == 'deferred' for c in cases)
    rows.append((p.name, len(cases), len(cases)-deferred, deferred))
    assert all(k in c for c in cases for k in
               ('mnemonic','format','class','encoding','input_state','wiki_cite'))
    assert all('word' in c['encoding'] for c in cases)
    print(p.name, rows[-1], collections.Counter(
        (c.get('class'), c.get('expected_fault')) for c in cases))
print('TOTAL', tuple(sum(r[i] for r in rows) for i in range(1,4)))
PY

# 3. 明确列出 cold-ret、control-flow fault/class 与所有非空 fault
nl -ba tests/vectors/isa/control-flow.yaml | sed -n '422,520p'
python3 - <<'PY'
from pathlib import Path
import yaml
for p in sorted(Path('tests/vectors/isa').glob('*.yaml')):
    for i,c in enumerate(yaml.safe_load(p.read_text()) or [], 1):
        if c.get('expected_fault'):
            print(p, i, c['mnemonic'], c['class'], c['expected_fault'], c['wiki_cite'])
PY

# 4. 目录参数 AttributeError（使用显式假 QEMU 路径，避免自动探测）
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/ --qemu /bin/false
# 预期：rc=1，AttributeError: 'str' object has no attribute 'get'

# 5. FAULT_CODES、分类与 fail-closed 分支
nl -ba tests/scripts/run_qemu_test.py | sed -n '19,60p;96,140p'
nl -ba tests/scripts/build_test_binary.py | sed -n '98,113p;277,297p'

# 6. 证明 RA/PC 键不会进入状态比较（只在内存中生成 bytes，不运行 QEMU）
python3 - <<'PY'
import sys
sys.path.insert(0, 'tests/scripts')
from build_test_binary import build_test_binary
import run_qemu_test as h
case={'encoding': {'word':'0x10000000'},
      'expected_state': {'ra': {'ra63':'0x0001000000000000'},
                         'pc':'0x80000004'}}
print(len(build_test_binary(case)), h._classify(0, case))
# 预期：24 ('PASS', 'exit=0')；builder 仅支持 rd/rb/memory。
PY
```

未执行面向 `~/toolchain` 的自动探测路径，也未把现有 ML-015a 的 QEMU 观测重新解释为本次 fresh 运行结果。
