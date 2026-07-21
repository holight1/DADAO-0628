# ML-015a LLVM + QEMU fresh baseline review

日期：2026-07-21  
范围：DADAO-0628 当前工作树的 QEMU 重编、裸金属 ISA harness 和 LLVM E2E 入口。  
限制：本轮未访问 `~/toolchain` 或 `~/knowledge-graph`；未修改 LLVM、QEMU、gem5、kernel、contracts、docs/issues、wiki，也未修改 `code-agent/tasks/ML-014a-musl-e2e-malloc-printf.md`。

## 结论

这是一次 fresh 验证，不是历史结果的重述。QEMU 在当前 `0019` 应用结果上重新编译成功（rc=0）。指定的目录级 ISA harness 入口在执行 case 前因脚本不支持目录参数而失败（rc=1）；按同一 harness 对 10 个 YAML 文件逐文件运行后，206 个 active case 的 fresh 分类为 **204 PASS / 2 FAIL / 0 SKIP / 0 timeout**。两个 FAIL 都是 control-flow 向量预期 `ILLI`，实际得到 `RASUF`（0x85）。

LLVM E2E 命令已启动，但本轮被用户在约 0.1 秒后中断；工具没有产生数值 rc，且事后没有残留 `llvm-lit` 进程。因此本报告不填写伪造的 fresh E2E 总数，也不把历史 59/59 或历史 203 PASS 当作本轮结果。

## 0019 与 QEMU 源码来源

真实检查命令及结果：

```text
cat components/qemu/patches/series
→ 最后一项为 0019-dadao-cfx-state-scaffold.patch

git -C .work/source/qemu rev-parse HEAD
→ ac58f31acddc7f583e5087002df100297f2f87f9

git -C .work/source/qemu apply --reverse --check \
  /home/holight/DADAO-0628/components/qemu/patches/0019-dadao-cfx-state-scaffold.patch
→ rc=0

git -C .work/source/qemu status --short --untracked-files=all
→ M target/dadao/cpu.c
  M target/dadao/cpu.h

git -C .work/source/qemu diff --check
→ rc=0
```

源码中的 `inner_run_mode`、`inner_cfx_code`、`inner_cfx_mask`、`cfx_power_frame` 及 reset 初值均存在；反向 apply check 通过，说明当前源码是 0019 的应用结果。源码树的 dirty 状态只显示该 patch 预期的两个文件。

QEMU 来源信息：

```text
git -C .work/source/qemu describe --always --dirty
→ v10.0.0-19-gac58f31-dirty

git -C .work/source/qemu log -1 --format='%H%n%ad%n%s' --date=iso-strict
→ ac58f31acddc7f583e5087002df100297f2f87f9
  2026-07-18T12:40:25+08:00
  target/dadao: add mmap arena host backing (ML-014c)

.work/source/qemu/build/qemu-system-dadao --version
→ QEMU emulator version 10.0.0 (v10.0.0-19-gac58f31), rc=0
```

## QEMU 重编

构建系统 inventory 确认 `qemu-system-dadao` 是当前 Ninja target。实际执行：

```text
ninja -C .work/source/qemu/build qemu-system-dadao
→ rc=0
→ [1/35] ...
  [4/35] Compiling C object libqemu-dadao-softmmu.a.p/target_dadao_cpu.c.o
  ...
  [35/35] Linking target qemu-system-dadao
```

构建输出有现存的 C 原型 warning（`cpu_get_tb_cpu_state`、`dadao_cpu_has_work`，以及相关 implicit declaration/nested extern warning），没有阻断构建。

## 裸金属 ISA harness

按任务要求执行的原始命令：

```text
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/
→ rc=1
→ Traceback ...
  AttributeError: 'str' object has no attribute 'get'
```

该入口在 `run_qemu_test.py` 把目录参数当成 YAML 字符串后，在第一个 case 构建前退出，没有产生自身的 PASS/FAIL 汇总。只读 inventory 显示 10 个 YAML 文件、212 个向量，其中 206 active、6 deferred。

为取得可审计分类，使用现有 harness 对每个 YAML 文件逐一执行（未改脚本、未改向量）：

```text
for f in tests/vectors/isa/*.yaml; do
  python3 tests/scripts/run_qemu_test.py "$f"
  rc=$?
  printf 'file_rc=%s\\n' "$rc"
done
→ active 总数=206
→ PASS=204, FAIL=2, SKIP=0, timeout=0
→ 仅 control-flow.yaml 非零（file_rc=1）；其余 9 个文件 file_rc=0
```

两个 fresh FAIL：

```text
FAIL expected ILLI exit=0x82, got 0x85
    encoding-only: RA stack cold=0 → jump to addr=0 → halt rd0 → ILLI

FAIL expected ILLI exit=0x82, got 0x85
    ret rd0,0; RA=0 → jump to addr=0 → halt rd0 → ILLI
```

这里的 0x85 是 `RASUF`。本轮只记录现象，没有越界修改 QEMU 或向量。

## LLVM / E2E

LLVM 构建来源先以真实命令记录：

```text
PATH=.work/build/llvm/bin:$PATH llvm-lit --version
→ lit 22.1.8dev, rc=0

PATH=.work/build/llvm/bin:$PATH clang --version
→ clang version 22.1.8
  https://github.com/llvm/llvm-project.git 1697be42b5b13cf468043ec8bf9fc612fec17a33
  InstalledDir: /home/holight/DADAO-0628/.work/build/llvm/bin
  Build config: +assertions
```

按任务要求执行的 full E2E 原始命令：

```text
PATH=.work/build/llvm/bin:$PATH llvm-lit -v tests/lit/E2E/
→ tool-level aborted by user after 0.1s；未产生数值 rc
→ 事后检查无残留 llvm-lit/lit.py 进程
```

因此：本轮没有可报告的 full E2E 总数，也没有独立启动 `tests/lit/E2E/llvm-test-suite/` 的 23 个用例；不得将历史 59/59 写成本轮 fresh 结果。full upstream `llvm-test-suite` 和 `gcc-c-torture` 也尚未启动，符合本任务范围约束。

## Fresh 与历史基线边界

- 本轮 fresh QEMU build：成功，rc=0。
- 本轮 fresh ISA：206 active，204 PASS、2 FAIL、0 SKIP、0 timeout；目录入口本身另有脚本参数错误 rc=1。
- 历史记录中的 **59/59** 是此前 full E2E 结果，不是本轮结果；本轮 E2E 被中断，不能复用该数字。
- 历史记录中的 **203 PASS** 是历史 QEMU ISA/vector 基线，不是本轮 206 active 的 fresh 分类；本轮应以实际 204/206 + 2 FAIL 记录。

## Open boundary

扩大测试前仍保留 tail-call lowering 缺口，以及 varargs 的 RB pointer save-area/ABI 边界；本轮没有启动 full upstream llvm-test-suite 或 gcc-c-torture，也没有尝试关闭这些 open boundary。
