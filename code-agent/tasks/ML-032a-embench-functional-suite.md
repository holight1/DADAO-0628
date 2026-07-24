# ML-032a：在 DADAO-0628 集成 Embench-IoT 19 项功能测试

**执行环境**：本地 subagent

**状态**：已完成整改、保留 1 项已知 O2 功能失败（待独立复核）

## 背景

DADAO-0628 已有可重复的 LLVM/Clang、musl 静态链接、QEMU bare-metal 和
gem5 SE 链路，但尚未把 Embench-IoT 作为项目内受版本锁定、可批量复跑的测试语料。
历史经验表明 Embench 很容易同时暴露优化器、寄存器分配、ABI、libc 和模拟器问题，
也容易因测试源补丁、旧 runner 路径或只看进程退出码而产生不可审计的“全绿”。

本任务建立当前项目自己的 fresh 基线，不继承历史通过数字，也不复用任何外部工作区
的绝对路径、编译器、sysroot 或 runner。

## 锁定输入

- Embench-IoT 上游仓库：`https://github.com/embench/embench-iot.git`
- 上游提交：`09c2ed8` 的完整 40 位 commit（实现时查询并写入
  `manifests/components.lock.toml`，不得使用 branch/tag 漂移输入）
- 当前项目工具：
  - `.work/build/llvm/bin/{clang,ld.lld,llvm-objcopy}`
  - `.work/build/musl/lib/{crt1.o,libc.a}`
  - `.work/source/qemu/build/qemu-system-dadao`
  - `tests/scripts/{dadao.ld,trampoline.bin}`
  - `GEM5_OPT`/`GEM5_SE`，默认沿用 `tests/lit/E2E/lit.cfg` 的当前路径
- 固定 benchmark inventory（必须恰好 19 项）：
  `aha-mont64 crc32 depthconv edn huffbench matmult-int md5sum nettle-aes
  nettle-sha256 nsichneu picojpeg qrduino sglib-combined slre statemate tarfind
  ud wikisort xgboost`

## 目标

1. 把 Embench 作为 enabled、精确 pin 的测试组件纳入 manifest，并提供空或最小
   patch series 目录；`scripts/fetch.py`/`apply_series.py`/manifest check 可正常处理。
2. 新增项目内可重复运行的批量脚本（建议
   `tests/scripts/embench_sweep.py`），逐 benchmark：
   - 编译每个源文件以及 Embench `support/main.c`、`support/beebsc.c` 和项目内
     DADAO board-support 胶水；
   - 使用 musl 头文件、`crt1.o` 和 `libc.a` 静态链接；
   - `llvm-objcopy -O binary` 后运行当前 QEMU bare-metal machine；
   - 直接用同一 ELF 运行当前 gem5 SE；
   - 按 Embench 自身语义判定：`verify_benchmark()` 为真时 `main` 返回 0，
     因而后端进程退出 0 才是 PASS。
3. 至少 fresh 扫描 `-O0`、`-O2` 两档；每档对 19 项分别给出：
   `PASS / FAIL_COMPILE / FAIL_LINK / FAIL_QEMU / FAIL_GEM5 /
   TIMEOUT_QEMU / TIMEOUT_GEM5`。禁止把未运行、工具缺失、超时或 skip 计为 PASS。
4. 生成机器可读 JSON 和 `docs/reviews/ML-032a-embench-functional-suite-2026-07-24.md`
   报告，写明工具/source commit、命令契约、每项双后端结果、汇总和失败根因初判。

## 实现约束

- 不访问或引用任何项目外的旧工作区，也不复制其中的绝对路径。
- 不修改 LLVM/QEMU/gem5/musl 来“追求全绿”；本任务是集成、fresh 扫描和分类。
  发现缺陷时保留产物和证据，建议后续独立立项。
- 不使用 `-disable-llvm-optzns`、`-regalloc=fast` 等绕过真实优化链的 workaround。
- 不静默修改 benchmark expected value 或算法。若 unmodified upstream 失败，先
  证明是 benchmark portability/source 问题还是项目实现问题；任何 source patch
  必须最小化、进入 `components/embench/patches/series`、在报告逐行说明，并同时
  保存 unpatched 结果。无法充分证明时保持 FAIL。
- board-support 只允许提供 `initialise_board/start_trigger/stop_trigger` 所需的
  最小目标胶水；不得改变 `benchmark()`/`verify_benchmark()`。
- 功能 sweep 可把 `WARMUP_HEAT` 固定为 0、`GLOBAL_SCALE_FACTOR` 固定为 1；
  仍必须真实执行一次 benchmark body 和校验。QEMU/gem5 wall-clock 只用于诊断
  超时，不能称为 Embench speed score、跨后端性能结果或硬件性能结论。
- 默认输出到 `.work/embench-sweep/` 或用户指定的 `/tmp`/`--out`，不提交 ELF、
  binary、日志或 JSON 大产物；提交报告和可重复脚本。
- 脚本必须 fail closed：inventory 不是 19、工具/组件缺失、零测试、结果缺项、
  任一非 PASS 时，主 sweep 返回非零；同时仍应完整写出结果供诊断。
- 不启动 nested subagent；不提交根仓库，由架构师统一 review/commit。

## 验收

- `python3 scripts/manifest_check.py`、`python3 scripts/check_issues.py` 通过。
- fresh checkout 路径可由 manifest fetch/apply；Embench HEAD 与 pin/series 一致。
- O0 与 O2 各发现且尝试 19 项，JSON 无缺项、无 SKIP、状态统计总数各为 19。
- 报告逐项列出 QEMU/gem5，不能只给“19/19”总数。
- 若 19/19 双后端全 PASS，明确它只是当前 pin、当前工具链、当前功能模型的
  correctness 结论；若未全绿，每个非通过都有阶段、退出码/超时和初步根因。
- 复跑现有 `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/`，
  记录通过/失败/unsupported 数量，确认集成未改坏已有门禁。
- 任务末尾填写完成区；之后由独立 subagent review 脚本的 fail-closed、
  inventory、测试语义、source pin 和报告证据。

## 非目标

- 不产出或校准 Embench speed/size 相对分数。
- 不把本任务扩张为 LLVM、musl、QEMU 或 gem5 缺陷修复。
- 不宣称 upstream 全量 llvm-test-suite 已覆盖。

## 完成区

完成日期：2026-07-24。

实现：

- 在 `manifests/components.lock.toml` enabled Embench，并精确 pin
  `09c2ed8c3b7008c95d08b038de4a3f6dc103ed70`。
- 新增 `components/embench/` patch series。唯一补丁显式按 little-endian
  存取 MD5 length/message words；未修改输入、算法轮次或 expected `RESULT`。
  未补丁结果保存在 `.work/embench-sweep/unpatched-results.json`。
- 新增项目内 `tests/embench/boardsupport.c`，只实现
  `initialise_board/start_trigger/stop_trigger` no-op glue。
- 新增 `tests/scripts/embench_sweep.py`：固定且校验恰好 19 项，fresh 编译
  O0/O2，链接项目 musl，运行 QEMU 与同一 ELF 的 gem5；每阶段有界 timeout，
  逐项 checkpoint，支持 `--resume`，缺工具、缺结果、timeout 或任一失败均
  fail closed。
- 生成机器证据 `.work/embench-sweep/results.json` 和本项目 Markdown 报告
  `docs/reviews/ML-032a-embench-functional-suite-2026-07-24.md`。

执行与精确结果：

- final O0：19/19 PASS；QEMU 19 PASS，gem5 19 PASS。
- final O2：18/19 PASS；QEMU 18 PASS / 1 FAIL，gem5 18 PASS / 1 FAIL。
- 总计 38 个 build，QEMU 37 PASS / 1 FAIL，gem5 37 PASS / 1 FAIL；
  compile/link failure 0，QEMU/gem5 timeout 0，SKIP/NOT_RUN 0。
- 唯一 final 失败：`-O2 qrduino`，QEMU rc=1、gem5 rc=1。诊断将首个
  output mismatch 定位到 `strinbuf[1]`（actual 6，expected 101）；仅把
  `qrencode.c` 降为 O0 可恢复双后端通过。未修改 LLVM/QEMU/gem5/musl，
  未使用优化/寄存器分配 workaround，保持 FAIL 并建议独立立项。
- 未补丁 baseline：O0 18 PASS / 1 FAIL（md5sum）；O2 17 PASS / 2 FAIL
  （md5sum、qrduino）；三项均在 QEMU/gem5 返回 1，均非 timeout。

验证命令：

- `python3 scripts/fetch.py`：enabled components 精确 fetch 成功，无 blocker。
- 项目内 fresh fixture 原样运行 `scripts/fetch.py` →
  `scripts/apply_series.py`：Embench pin + 1 patch，clean tree 与工作区一致。
- `python3 -m py_compile tests/scripts/embench_sweep.py`：PASS。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：PASS（open 22 / closed 39 / total 61）。
- `git diff --check`：PASS。
- `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/`：
  76 discovered / 76 PASS / 0 FAIL / 0 unsupported。
- `timeout --signal=INT --kill-after=30s 9000s python3
  tests/scripts/embench_sweep.py --out .work/embench-sweep/rectified-final --report
  docs/reviews/ML-032a-embench-functional-suite-2026-07-24.md`：完成 38 项，
  因保留的 O2 qrduino FAIL 按设计返回 1。

遗留风险：

- O2 qrduino 是当前 DADAO optimizer/backend 路径风险；尚未证明为可安全修补的
  benchmark source 问题。
- upstream xgboost verifier 在 `GLOBAL_SCALE_FACTOR=1` 时有效阈值为 0；
  其 PASS 不能单独证明 prediction accuracy，报告已限制结论。
- 结论只覆盖当前 pin、当前工具构建、静态 musl、QEMU dadao-m1 与 gem5 SE
  correctness，不是 Embench 性能、硬件、动态链接或完整 libc 结论。

未提交根仓库；未启动 nested subagent。

## 独立 review

独立 review 日期：2026-07-24。正式报告：
`docs/reviews/ML-032a-independent-review-20260724.md`。

Findings（按严重度）：

- **High — H1**：`--resume` 只按 `(optimization, benchmark)` 复用 checkpoint，
  不比较 source/tool/build/script/参数身份，并用当前 metadata 覆盖旧 metadata。
  隔离验证以 `--qemu /bin/false` 恢复时 38 项全部被跳过，生成的 metadata 指向
  `/bin/false`，结果 command 却仍指向旧 QEMU；这违反 fresh、可审计和 fail-closed
  契约。
- **Medium — M1**：汇总只统计有 QEMU 优先级的唯一总状态。O2 qrduino 的 QEMU
  和 gem5 均 rc=1，但 summary 显示 `FAIL_QEMU=1 / FAIL_GEM5=0`，会误导后端失败
  计数。
- **Medium — M2**：`unpatched-results.json` 的 `json_path`、log、ELF 和 binary
  路径仍指向后来被 final sweep 覆盖的 `O0/O2` 目录；真实 unpatched 产物已移至
  `O0.unpatched/O2.unpatched`。例如 JSON 中 md5sum gem5 rc=1，而其当前引用日志
  记录 rc=0。
- **Low — L1**：runner 对非空 patch series 只检查 pin 祖先关系和提交数量，不证明
  HEAD 确实由声明的 patch 内容产生。当前 series 本身已由独立 fresh fetch/apply
  验证可重放，tree 与 patch-id 一致。

已确认：MD5 补丁是当前 benchmark 范围内正当的 little-endian portability 修复，
未修改 expected；独立 fresh 38 项 sweep 再现 O0 19/19、O2 18/19 及 qrduino
双后端失败并返回 1；qrduino 和 xgboost 的风险边界表述准确；76 项 E2E 全通过。

判决：**Changes requested**。

## 独立 review 整改区

整改日期：2026-07-24。H1/M1/M2/L1 已完成实现方整改并重生 fresh 证据，原
review 判决保留为历史，等待独立 reviewer 复核。

- **H1**：JSON schema 升至 2；execution fingerprint 覆盖 inventory/opts、
  Embench pin/HEAD/tree/series/patch identity、runner 与 board/linker/trampoline/
  gem5-SE、clang/lld/objcopy/QEMU/gem5、source HEAD、musl crt/libc/include
  identity、编译/运行契约、timeout 和输出路径。resume 比较通过前不修改旧 payload；
  缺失、损坏或漂移 rc=2。已有结果逐 backend 校验
  attempted/state/timed_out/returncode，并重新推导 primary status。
- **M1**：primary status 明确为 QEMU 优先，JSON/报告另有独立 QEMU/gem5
  PASS/FAIL/TIMEOUT/NOT_RUN 统计。final O2 的 QEMU 和 gem5 均为
  18 PASS / 1 FAIL，不再显示 gem5 0 failure。
- **M2**：从 exact pin project worktree fresh 重生
  `.work/embench-sweep/unpatched-results.json`；其 json_path/invocation 正确，
  312 个日志和 236 个 object/ELF/bin 引用全部存在于稳定 unpatched 目录，
  日志 footer 与记录 rc/timeout/command、artifact size/SHA256 逐项一致。
- **L1**：preflight 按顺序比较 series patch 与 checkout commit 的 stable
  patch-id，并把 series SHA256、patch SHA256/patch-id、HEAD/tree 纳入
  fingerprint。当前 patch-id 为
  `30ad5b77725f26549e669caf791b48487661ad1a`。

整改后验证：

- patched fresh 38 项：O0 两后端 19 PASS；O2 两后端各 18 PASS / 1 FAIL，
  唯一失败 qrduino rc=1；0 compile/link failure，0 timeout，0 NOT_RUN。
- 同身份 resume：38 项仅复用，results hash 与 O0/O2 artifact mtime/size hash
  前后不变。
- `--resume --qemu /bin/false`：rc=2；JSON 与报告 SHA256 前后不变，旧
  fingerprint/metadata 未被覆盖。
- unpatched fresh：O0 两后端各 18 PASS / 1 FAIL（md5sum）；O2 两后端各
  17 PASS / 2 FAIL（md5sum、qrduino）。
- final fingerprint：
  `fed694160161c4a65963630bc5095b2efc8fcc5809f24cf54941d5152ae968f5`。
- 整改后 py_compile、manifest check、issue registry、`git diff --check` 均
  PASS；E2E 76 discovered / 76 PASS / 0 FAIL / 0 unsupported。

### 最终独立复审判决

复审日期：2026-07-24。

- **H1：Closed。** 同 identity resume 复用 38 项且 results/artifacts 不变；
  `--resume --qemu /bin/false` rc=2，checkpoint/report SHA256 均不变。
- **M1：Closed。** patched O2 独立 backend summary 明确 QEMU 和 gem5 各
  18 PASS / 1 FAIL。
- **M2：Closed。** unpatched schema-2 JSON 的 312 个日志 footer 和 236 个
  artifact identity 已独立逐项验证，路径、command/rc/timeout、size/SHA256
  全部自洽。
- **L1：Closed。** exact pin 上的错误单 commit 被 stable patch-id 顺序校验拒绝，
  rc=2 且未创建 checkpoint。
- **新 Low — R1（保留，不阻断）**：同 identity resume 若携带 `--report`，当前
  renderer 会覆盖主报告中人工追加的 unpatched/resume/门禁附录。建议让这些章节
  完全由 renderer 生成、移至独立 appendix，或在纯复用 resume 时不重写 report。

最终判决：**Accepted-with-findings**。原 H1/M1/M2/L1 全部关闭；Low R1 不阻断
ML-032a 接受。

### 架构师收口 R1（2026-07-24）

接受且窄修：完整矩阵的同身份 `--resume` 现在只验证/复用 checkpoint，不再调用
generic renderer 覆盖既有 durable 报告；部分矩阵 resume 在新增结果后仍正常更新
报告。定向验证对已有完整 checkpoint 执行带 `--report` 的 resume，报告 SHA256
保持不变，进程仍因已知 `qrduino -O2` 返回 1。R1 已关闭；原独立 review 判决与
finding 保留为审计历史。
