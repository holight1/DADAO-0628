# ML-032a 独立 review

日期：2026-07-24。

判决：**Changes requested**。

整改状态（2026-07-24）：**H1/M1/M2/L1 已由实现方整改并重生证据，待独立复核**。
下方原始 findings 与判决保留不改，文末追加逐项整改记录。

本 review 严格限定在 `/home/holight/DADAO-0628` 内进行；未访问项目外旧工作区，
未启动 nested subagent，未修改实现文件。审查覆盖任务契约、当前未提交 diff、
Embench 组件与 patch series、sweep 脚本、board glue、现有报告、patched/unpatched
JSON 及项目内诊断与重放证据，并独立执行了 fresh 38 项 sweep。

## Findings（按严重度）

### High — H1：`--resume` 未绑定 source/tool identity，会复用并错误重标旧结果

`tests/scripts/embench_sweep.py:805-836` 先直接载入已有 JSON，随后用当前 preflight
metadata 覆盖旧 metadata；`tests/scripts/embench_sweep.py:837-854` 只按
`(optimization, benchmark)` 判断完成项，不比较 checkpoint 的 source、工具、
构建产物、脚本、参数或 timeout 身份。`validate_results()` 也只检查矩阵键和总状态，
不检查 backend 的 `attempted/state/returncode` 与总状态是否一致。

隔离行为验证把现有 checkpoint 复制到项目内 `.work`，然后以
`--resume --qemu /bin/false` 运行。结果如下：

- 38 项全部显示 `checkpoint exists`，`/bin/false` 没有执行；
- 新 JSON metadata 把 QEMU 标成 `/bin/false` 及其 sha256；
- 38 项结果中的 QEMU command 仍是原
  `.work/source/qemu/build/qemu-system-dadao`；
- 因现有 qrduino 失败，进程返回 1；若 checkpoint 原为全 PASS，该路径会返回 0。

因此当前 `--resume` 可把旧 source/tool 结果包装成当前身份，违反 fresh/可审计和
fail-closed 契约。修复时应在复用前构造并比较稳定的 execution fingerprint，至少
覆盖 schema、inventory/optimization、Embench pin/HEAD/tree/patch 内容、sweep
脚本与 board/linker/trampoline/gem5-SE 文件、工具及 musl 构建产物身份、关键参数
和 timeout；不一致时应拒绝 resume 或清空旧矩阵。恢复结果还应验证每个后端确实
attempted，且 backend 状态、退出码和总状态相互一致。

### Medium — M1：汇总把“优先级总状态”显示成后端失败数，双后端失败时误导

`tests/scripts/embench_sweep.py:467-474` 按 QEMU 优先级选择唯一总状态，
`tests/scripts/embench_sweep.py:480-492` 又只统计该字段。于是 O2 qrduino 的
QEMU 和 gem5 均为 rc=1，但 JSON/Markdown 汇总显示
`FAIL_QEMU=1 / FAIL_GEM5=0`。

逐项表和任务完成区正确写出了 gem5 的失败，因此没有丢失原始结果；但汇总列名看似
后端计数，机器消费者也很容易据此得出“gem5 无失败”的错误结论。应增加独立的
QEMU/gem5 PASS/FAIL/TIMEOUT 计数，或把现有列明确改名为
`PRIMARY_STATUS_*`，不得将其表述为后端失败数。

### Medium — M2：`unpatched-results.json` 的产物路径和自身身份已失配

`.work/embench-sweep/unpatched-results.json` 的 `metadata.json_path` 仍为
`.work/embench-sweep/results.json`，各项 log/ELF/binary 路径也仍指向
`.work/embench-sweep/O0|O2/...`。这些目录后来被 final patched sweep 覆盖，真实
unpatched 产物被移到 `O0.unpatched`/`O2.unpatched`，但 JSON 未同步。

例如 unpatched O0 md5sum 在 JSON 中为 gem5 rc=1，JSON 指向的当前
`O0/md5sum/gem5.log` 却记录 `trap-exit code=0`；实际 rc=1 日志位于
`O0.unpatched/md5sum/gem5.log`。JSON 内的状态矩阵和保留的 relocated 日志仍相互
支持，但其直接证据链接已经错误，削弱了 MD5 unpatched 对照的可审计性。应使用独立
且稳定的 `--out/--json` 生成 unpatched baseline，或在移动产物时同步重写并验证
所有路径及 invocation。

### Low — L1：当前 source checkout 校验只检查提交数量，不证明应用的是声明的 series

`tests/scripts/embench_sweep.py:181-210` 对非空 series 只验证 pin 是 HEAD 的祖先，
且 `pin..HEAD` 的提交数等于 patch 文件数。任意一个基于 pin 的单提交 clean tree
都可通过当前一补丁 series 的 preflight。

当前实际 checkout 没有出现该问题：独立 fresh fetch/apply 得到 tree
`7e1569deeb5b03ef52a3be1ab217310c097de251`，补丁 patch-id
`30ad5b77725f26549e669caf791b48487661ad1a` 与根工作区一致。建议后续把 series
内容哈希、应用后 tree 或逐提交 patch-id 纳入校验和 execution fingerprint。

## 七项重点结论

1. **MD5 patch 可接受。** 上游代码把 MD5 消息 word 和 length 当作 host-native
   endian；补丁只改为显式 little-endian 编解码。pin 到 patched HEAD 的 diff
   只有 `src/md5sum/md5.c` 这 14 增 2 删，`RESULT`、输入、轮次和 verifier 均未改。
   对 0..999 字节输入用独立标准 MD5 计算，四个 little-endian digest word 的 XOR
   正是现有 `RESULT=0x33f673b4`。该结论只覆盖当前 1000-byte benchmark；补丁没有
   把上游 32-bit length 实现扩张成通用大消息 MD5。
2. **19×O0/O2 inventory 与实际执行成立。** inventory 固定且 preflight 要求
   source 目录与其精确相等。现有两份 JSON 各有 38 个唯一结果；final JSON 中
   QEMU/gem5 均 attempted 38 次、无 NOT_RUN/SKIP。独立 fresh sweep 再现 O0
   19 PASS，O2 18 PASS + qrduino 双后端 FAIL，且因非全绿返回 1。除 H1 的 resume
   身份漏洞外，fresh 路径对缺工具、缺项、timeout 和非 PASS 均 fail closed。
3. **双后端失败的 summary 会误导。** 见 M1。
4. **`--resume` 会错误复用身份已改变的结果。** 见 H1，已有直接行为复现。
5. **pin/fetch/apply/series 当前可重放。** 根 `scripts/fetch.py` 成功 fetch 所有
   enabled pin 并保留已打补丁 HEAD；独立 fresh fixture 从 GitHub checkout
   `09c2ed8c3b7008c95d08b038de4a3f6dc103ed70`，运行原
   `apply_series.py` 后得到上述相同 tree 和 patch-id，工作树 clean。L1 是 runner
   对任意 checkout 的验真不足，不否定当前 series 本身可重放。
6. **qrduino/xgboost 边界表述基本准确。** qrduino 报告保留 FAIL，只把证据收敛到
   DADAO 对 `qrencode.c` 的优化路径，并明确不足以安全修改 benchmark source；
   项目内诊断日志支持首个差异 `strinbuf[1]` actual 6 / expected 101，以及仅
   `qrencode.c` 降 O0 恢复。xgboost verifier 在 scale=1 时阈值为 0，而 body 返回
   非负正确计数，因此报告把 PASS 限定为“body 执行且 upstream verifier 返回真，
   不单独证明 prediction accuracy”是必要且正确的。
7. **完成区的数值和主要边界与证据一致，但完成声明尚不成立。** final/unpatched
   计数、qrduino 失败、76 项 E2E、manifest/issues checks 和 replay 结论均可复核。
   但“支持 `--resume` 且 fail closed”的描述被 H1 反证，unpatched 机器证据路径又
   存在 M2；修复并重生相应证据前不应接受任务完成。

## 独立验证

- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：PASS（open 22 / closed 39 / total 61）。
- `git diff --check`：PASS。
- `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/`：
  76 discovered / 76 PASS。
- `python3 tests/scripts/embench_sweep.py --out
  .work/ML-032a-independent-review-fresh-20260724`：完成 38 项；O0 19 PASS，
  O2 18 PASS + qrduino 双后端 FAIL；按设计 rc=1。
- `python3 tests/scripts/embench_sweep.py --resume ... --qemu /bin/false`：
  38 项均被复用，复现 H1。
- 隔离 fresh fixture 中原样执行 `scripts/fetch.py` →
  `scripts/apply_series.py`：PASS，tree/patch-id 与当前 checkout 一致。
- 标准库 MD5 独立计算：digest word XOR 为 `0x33f673b4`，与未修改 expected 一致。

## 判决

**Changes requested**。H1 是阻断项；M1、M2 应与其一并修复并重生报告/JSON。
L1 可在同一轮补强，或明确登记为后续验真加固，但不得继续宣称当前 resume 对身份
变化 fail closed。

## 实现方整改记录（2026-07-24）

### H1 — 已整改：resume 绑定稳定 execution fingerprint

JSON schema 升至 2。fingerprint identity 使用 canonical JSON SHA256，覆盖：

- schema、精确 19 项 inventory、O0/O2；
- Embench repository、pin、HEAD、tree、source mode、series 内容 SHA256、每个
  patch 的 SHA256/stable patch-id 和 checkout commit patch-id；
- sweep 脚本、board glue、linker script、trampoline、gem5-SE、Embench support
  source；
- clang、ld.lld、llvm-objcopy、QEMU、gem5 的 path/SHA256/size/executable；
- LLVM/QEMU/gem5/musl source HEAD，musl crt1/libc identity，以及实际使用的四个
  include directory 内容 identity；
- compile/link/QEMU/gem5 契约、defines、timeout 和 source/out/JSON 路径。

resume 先完成当前 preflight/fingerprint，再读取旧 JSON 并检查 stored fingerprint
自身 digest、与当前 fingerprint 的完整相等性、JSON path、summary、已有结果和
证据；通过前不修改 payload。缺 checkpoint、旧 schema、缺 fingerprint、identity
漂移或 evidence 不一致均 rc=2 且不写旧 JSON。通过后只追加
`metadata.resume_history`，不覆盖原 invocation 或 execution identity。

结果 validator 现在逐 backend 检查 attempted/state/timed_out/returncode/command/log
组合，并根据 QEMU 优先规则重新推导 primary status。compile/link/objcopy/QEMU/
gem5 日志带机器可读 footer；resume 同时验证 footer 与 JSON rc/timeout/command
一致，以及 object/ELF/bin 的 path/size/SHA256。

验证：

- 完整 final checkpoint 同身份 resume：38 项均 `checkpoint exists`，rc=1 仅因
  已知 qrduino FAIL；results hash 和 O0/O2 文件 size+mtime hash 前后不变。
- `--resume --qemu /bin/false`：rc=2，stored/current fingerprint 分别为
  `fed69416…`/`4edce1d0…`；JSON sha256 前后均为
  `5f49417ae0458c803eadaf48a18aa39e0bdd337651ae321fe34208604519bb08`，
  报告当时的 sha256 前后也相同。

### M1 — 已整改：primary 与 backend 统计分离

`status` 保留 QEMU 优先的单一 primary status，并在 JSON/报告明确命名为
`primary_status`/`PRIMARY_*`。另新增 QEMU 和 gem5 各自
PASS/FAIL/TIMEOUT/NOT_RUN 统计。整改后 final O2 明确显示：

- primary：PASS 18、FAIL_QEMU 1；
- QEMU：PASS 18、FAIL 1、TIMEOUT 0、NOT_RUN 0；
- gem5：PASS 18、FAIL 1、TIMEOUT 0、NOT_RUN 0。

因此不再出现汇总称 gem5 0 failure、逐项却 gem5 失败的歧义。

### M2 — 已整改：fresh 重生稳定 unpatched 证据

使用项目内 exact-pin detached worktree 和 `--source-mode unpatched` fresh 执行
38 项。canonical JSON：
`.work/embench-sweep/unpatched-results.json`，sha256
`19b93c5c16cdae9508b4bfe8572a0f01c53280b2ff73601fc417f9612494fa86`。
其 `metadata.json_path`、invocation、fingerprint source mode/HEAD 均正确；所有
日志和 object/ELF/bin 指向独立稳定目录 `.work/embench-sweep/unpatched/`。

逐项 evidence validator 核验 312 个日志和 236 个 artifact identity 全部存在，
日志 footer 与 JSON rc/timeout/command 一致，artifact size/SHA256 一致。fresh
结果未改变：O0 两后端各 18 PASS / 1 FAIL（md5sum）；O2 两后端各
17 PASS / 2 FAIL（md5sum、qrduino）。旧失配 JSON 只作为历史保留在
`.work/embench-sweep/unpatched-results.pre-rectification.json`。

### L1 — 已整改：series 内容与 checkout commit patch-id 验真

preflight 除 pin ancestor 与 commit count 外，现逐项计算 series patch 和
`pin..HEAD` commit 的 stable patch-id 并按顺序比较。series 文件 SHA256 为
`89d0ac6146fd0f5c14827cb8a37b5f12e085ab890fb0f39c0574bcff2c77d739`，
series/checkout patch-id 均为
`30ad5b77725f26549e669caf791b48487661ad1a`，最终 tree 仍为
`7e1569deeb5b03ef52a3be1ab217310c097de251`。这些 identity 同时进入 resume
fingerprint。

### 整改后 fresh 结果

命令：

`python3 tests/scripts/embench_sweep.py --out .work/embench-sweep/rectified-final --report docs/reviews/ML-032a-embench-functional-suite-2026-07-24.md`

- O0：QEMU 19 PASS，gem5 19 PASS。
- O2：QEMU 18 PASS / 1 FAIL，gem5 18 PASS / 1 FAIL。
- 唯一失败仍为 qrduino，两个 backend rc=1；compile/link failure、timeout、
  NOT_RUN 均为 0。
- final execution fingerprint：
  `fed694160161c4a65963630bc5095b2efc8fcc5809f24cf54941d5152ae968f5`。
- py_compile、manifest check、issue registry、`git diff --check` 均 PASS；
  E2E 为 76 discovered / 76 PASS / 0 FAIL / 0 unsupported。

实现方结论：H1、M1、M2 和 L1 的整改及 fresh 证据已完成；原始
**Changes requested** 判决作为 review 历史保留，状态等待独立 reviewer 复核。

## 整改独立复审结论（2026-07-24）

复审判决：**Accepted-with-findings**。

本轮完整读取了 schema-2 runner、主报告、任务整改区、本报告中的实现方整改记录，
以及 fresh patched/unpatched JSON。按要求只做定向探针，没有第三次执行完整
38 项 sweep；数值与整改后 fresh 证据及此前独立 fresh 结果一致。

### 原 findings 处置

- **H1 — Closed。** 隔离 checkpoint 的同 identity resume 复用 38 项，rc=1 仅因
  已知 qrduino FAIL；results hash 与 O0/O2 artifact path/size/mtime 集合 hash
  前后不变。随后加 `--qemu /bin/false` 得到 rc=2，checkpoint 与 report 的完整
  SHA256 前后均不变，stderr 明确报告 fingerprint drift。代码在 fingerprint 和
  schema/evidence 验证通过前没有写 checkpoint。
- **M1 — Closed。** schema-2 JSON 将 QEMU 优先的 `primary_status` 与独立
  backend 统计分开。patched O2 明确为 QEMU PASS=18/FAIL=1、gem5
  PASS=18/FAIL=1；主报告的独立 backend 表也逐项显示两者 FAIL=1，不再把 primary
  的 `FAIL_GEM5=0` 误表述为 gem5 后端无失败。
- **M2 — Closed。** fresh unpatched JSON 的 schema、json_path、invocation、
  source mode、pin/HEAD 和 fingerprint 均自洽。独立遍历全部 38 项，核验 312 个
  唯一日志和 236 个唯一 object/ELF/bin identity：所有路径均位于稳定
  `.work/embench-sweep/unpatched/`，文件存在，日志末行 footer 与 JSON 的
  command/rc/timeout 完全一致，artifact size/SHA256 全部匹配。runner 自带的
  schema-2 evidence validator 对 patched/unpatched 两份 JSON 也均返回零错误。
- **L1 — Closed。** 在项目内 detached worktree 从 exact pin 构造一个只有单个
  错误 README commit 的 clean checkout；其 patch-id
  `6b26f4f0a7498f8331071662053bdb931910ebfd` 与声明 series 的
  `30ad5b77725f26549e669caf791b48487661ad1a` 不同。patched preflight 以
  “checkout commits do not match declared series patch-id order”拒绝，rc=2，
  且没有创建 checkpoint。隔离 worktree 已移除。

### 新 finding

- **Low — R1：同 identity resume 携带 `--report` 会覆盖主报告中的人工附录。**
  `write_checkpoint()` 在 resume 完成后无条件调用 `render_report()`；当前 renderer
  只生成核心结果，不生成主报告中人工追加的 “Fresh unpatched 对照”、
  “Resume 与证据一致性验证”和“整改后门禁”。隔离副本上的同 identity resume
  把报告从 185 行重写为 118 行并丢失这三个章节。漂移 resume 在写前返回，因此
  不受此问题影响；canonical 主报告也未在本次探针中修改。

  该问题不改变 patched/unpatched JSON、artifact、backend 结论或四个原 finding
  的关闭状态，故不作为 blocker。建议让报告完全由 renderer 生成、把人工内容移到
  独立 durable appendix，或在没有新增结果的 resume 中不重写既有 report。

### 复审验证

- 同 identity resume：38 个 `checkpoint exists`，rc=1，results/artifacts 不变。
- identity drift resume（`--qemu /bin/false`）：rc=2，checkpoint/report SHA256
  不变。
- patched/unpatched schema-2 evidence validator：各 38 项，零错误。
- unpatched 独立证据遍历：312 logs、236 artifacts，全部唯一且一致。
- wrong-single-commit patch-id negative control：rc=2，无 checkpoint。
- `PYTHONPYCACHEPREFIX=.work/ML-032a-rereview-20260724/pycache
  python3 -m py_compile tests/scripts/embench_sweep.py`：PASS。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：PASS（open 22 / closed 39 / total 61）。
- `git diff --check`：PASS。

最终判决：**Accepted-with-findings**。原 H1/M1/M2/L1 全部关闭；仅保留新 Low R1，
不阻断 ML-032a 接受。

## 架构师后续收口（2026-07-24）

接受并窄修 Low R1：完整矩阵的同身份 resume 不再调用 generic renderer；部分
checkpoint 在新增结果后仍会更新报告。原 review finding 与判决保留为审计历史。
整改后以当前脚本 fresh 生成 38 项 checkpoint，再带原 `--report` 做纯复用 resume：
报告 SHA256 保持不变，38 项均复用，进程仅因已知 `qrduino -O2` 返回 1。
