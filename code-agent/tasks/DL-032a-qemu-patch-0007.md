# DL-032a: QEMU patch 0007（branch PC 公式 + call RA 修复）

**执行环境**: 本地 DS · DADAO-0628

**状态**: 待执行

---

## 背景

当前状态：
- `.work/source/qemu` git HEAD = `e7639ea`（DL-026a，含 machine/cpu/helper/halt/divs-divu 修复）
- `.work/source/qemu/target/dadao/translate.c` 有 **未提交修改**（`git status -s` 显示 `M translate.c`）

这些未提交修改包含两处关键修复：
1. **分支 PC 公式**（DL-028a）：not-taken `pc_next → pc_next+4`；taken `pc_next-4 → pc_next+4`（全部条件分支 trans_brz/brnz/brn/brnn/brp/brnp/breq/brne）
2. **call 返回地址**（DL-030a）：`ra[63] = pc_next → ra[63] = pc_next+4`（trans_call_i + trans_call_r）

当前测试套件 137/137 PASS 依赖这些修改，但它们还不在 patch series 里。

---

## 目标

1. 将 translate.c 未提交修改提交到 `.work/source/qemu` git（新 commit：`DL-028a/030a branch PC formula + call RA fix`）
2. 用 `git format-patch` 导出为 `components/qemu/patches/0007-dadao-branch-call-fix.patch`
3. 更新 `components/qemu/patches/series` 加入 0007

---

## 接口说明书

### 1. 提交到 QEMU git

```bash
cd .work/source/qemu
git add target/dadao/translate.c
git commit -m "target/dadao: DL-028a/030a branch PC formula + call RA fix

- Conditional branches (brz/brnz/brn/brnn/brp/brnp/breq/brne):
  not-taken: pc_next → pc_next+4 (was re-executing branch)
  taken: pc_next-4+imm*4 → pc_next+4+imm*4 (DADAO offset from PC+4)
- call_i/call_r: ra[63] = pc_next → pc_next+4 (return after call)

Validated: 137/137 test vectors PASS"
```

### 2. 导出 patch

```bash
cd .work/source/qemu
git format-patch HEAD~1..HEAD \
  --output=../../components/qemu/patches/0007-dadao-branch-call-fix.patch
```

验证 patch 包含 `translate.c` 中的以下模式：
- `pc_next + 4` 在 not-taken 路径出现 ≥6 次
- `pc_next + 4 + (int64_t)` 在 taken 路径出现 ≥6 次
- `ra[63]` 两处改为 `pc_next + 4`

### 3. 更新 series 文件

在 `components/qemu/patches/series` 末尾追加：
```
0007-dadao-branch-call-fix.patch
```

### 4. 验证 patch 可正向应用

对新 checkout 或 --dry-run 验证（可选，不强求）：
```bash
cd .work/source/qemu
git stash   # stash current HEAD
git am --dry-run ../../components/qemu/patches/0007-dadao-branch-call-fix.patch
git stash pop
```

---

## 约束

- 仅操作 `.work/source/qemu` git 和 `components/qemu/patches/`，不修改 DADAO-0628 主仓库源码
- DADAO-0628 主仓库的 commit 在本任务完成后由架构师统一处理（DS 不做主仓库 git 操作）
- 验收后确认 137/137 仍 PASS（qemu-system-dadao 是 in-tree build，改完重新跑测试）

---

## 验收

```bash
cat components/qemu/patches/series           # 末尾有 0007
head -5 components/qemu/patches/0007-*.patch # 有 From: + Subject:
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/control-flow.yaml
# 37/37 PASS (QEMU 重新 build 后)
```

---

## 参考指针

- 知识库 §1.2-§1.3（branch/call 公式）
- QEMU git：`.work/source/qemu`（HEAD = e7639ea）
- 已有 patch 格式参考：`components/qemu/patches/0006-dadao-ctrl-flow.patch`

---

## 完成区

**状态**：已完成
**修改文件**：
  - `.work/source/qemu` — commit e6e9df7 (branch PC + call RA fix)
  - `components/qemu/patches/0007-dadao-branch-call-fix.patch` — 从 commit 导出
  - `components/qemu/patches/series` — 追加 0007 行
**验证**：patch 含 pc_next+4 模式 20 处 + ra[63] 模式 7 处；control-flow 37/37 PASS
**遗留问题**：无

---

## Architecture Review — 代码级 (2026-06-30)

**评审结论**：**Accepted — Patch 0007 正确导出，series 更新，27 处修复模式完整。**

### 验证

```
patch: 9082 bytes, components/qemu/patches/0007-dadao-branch-call-fix.patch ✅
series: 7 patches (0001–0007) ✅
```

### Patch 内容检查

| 模式 | 计数 | 含义 |
|------|------|------|
| `pc_next + 4` | ≥6 (branch not-taken) | not-taken 路径 +4 跳转修正 |
| `pc_next + 4 + imm*4` | ≥6 (branch taken) | taken 路径 PC-relative 修正 |
| `ra[63] = pc_next+4` | ≥2 (call_i/call_r) | 返回地址压栈修正 |
| 总数 | **27** | 全覆盖 ✅ |

### 验证

```
control-flow 37/37 PASS (patch 启用后)
```

### 最终判断

Patch 正确导出，DL-028a/030a 的 translate.c 修改现在可复现。可 accept。
