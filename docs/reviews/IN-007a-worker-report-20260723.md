# IN-007a worker report：补齐 QEMU patch series 缺失提交

日期：2026-07-23  
角色：worker（非独立 reviewer）

## 1. Worker 判决

**Worker 范围内目标全部达到，等待独立 review。**

QEMU component series 已在真实历史位置补入
`e7639ea9a84ecfd42b28d387fb5ca5383999605e` 的原样 format-patch。series
现在为 21 条；从 manifest pin plain `git am` 21/21 成功，最终 tree 与 live
`cf5c06b...` 完全一致。构建和项目门禁均通过。

## 2. 初始事实与历史位置

```text
manifest QEMU pin:
  385b0a7d9785c8f3ac7b116d7f31d61502b55183
live QEMU HEAD:
  cf5c06bbcf7ac0e176b7f5e52fca48868c3d03a9
live QEMU status:
  clean
pin..HEAD linear commits:
  21
pre-change series entries:
  20
```

live 历史相邻关系：

```text
a1b593aad627867aa50231e033633d4e16202e61  existing 0006
e7639ea9a84ecfd42b28d387fb5ca5383999605e  missing commit
e6e9df7af65225e3bbd8c247321caf9ac64735ac  original 0007
```

因此插入点严格位于现有 0006 与原 0007 之间。

## 3. 原样导出

使用 live QEMU object database：

```bash
git -C .work/source/qemu format-patch -1 \
  e7639ea9a84ecfd42b28d387fb5ca5383999605e
```

component 文件：

```text
components/qemu/patches/
  0007-target-dadao-DL-026a-divs-divu-TCG-label-fix-machine.patch
```

核对结果：

```text
first From hash:
  e7639ea9a84ecfd42b28d387fb5ca5383999605e
SHA-256:
  3663eb869e1084d7774b9a95b36dc21b008c926f7472830e998f69ecafe4c325
stable patch-id:
  3b8df92718fe88306abedb4f28187dadd46b1385
fresh format-patch stdout vs component file:
  cmp PASS
```

该 stable patch-id 与直接对提交执行 `git format-patch -1 --stdout |
git patch-id --stable` 的结果相同。

## 4. 机械重编号与 payload 审计

原 0007～0020 只调整文件名前缀，顺延为 0008～0021；`series` 同步为真实
历史顺序。未修改这些 patch 内的 `From`、metadata、diff hunk 或尾部字节。

逐项将主仓 `HEAD:<旧路径>` 与新路径比较：

```text
14/14 byte SHA-256: SAME
14/14 stable patch-id: SAME
```

修改后：

```text
series entries: 21
numbered patch files: 21
new 0007 follows 0006: PASS
original 0007 is new 0008: PASS
```

## 5. 裸 pin plain git am

为避免触碰 live QEMU，使用独立临时 clone：

```text
/tmp/in-007a-qemu-replay-mFuSnb/qemu
```

从 manifest pin detached checkout 后，严格按 `series` 对每条 patch 单独执行
普通 `git am <patch>`，未使用 3-way、reject、skip、手工 preimage 修改或
其它放宽参数。

```text
applied: 21/21
replay status: clean
replay HEAD:
  828f4f7eddbc6fe3d9db68503ee8f7dcb218b19b
replay HEAD tree:
  fb88a907774b33fa656e05e6f8ce3308f954d876
live cf5c06b tree:
  fb88a907774b33fa656e05e6f8ce3308f954d876
tree identity:
  PASS
```

`git am` 生成的新 commit hash 受 committer metadata 影响，故以 tree id 作为
最终源码等价验收。

## 6. 构建与回归

```text
ninja -C .work/source/qemu/build qemu-system-dadao
  exit 0
QEMU binary SHA-256:
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
  manifest validation: PASS

python3 scripts/check_issues.py
  Open=23 Closed=34 Total=57
  ISSUE REGISTRY: PASS
```

## 7. Ownership 与工作树

本 worker 的改动仅包括：

- 新增 e7639ea 的 QEMU patch；
- 原 QEMU 0007～0020 patch 文件机械顺延；
- 更新 QEMU `series`；
- 更新 IN-007a 完成区；
- 新增本 worker report。

未修改：

- `.work/source/qemu` 源码、commit 或历史；
- 其它 component；
- 测试；
- issues、roadmap、wiki。

结束时 `.work/source/qemu` 仍为 clean，HEAD 仍为 `cf5c06b...`。主仓未由本
worker 提交。共享工作区中并发出现的 LLVM patch 改动不属于 IN-007a，本
worker 未触碰，也未纳入本任务结论。

## 8. 交给独立 reviewer 的重点

1. 独立重新导出 `e7639ea`，核对新 0007 的 SHA-256、stable patch-id 与
   patch payload。
2. 独立确认插入点是 `a1b593a` 与 `e6e9df7` 之间。
3. 从主仓 parent 读取原 0007～0020，与新 0008～0021 做字节和 patch-id
   对照，确认 14/14 未变化。
4. 从裸 pin 独立 plain `git am` 21/21，并比较最终 tree
   `fb88a907...`。
5. 核查 `.work/source/qemu` 未被修改，且本任务未越过 ownership。
