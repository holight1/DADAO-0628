# IN-007a：补齐 QEMU patch series 缺失历史提交

日期：2026-07-23

## 状态

已完成；独立 review 判决 **Accepted**。

## 背景

ML-025a worker 与独立 reviewer 均确认：QEMU live 历史从 manifest pin 到
`cf5c06b...` 有 21 个线性提交，component series 只有 20 条。缺失的是
`e7639ea9a84ecfd42b28d387fb5ca5383999605e`
（DL-026a divs/divu TCG label fix + machine/CPU hardening）。它在真实历史中
位于现有 0006 与 0007 之间，并创建后续 0008 所需的 `helper_exit()`。

## Ownership 与约束

- 只允许新增由 `e7639ea...` 原样导出的 QEMU patch、调整 QEMU series 中的
  文件名编号/顺序以插入正确历史位置、本任务完成区及 worker report。
- 不修改 `.work/source/qemu` 源码或历史、其它 component、测试、issues、
  roadmap、wiki。
- 不得把缺失提交合并进相邻 patch，不得改其源码 payload，不得改变后续 patch
  最终表达的 tree。

## 目标

1. 从真实提交导出 patch，在现有 0006 与原 0007 之间插入。
2. 必要时机械重编号原 0007～0020，并同步 series；内容不得变化。
3. 从 QEMU manifest pin plain `git am` 全 series，必须 21/21。
4. 最终重放 tree 与 live QEMU HEAD `cf5c06b...` 一致。
5. 运行 QEMU build、E2E、differential、manifest/issues。

## 验收

独立 reviewer 必须核对缺失 patch 的 patch-id/tree、插入位置、后续 patch
payload 未变化、21/21 replay 与最终 tree identity。

## Worker 完成区（2026-07-23）

### 结论

**Worker 目标全部达到，等待独立 review。**

- 将提交 `e7639ea9a84ecfd42b28d387fb5ca5383999605e` 用
  `git format-patch -1` 原样导出为
  `0007-target-dadao-DL-026a-divs-divu-TCG-label-fix-machine.patch`。
- 新 patch 位于原 0006 与原 0007 之间；原 0007～0020 机械顺延为
  0008～0021。
- 从 manifest QEMU pin 依次执行 plain `git am`，21/21 成功。
- 重放最终 tree 与 live QEMU `cf5c06b...` tree 完全一致。
- QEMU build、全 E2E、四方 differential、manifest/issues 均通过。

### 导出与重编号核对

新 0007：

```text
From commit:
  e7639ea9a84ecfd42b28d387fb5ca5383999605e
SHA-256:
  3663eb869e1084d7774b9a95b36dc21b008c926f7472830e998f69ecafe4c325
stable patch-id:
  3b8df92718fe88306abedb4f28187dadd46b1385
cmp against fresh `git format-patch -1 --stdout`:
  PASS
```

对每个原 0007～0020，分别将 `HEAD:<旧路径>` 与顺延后的新路径比较：
14/14 字节 SHA-256 相同，14/14 stable patch-id 相同。没有改动任何后续
patch 的邮件内容或源码 payload。

### 裸 pin 重放

临时 clone：

```text
/tmp/in-007a-qemu-replay-mFuSnb/qemu
```

基点及结果：

```text
pin:
  385b0a7d9785c8f3ac7b116d7f31d61502b55183
plain git am:
  21/21 PASS
replay HEAD:
  828f4f7eddbc6fe3d9db68503ee8f7dcb218b19b
replay tree:
  fb88a907774b33fa656e05e6f8ce3308f954d876
live cf5c06b tree:
  fb88a907774b33fa656e05e6f8ce3308f954d876
tree identity:
  PASS
```

重放 commit hash 因 `git am` 的 committer metadata 不同而与 live 历史不同；
验收比较使用 tree id。

### 构建与门禁

```text
ninja -C .work/source/qemu/build qemu-system-dadao
  PASS

.work/build/llvm/bin/llvm-lit -sv tests/lit/E2E/
  66/66 PASS

python3 tools/run_differential.py
  AGREE(3-way)=200
  AGREE(interp+QEMU, gem5-SKIP)=2
  DIVERGE=0
  AGREE(4-way)=200
  Sail-SKIP=2
  SAIL-DIVERGE=0

python3 scripts/manifest_check.py
  PASS

python3 scripts/check_issues.py
  Open=23 Closed=34 Total=57
  PASS
```

### Ownership

本 worker 只修改 QEMU patch 文件名/series，新增 e7639ea 原样 patch，更新本
任务完成区并新增 worker report。`.work/source/qemu` 保持 clean，HEAD 仍为
`cf5c06bbcf7ac0e176b7f5e52fca48868c3d03a9`。未修改其它 component、测试、
issues、roadmap、wiki 或任何源码历史；主仓未提交。

完整命令与审计重点见
`docs/reviews/IN-007a-worker-report-20260723.md`。

## 独立 review

- 报告：`docs/reviews/IN-007a-independent-review-20260723.md`
- 判决：Accepted，无 blocking/non-blocking finding。
- 独立确认新增 0007 与 `e7639ea...` fresh format-patch 字节和 patch-id
  一致；原 14 条后续 patch 仅机械顺延且 payload 不变；裸 pin 21/21
  plain `git am` 与最终 tree identity、构建和项目门禁全部通过。
