# IN-006a worker report：LLVM patch series 裸 pin 重放修复

日期：2026-07-23  
角色：worker（非独立 reviewer）

## 1. Worker 判决

**0005 修复成功；IN-006a 全量验收被 ownership 外的 0006 格式错误阻塞。**

本轮没有宣称 48/48 完成：从 manifest pin 重放到 0005 为 5/48 成功，0006
在解析自身 mbox 时失败，最终 tree 因此不能与 `.work/llvm` HEAD 比较。

## 2. 精确根因

原始 0005 的 CMake hunk 头是：

```text
@@ -3,11 +3,13 @@ add_llvm_component_group(DADAO)
```

旧侧计数确为 11，新侧正文只有 12。正文缺少原 postimage
`08db6fd37cd6` 中的：

```text
tablegen(LLVM DADAOGenMCCodeEmitter.inc -gen-emitter)
```

所以 line 447 的删除行本身合法；实际错误是 parser 到下一个 hunk 头时仍
等待新侧第 13 行。首次只修计数后，错误前移到后续 malformed hunk，证明
0005 曾有多段序列丢失：

- InstPrinter 第二 hunk：声明旧/新 14/14，实际 8/13，并漏掉返回类型上下文；
- MCCodeEmitter 新文件：声明 77 行，实际 74 行，并漏掉生成式 encoder 相关
  声明、调用和 include。

这些缺失还会使输出无法命中 0005 自己记录的 postimage hashes。修复以原有
`index old..new`、邮件统计和对应历史提交为约束，恢复缺失序列。当前
0001～0004 产生的 `DADAO.td` preimage 另有一条多余 include 和一个缺失的
文件末尾 `}`；0005 对该 preimage 做了适配，但输出仍严格命中其原声明的
目标 tree。

## 3. 裸 pin 重放与 tree 证据

独立临时仓：

```text
/tmp/in-006a-final-replay-20260723-c8JQny/llvm
```

来源 `.work/llvm` 是 partial/promisor 仓库；首次 `--no-local` 物理复制因
缺少 promisor object `1ab2a81...` 失败。随后使用独立工作树、索引和 refs
但只读共享本地 object store 的 clone；没有修改 `.work/llvm`。

关键命令：

```bash
git clone --shared --no-checkout \
  /home/holight/DADAO-0628/.work/llvm \
  /tmp/in-006a-final-replay-20260723-c8JQny/llvm
git -C /tmp/in-006a-final-replay-20260723-c8JQny/llvm \
  checkout --detach ca7933e47d3a3451d81e72ac174dcb5aa28b59d1

git -C /tmp/in-006a-final-replay-20260723-c8JQny/llvm am \
  components/llvm/patches/0001-dadao-triple-registration.patch
# 同样按 series 顺序应用 0002、0003、0004、0005

git -C /tmp/in-006a-final-replay-20260723-c8JQny/llvm \
  diff --exit-code HEAD 79e6b7958a670ba72a76df1ef55a5e868bc33ab6
```

结果：

```text
0001..0005: PASS
replay tree:   9c62c5421eb1e9fc716b528e5304ce35d2166c9e
expected tree: 9c62c5421eb1e9fc716b528e5304ce35d2166c9e
tree diff rc:  0
```

因此修复后的 0005 生成其既有历史目标源码树；commit id 因邮件 subject 和
committer metadata 不同而不同，tree id 才是本验收使用的字节级依据。

## 4. 真实阻塞证据

继续应用 series 第 6 条：

```bash
git -C /tmp/in-006a-final-replay-20260723-c8JQny/llvm am \
  /home/holight/DADAO-0628/components/llvm/patches/0006-dadao-disassembler.patch
```

返回：

```text
Applying: DADAO Disassembler
Patch failed at 0001 DADAO Disassembler
error: corrupt patch at line 27
```

0006 line 21 的首个 hunk 声明 `@@ -0,0 +1,12 @@`，实际 line 22～31 只有
10 条新增行，line 32 已进入下一个 `diff --git`。这是 0006 独立格式错误，
不是 0005 的上下文或源码冲突。IN-006a ownership 禁止修改其它 patch，
因此 worker 未修复、跳过或放宽应用参数。

结论：48/48、最终 tree 与 `4b812d2f...` 的比较均未执行成功，应由架构师
另开 0006（并建议扫描后续 patch）的 repair 任务。

## 5. 其它检查与边界

```text
python3 scripts/manifest_check.py
  manifest validation: PASS

git -C .work/llvm status --short
  empty

git -C .work/llvm rev-parse HEAD
  4b812d2f99305a259a3d37a827d67c6c1ae14546
```

本 worker 修改：

- `components/llvm/patches/0005-dadao-asmparser.patch`
- `code-agent/tasks/IN-006a-llvm-patch-series-full-replay-repair.md` 完成区
- `docs/reviews/IN-006a-worker-report-20260723.md`

未修改 `.work/llvm`、其它 patch、series、issues、roadmap、wiki、测试或其它
component。主仓中的其它并发改动不属于 IN-006a，本 worker 未纳入或改写。

## 6. 独立 reviewer 重点

1. 从 pin 独立应用 0001～0005，并核对 tree id `9c62c542...`。
2. 核对修复前 patch 的 postimage hashes 确实定义同一目标源码树。
3. 独立复现 0006 line 27 corrupt，确认不是 0005 上下文冲突。
4. 在 48/48 未完成前保持任务/issue 开放。
