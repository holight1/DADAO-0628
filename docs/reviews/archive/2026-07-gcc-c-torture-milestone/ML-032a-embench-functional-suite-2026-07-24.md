# ML-032a: Embench-IoT 19 项功能测试报告

生成时间（UTC）：`2026-07-24T07:52:31+00:00`。

## 范围与判定契约

本报告只陈述锁定 Embench source、当前 DADAO 工具链和两个功能模型下的 correctness 结果，不是 Embench speed/size 分数，也不是跨后端或硬件性能结论。
`WARMUP_HEAT=0`、`GLOBAL_SCALE_FACTOR=1`；每项仍执行一次 `benchmark()`，随后由 upstream `verify_benchmark()` 判定，`support/main.c` 仅在验证为真时返回 0。

每个源文件、`support/main.c`、`support/beebsc.c` 与项目内 `tests/embench/boardsupport.c` 分别编译；随后以项目 musl `crt1.o`/`libc.a` 静态链接。同一 ELF 交给 gem5 SE，objcopy 后 flat binary 交给 QEMU `dadao-m1`。工具缺失、未运行、超时和任一非零退出均不会计为 PASS。

## 锁定输入与工具

| 项 | 身份 |
|---|---|
| Embench | `https://github.com/embench/embench-iot.git` @ `25e4e8a5f03578ff46832788cf5feae0dc180cc7`; pin `09c2ed8c3b7008c95d08b038de4a3f6dc103ed70`; tree `7e1569deeb5b03ef52a3be1ab217310c097de251`; mode `patched`; patches `1` |
| gem5 source HEAD | `1da944e05a5f2653345895ce04a575b635816a65` |
| llvm source HEAD | `86656a44524167b605274b616906f8d432563f6e` |
| musl source HEAD | `f6ba5f43b337ae9df767417086eed59711551f23` |
| qemu source HEAD | `79ee086d6d99f443b3bdce184f518f914c826ca0` |
| clang | `.work/build/llvm/bin/clang`; sha256 `0f3f42acb38b294f51d71ddf4df8c1f3832c4f04cbddd0dc5c5ea2ba7ba5fc1f` |
| gem5 | `.work/source/gem5/build/DADAO/gem5.opt`; sha256 `e150f312e32891e5d4e523cdae0ad34cf4d4f092370e4c916f8a0ef6c0f22b66` |
| ld.lld | `.work/build/llvm/bin/ld.lld`; sha256 `f228460d38390f83a9e7d5f3f21523066e302d221f05ca39deb75d75bed50560` |
| llvm-objcopy | `.work/build/llvm/bin/llvm-objcopy`; sha256 `5c9bf789fb09e7fd01474f7c546da76e0b4e9d8d5697c42357e57e4e7f50f38a` |
| qemu | `.work/source/qemu/build/qemu-system-dadao`; sha256 `58b74666b2b1ac393510c61196b66be0a02e5316febb57968268a5a3bd444cd4` |
| board_glue | `tests/embench/boardsupport.c` |
| gem5_se | `.work/source/gem5/tests/dadao/dadao_se.py` |
| linker_script | `tests/scripts/dadao.ld` |
| musl_crt1 | `.work/build/musl/lib/crt1.o` |
| musl_libc | `.work/build/musl/lib/libc.a` |
| trampoline | `tests/scripts/trampoline.bin` |
| execution fingerprint | `fed694160161c4a65963630bc5095b2efc8fcc5809f24cf54941d5152ae968f5` (sha256) |
| musl crt1 | `.work/build/musl/lib/crt1.o`; sha256 `a4b06df6929dc44d48afb36d80774d79b54438ad75f44f3d9879aeb0c83f4b50` |
| musl libc | `.work/build/musl/lib/libc.a`; sha256 `0708f4e8dc359254bb08cc1de948690e01e86662af363ef483affa114fb5f61f` |

fingerprint identity 是 canonical JSON 的 SHA256，覆盖 schema、19 项 inventory、
O0/O2、Embench repository/pin/HEAD/tree/source mode、series 文件内容、每个 patch
的 SHA256 与 stable patch-id、实际 checkout commit patch-id、sweep 脚本、board
glue、linker script、trampoline、gem5-SE、support source、五个工具、各 source
HEAD、musl crt1/libc、四个 include directory 内容、编译/链接/运行契约、timeout
以及 source/out/JSON 路径。resume 在读取结果后、修改任何旧 metadata 前比较完整
fingerprint；缺失、损坏或漂移均 rc=2 且不写 checkpoint。

## 组件 patch series

- series sha256：
  `89d0ac6146fd0f5c14827cb8a37b5f12e085ab890fb0f39c0574bcff2c77d739`。
- series patch-id 与 checkout commit patch-id 均为
  `30ad5b77725f26549e669caf791b48487661ad1a`；runner 按顺序逐项比较，不再只检查
  pin 祖先关系和提交数量。
- `0001-md5sum-decode-message-words-as-little-endian.patch`
  - 将消息 bit length 从 host-native `memcpy` 改为 4 个显式 little-endian byte store。
  - 将消息块的 native `uint32_t *` load 改为 16 个显式 little-endian word decode。
  - benchmark 输入、算法轮次与 `RESULT` 均未修改。

## Fresh unpatched 对照

使用精确 pin 的 detached project worktree fresh 重生：

`/usr/bin/python3 tests/scripts/embench_sweep.py --source-mode unpatched --source .work/source/embench-unpatched-ML-032a --out .work/embench-sweep/unpatched --json .work/embench-sweep/unpatched-results.json`

canonical JSON 为 `.work/embench-sweep/unpatched-results.json`，sha256
`19b93c5c16cdae9508b4bfe8572a0f01c53280b2ff73601fc417f9612494fa86`，
execution fingerprint
`02a5988ad6226eb6bfa7bdea6b2fec6f750360a9ada014dd7cf072ee3df5b770`。
其 `metadata.json_path` 和 invocation 与实际命令一致；312 个阶段日志及 236 个
object/ELF/bin identity 全部引用 `.work/embench-sweep/unpatched/` 内现存文件，
sha256/size 均匹配，日志末尾的机器 footer 与 JSON command/rc/timeout 逐项一致。
旧失配 JSON 保留为
`.work/embench-sweep/unpatched-results.pre-rectification.json`，不再作为证据。

| 优化 | backend | PASS | FAIL | TIMEOUT | NOT_RUN |
|---|---|---:|---:|---:|---:|
| -O0 | QEMU | 18 | 1 (`md5sum`) | 0 | 0 |
| -O0 | gem5 | 18 | 1 (`md5sum`) | 0 | 0 |
| -O2 | QEMU | 17 | 2 (`md5sum`, `qrduino`) | 0 | 0 |
| -O2 | gem5 | 17 | 2 (`md5sum`, `qrduino`) | 0 | 0 |

## 执行命令

`/usr/bin/python3 tests/scripts/embench_sweep.py --out .work/embench-sweep/rectified-final --report docs/reviews/ML-032a-embench-functional-suite-2026-07-24.md`

编译契约：`clang --target=dadao -std=c99 -nostdinc -ffreestanding -O{0,2} -DWARMUP_HEAT=0 -DGLOBAL_SCALE_FACTOR=1` 加 musl/support/benchmark include；链接契约：`ld.lld -T tests/scripts/dadao.ld --start-group crt1.o <objects> libc.a --end-group`。

每项有界 timeout（秒）：compile `120.0`、link/objcopy `60.0`、QEMU `60.0`、gem5 `180.0`。每完成一项即写 JSON/Markdown checkpoint；中断中的项目不会记录为 PASS。

## 汇总

下表统计 QEMU 优先的 primary status；它用于保持单一总状态，不是后端失败计数。

| 优化 | PRIMARY_PASS | PRIMARY_FAIL_COMPILE | PRIMARY_FAIL_LINK | PRIMARY_FAIL_QEMU | PRIMARY_FAIL_GEM5 | PRIMARY_TIMEOUT_QEMU | PRIMARY_TIMEOUT_GEM5 | TOTAL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| -O0 | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 19 |
| -O2 | 18 | 0 | 0 | 1 | 0 | 0 | 0 | 19 |

### 独立 backend 汇总

| 优化 | backend | PASS | FAIL | TIMEOUT | NOT_RUN | TOTAL |
|---|---|---:|---:|---:|---:|---:|
| -O0 | qemu | 19 | 0 | 0 | 0 | 19 |
| -O0 | gem5 | 19 | 0 | 0 | 0 | 19 |
| -O2 | qemu | 18 | 1 | 0 | 0 | 19 |
| -O2 | gem5 | 18 | 1 | 0 | 0 | 19 |

## 逐项结果

| 优化 | benchmark | primary status（QEMU 优先） | QEMU | gem5 | 初步诊断 |
|---|---|---|---|---|---|
| -O0 | `aha-mont64` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `crc32` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `depthconv` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `edn` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `huffbench` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `matmult-int` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `md5sum` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `nettle-aes` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `nettle-sha256` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `nsichneu` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `picojpeg` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `qrduino` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `sglib-combined` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `slre` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `statemate` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `tarfind` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `ud` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `wikisort` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O0 | `xgboost` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `aha-mont64` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `crc32` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `depthconv` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `edn` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `huffbench` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `matmult-int` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `md5sum` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `nettle-aes` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `nettle-sha256` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `nsichneu` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `picojpeg` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `qrduino` | FAIL_QEMU | FAIL (rc=1) | FAIL (rc=1) | QEMU rc=1 (nonzero verify/runtime exit); gem5 rc=1 |
| -O2 | `sglib-combined` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `slre` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `statemate` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `tarfind` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `ud` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `wikisort` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |
| -O2 | `xgboost` | PASS | PASS (rc=0) | PASS (rc=0) | verify_benchmark true on both backends |

## 失败与遗留风险

- `-O2 qrduino`: primary status 因 QEMU 优先而为 FAIL_QEMU，但独立 backend
  统计明确记录 QEMU FAIL=1、gem5 FAIL=1；两者 rc=1，均非 timeout。既有诊断
  将首个差异定位为 `strinbuf[1]` actual 6 / expected 101，且只有把
  `qrencode.c` 降为 O0 才恢复双后端通过。证据仍不足以安全修改 benchmark，
  因此保持 FAIL 并建议独立 optimizer/backend 任务。
- 上游 pin 的 `xgboost/verify_benchmark()` 使用 `SAMPLES_IN_FILE * (LOCAL_SCALE_FACTOR, GLOBAL_SCALE_FACTOR / 12)`；在本任务规定的 `GLOBAL_SCALE_FACTOR=1` 下阈值为 0。故 xgboost 的 PASS 只证明 body 已执行且 upstream verifier 返回真，不能单独证明预测准确率；本任务未修改 verifier/expected value。

## Resume 与证据一致性验证

- 同身份 resume：rc=1（因已知 qrduino FAIL），38 行 `checkpoint exists`；
  results canonical hash 前后均为
  `8d662025be9a92c4dcfa4f9b00cc143f927f7e67e32d9630cc776bcf8aec7ddb`，
  O0/O2 文件 size+mtime 集合 hash 前后均为
  `23e6dededd6831e180b28efc9572b808dd886082896b11a06ebb3b119934e292`，
  证明仅复用且未重跑。
- 漂移 resume：加 `--qemu /bin/false` 后 rc=2；stored fingerprint
  `fed69416…` 与 current `4edce1d0…` 不同。JSON sha256 前后均为
  `5f49417ae0458c803eadaf48a18aa39e0bdd337651ae321fe34208604519bb08`，
  当时报告 sha256 前后均为
  `b9ab41dbbc1332b87222e84cf2904a6cf1d04a87cbb5626e7e9732296ccfb56b`；
  旧身份没有被当前 metadata 覆盖。
- schema-2 validator 要求每个 backend 的 attempted/state/timed_out/returncode
  自洽，并从 QEMU 优先规则重新推导 primary status；同时核验 compile/link/
  objcopy/QEMU/gem5 日志 footer 和 object/ELF/bin identity。final 与 unpatched
  两份 38 项 JSON 均通过。

## 整改后门禁

- `python3 -m py_compile tests/scripts/embench_sweep.py`：PASS。
- `python3 scripts/manifest_check.py`：PASS。
- `python3 scripts/check_issues.py`：PASS（open 22 / closed 39 / total 61）。
- `git diff --check`：PASS。
- `PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/`：
  76 discovered / 76 PASS / 0 FAIL / 0 unsupported。

机器可读证据：`.work/embench-sweep/rectified-final/results.json`；产物与日志目录 `.work/embench-sweep/rectified-final`（不提交大产物）。
