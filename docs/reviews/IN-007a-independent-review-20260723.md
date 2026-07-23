# IN-007a 独立审查：QEMU patch series 缺失提交

日期：2026-07-23  
角色：独立 reviewer

## 判决

**Accepted**

无 blocking finding。IN-007a 的 QEMU patch series 修复满足任务验收条件：
缺失提交被原样插回真实历史位置，原有后续 patch 只有机械重编号，从 manifest
pin 执行普通 `git am` 21/21 成功，最终 tree 与 live QEMU
`cf5c06bbcf7ac0e176b7f5e52fca48868c3d03a9` 完全一致；构建和项目门禁均通过。

本结论来自独立复核，不采信 worker 报告中的预设判决。

## 1. 审查范围

完整读取并核对：

- `code-agent/tasks/IN-007a-qemu-patch-series-missing-commit.md`
- `docs/reviews/IN-007a-worker-report-20260723.md`
- `components/qemu/patches/series` 当前 diff
- 新增 0007 的完整邮件 patch 和源码 payload
- 主仓 `HEAD` 中旧 0007～0020 与当前新 0008～0021
- manifest QEMU pin、live QEMU 提交关系及当前组件状态

共享工作区中的并发 LLVM patch 改动不属于本任务，未纳入 IN-007a 判决，也未
触碰。

## 2. 新增 0007 的身份与历史位置

目标提交：

```text
e7639ea9a84ecfd42b28d387fb5ca5383999605e
parent: a1b593aad627867aa50231e033633d4e16202e61
tree:   8ae97d3ec9073e11dc8c30d107867880360d0bc3
```

live 历史中的下一提交为：

```text
e6e9df7af65225e3bbd8c247321caf9ac64735ac
parent: e7639ea9a84ecfd42b28d387fb5ca5383999605e
```

因此新 patch 位于原 0006 与原 0007 之间，series 插入位置正确。

独立执行 fresh `git format-patch -1 --stdout e7639ea...` 并与组件文件比较：

```text
cmp:            PASS（逐字节相同）
SHA-256:        3663eb869e1084d7774b9a95b36dc21b008c926f7472830e998f69ecafe4c325
stable patch-id: 3b8df92718fe88306abedb4f28187dadd46b1385
```

组件文件和真实提交导出的 fresh patch 的 SHA-256、stable patch-id 均一致，
未发现 payload 或邮件 metadata 改写。

## 3. 原 0007～0020 机械重编号

从主仓 `HEAD:components/qemu/patches/series` 读取旧序列，并逐项将旧
0007～0020 与当前新 0008～0021 比较：

```text
旧 entries:             20
新 entries:             21
后续 patch 字节相同:    14/14
后续 stable patch-id 同: 14/14
```

所有 14 个后续 patch 的完整文件 SHA-256 和 stable patch-id 均逐项相同。
除了文件名前缀顺延及 series 同步，未发现 metadata、diff hunk、尾部字节或
源码 payload 变化。

## 4. manifest pin 裸重放与 tree identity

manifest QEMU pin：

```text
385b0a7d9785c8f3ac7b116d7f31d61502b55183
```

在独立临时 clone 中 detached checkout 到该 pin，严格按当前 `series` 逐条执行：

```text
git am <patch>
```

未使用 `--3way`、reject、skip、手工 preimage 修订或其它放宽方式。

结果：

```text
plain git am: 21/21 PASS
replay status: clean
replay HEAD: dcf3da8ec499cc181e6616b441cade8da00c3bd6
replay tree: fb88a907774b33fa656e05e6f8ce3308f954d876
cf5c06b tree: fb88a907774b33fa656e05e6f8ce3308f954d876
tree identity: PASS
```

重放 commit id 因 committer metadata 不同而变化，不影响 tree identity
验收。

## 5. 构建与项目门禁

独立执行结果：

```text
ninja -C .work/source/qemu/build qemu-system-dadao
  PASS

QEMU binary SHA-256
  46408ebc810005cb0a579e57febb5e97c04ae0a049eaa2eb81a97f632e9556be

.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/
  66/66 PASS

python3 tools/run_differential.py
  AGREE(3-way)=200
  AGREE(interp+QEMU, gem5-SKIP)=2
  DIVERGE=0
  AGREE(4-way)=200
  Sail-SKIP(out-of-slice)=2
  SAIL-DIVERGE=0

python3 scripts/manifest_check.py
  PASS

python3 scripts/check_issues.py
  Open=23 Closed=34 Total=57
  PASS
```

live QEMU 保持：

```text
HEAD: cf5c06bbcf7ac0e176b7f5e52fca48868c3d03a9
tree: fb88a907774b33fa656e05e6f8ce3308f954d876
status: clean
```

## 6. Findings

### Blocking

无。

### Non-blocking

无 IN-007a 范围内的非阻塞 finding。

主仓仍有其它并发任务产生的未提交改动；它们不改变本次 QEMU patch
identity、重放、tree identity 和门禁结论，后续集成提交时仍应按任务 ownership
分别收口。
