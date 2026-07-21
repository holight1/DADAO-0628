# ML-015a 独立审阅

日期：2026-07-21  
范围：ML-015a worker review、task、ISA harness/YAML、ISA §5.6、当前 QEMU build/version。  
限制：未访问 `~/toolchain` 或 `~/knowledge-graph`；未修改 worker 报告、源码或向量。

## 结论：Needs-fix

存在一个必须先修正的规范/向量预期不一致：`control-flow.yaml` 的两个 cold-RegRAS `ret` 用例声明 `expected_fault: ILLI`，但 `contracts/isa/spec.md §5.6` 明确规定 cold RegRAS（`ra63[63:48] == 0`）的返回异常是 `RASUF`。当前 QEMU 返回 `0x85`，与规范一致。因此这两项不能计为 QEMU 失败；本审阅不修改 QEMU 或 YAML，也不擅自把向量改成某个结果。应由 ISA/vector owner 先处理预期与规范的对齐。

## 1. cold RegRAS 审计（阻塞项）

规范证据（`contracts/isa/spec.md` §5.6，约 L903–L913）：

- `ret` 在 `ra63[63:48] == 0` 时走 `RASUF`；
- `RASUF` 是 precise fault，RA 不修改；
- `ILLI` 不是该 cold-RegRAS 条件的规范异常。

两个 YAML 条目：

- `control-flow.yaml:L470-L480`：`ret`, encoding `0x6E040000`，`expected_fault: ILLI`，notes 写明 “RA stack cold=0”；
- `control-flow.yaml:L508-L518`：`ret`, encoding `0x6E000000`，`expected_fault: ILLI`，notes 写明 “RA=0”。

`run_qemu_test.py:L24` 将 `ILLI` 映射为 `0x82`、`RASUF` 映射为 `0x85`。独立逐 YAML 执行实际得到这两行：

```text
FAIL expected ILLI exit=0x82, got 0x85 encoding-only: RA stack cold=0 → jump to addr=0 → halt rd0 → ILLI
FAIL expected ILLI exit=0x82, got 0x85 ret rd0,0; RA=0 → jump to addr=0 → halt rd0 → ILLI
```

审计判定：这准确记录了观察到的返回码，但将两项归为“QEMU FAIL”是不严谨的；按 §5.6，`0x85` 是符合规范的 cold-RegRAS 行为。两项应暂时作为“向量 expected_fault 与 ISA §5.6 不一致”的待处理项，不得作为 QEMU 修复依据。

## 2. 目录参数与 ISA 统计

目录入口的 `AttributeError` 可复现。`run_qemu_test.py:L110-L122` 仅在 `os.path.isfile(args.case)` 为真时按 YAML 文件读取；传入目录后把目录字符串交给 `yaml.safe_load(args.case)`，最终在 `build_test_binary(case)` 的 `case.get(...)` 处触发：

```text
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/ \
  --qemu .work/source/qemu/build/qemu-system-dadao
→ rc=1
→ AttributeError: 'str' object has no attribute 'get'
```

逐 YAML 的只读复核得到：

| YAML | total | active | deferred |
|---|---:|---:|---:|
| control-flow.yaml | 37 | 37 | 0 |
| misc.yaml | 4 | 3 | 1 |
| rb-ops.yaml | 28 | 28 | 0 |
| rd-arith.yaml | 21 | 21 | 0 |
| rd-compare.yaml | 10 | 10 | 0 |
| rd-cond-assign.yaml | 15 | 10 | 5 |
| rd-load-store.yaml | 49 | 49 | 0 |
| rd-logic.yaml | 8 | 8 | 0 |
| rd-shift-extend.yaml | 21 | 21 | 0 |
| rd-wyde-block.yaml | 19 | 19 | 0 |
| **合计** | **212** | **206** | **6** |

同一 harness、显式指定当前 QEMU、逐文件执行的 fresh 分类为：`204 PASS / 2 FAIL / 0 SKIP / 0 timeout`；仅 `control-flow.yaml` 返回 file rc=1。统计本身可复核，但上面的两个 FAIL 不能再表述为 QEMU 缺陷。

复核命令：

```bash
python3 - <<'PY'
from pathlib import Path
import yaml
root = Path('tests/vectors/isa')
rows = []
for p in sorted(root.glob('*.yaml')):
    cases = yaml.safe_load(p.read_text())
    deferred = sum(c.get('status') == 'deferred' for c in cases)
    rows.append((p.name, len(cases), len(cases) - deferred, deferred))
print(rows)
print(tuple(sum(r[i] for r in rows) for i in range(1, 4)))
PY

python3 - <<'PY'
from pathlib import Path
import subprocess, sys
root = Path('.')
counts = {'PASS': 0, 'FAIL': 0, 'SKIP': 0}
for p in sorted((root / 'tests/vectors/isa').glob('*.yaml')):
    r = subprocess.run([
        sys.executable, 'tests/scripts/run_qemu_test.py', str(p),
        '--qemu', '.work/source/qemu/build/qemu-system-dadao'],
        capture_output=True, text=True, check=False)
    for line in r.stdout.splitlines():
        status = line.split(None, 1)[0] if line.split() else ''
        if status in counts:
            counts[status] += 1
print(counts)
PY
```

## 3. QEMU 0019 与当前 build/version

0019 应用状态有充分证据：

```bash
tail -1 components/qemu/patches/series
→ 0019-dadao-cfx-state-scaffold.patch

git -C .work/source/qemu apply --reverse --check \
  components/qemu/patches/0019-dadao-cfx-state-scaffold.patch
→ rc=0

git -C .work/source/qemu status --short --untracked-files=all
→ M target/dadao/cpu.c
→ M target/dadao/cpu.h
```

这证明当前源码树包含 0019 的工作树改动，且 dirty 文件正是该 patch 涉及的两个文件。worker 报告记录的 `ninja -C .work/source/qemu/build qemu-system-dadao → rc=0` 及其编译/链接输出，作为当时的重编记录是合理的。

不过，当前复核时版本字符串与 worker 报告不一致：

```bash
.work/source/qemu/build/qemu-system-dadao --version
→ QEMU emulator version 10.0.0 (v10.0.0-19-gac58f31-dirty)

ninja -C .work/source/qemu/build -n qemu-system-dadao
→ 当前 dry-run 仍列出 4 个生成/编译/链接动作
```

worker 报告写的是不带 `-dirty` 的 `v10.0.0-19-gac58f31`。因此 0019 应用可接受，但报告中的“当前 QEMU version”应以实际带 `-dirty` 的当前输出为准，并应补足可重放的构建产物/版本对应关系；在此修正前，重编证据的当前状态标记为 Needs-fix。

## 4. LLVM E2E 与历史边界

worker 记录的命令是：

```text
PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/
→ 被用户约 0.1 秒后中断；无数值 rc；事后无残留 llvm-lit/lit.py 进程
```

该描述明确区分了“被中断”和“无 fresh 数值”，没有伪造 full E2E 或其中 23 个 `llvm-test-suite` thin-lit 用例的结果。当前树中 `tests/lit/E2E/llvm-test-suite/*.test` 静态计数确为 23；这只是入口内容计数，不是本轮 fresh PASS 数。

边界表述严谨：

- 历史 `59/59` 不是本轮 E2E fresh 结果；
- 历史 `203 PASS` 不是本轮 206 active 的 ISA fresh 结果；
- full upstream `llvm-test-suite` 与 `gcc-c-torture` 本轮未启动，不能从被中断的 `tests/lit/E2E/` 命令推导其结果；
- tail-call lowering 与 varargs RB pointer save-area 仍是扩大测试前的 open boundary。

## 最终处理意见

保留当前 fresh 观测值 `204 PASS / 2 observed RASUF / 0 SKIP / 0 timeout`，但不要把它写成 `204 PASS / 2 QEMU FAIL`。在 ISA §5.6 与两个 YAML 的 `expected_fault`/notes 对齐、并校正当前 QEMU version/build 证据前，本 review 不接受（`Needs-fix`）。本次审阅未修改任何 worker 报告、源码或向量。
