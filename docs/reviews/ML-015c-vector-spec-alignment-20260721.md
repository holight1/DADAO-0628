# ML-015c：ISA vector 与 spec 对齐记录

日期：2026-07-21  
范围：仅审计并最小修正 `tests/vectors/isa/*.yaml`；本次修改集中在
`control-flow.yaml` 的 cold `ret` 与合法 `rb0` control-flow。未运行 QEMU。

## 结果

向量计数（`total / active / deferred`）：

| 状态 | 修改前 | 修改后 | 变化 |
|---|---:|---:|---:|
| 总数 | 212 | 213 | +1（把 cold-ret fault 从 encoding-only 拆出独立 boundary case） |
| active | 206 | 207 | +1 |
| deferred | 6 | 6 | 0 |

class 计数：`encoding 87 → 89`、`legality 16 → 13`、`boundary 5 → 7`；
fault 计数：`ILLI 36 → 30`、`RASUF 0 → 2`、`MALIGN 1 → 1`。

## 已修改项及 spec 依据

1. `control-flow.yaml` 的两个 cold `ret`（`0x6E040000`、`0x6E000000`）：
   原来的 downstream `halt rd0` / `ILLI` 已移除。`0x6E040000` 保留为真正
   的 encoding-only 记录，并新增 boundary 执行记录；`0x6E000000` 直接改为
   boundary。两条执行记录均期望 `RASUF`，引用 `spec.md §5.6`，notes 明确
   `RASUF` precise、PC/RA 不变，不能用后续 halt 的 `ILLI` 代替。依据是
   `spec.md §5.6`：`ra63[63:48] == 0` 的 pop 唯一 fault 为 `RASUF`；并由
   `§2.6.1`确认 `ret rdha=rd0` 合法。
2. 合法 `jump rb0,...`：两个原 encoding/legality 记录都改为
   encoding-only、`expected_fault: null`，notes 标明 `§5.3` 的
   `rbha=rb0` relative-jump 特例；不再把下游 halt 的 `ILLI` 当作 jump fault。
3. 合法 `call rb0,...`：两个原 encoding/legality 记录都改为
   encoding-only、`expected_fault: null`，并将 call 引用改为 `spec.md §5.4`。
   依据是 `§5.4` 定义 `rbha` 为 call 的合法源并规定 `rbha=rb0` 的地址计算；
   该条目不证明 operand legality，也不证明 downstream fault。

## 保留、未修改的疑点

按本次“先收敛”范围未扩大修改，以下条目保留并需后续独立处理：

- 其他文件中仍有 `class: encoding` 搭配 `expected_fault: ILLI` 的执行型
  条目：`misc.yaml` 的 `unimp`，`rb-ops.yaml` 的 `sto/ldmo/stmo`，
  `rd-arith.yaml` 的 `divs/divu`，`rd-load-store.yaml` 的 store/multi-store
  条目，以及 `rd-wyde-block.yaml` 的四条 block-copy 条目。它们分别涉及
  `§6.2`、`§2.6.1/§2.6.2/§2.6.3` 或 `§3.7/§3.14` 的执行 fault/operand
  legality，不在本次 control-flow 最小修正中猜测重分类。
- `rd-load-store.yaml` 的 `ldo` 非对齐条目当前为 `class: legality`、
  `expected_fault: MALIGN`；`spec.md §3.1` 明确这是合法操作的对齐执行 fault，
  但本次不改其 class。
- `tests/vectors/schema.md` 的 class 表没有专门的 execution-fault class，且
  boundary 行示例只列 `null/ILLI`；本次以 `boundary` 表示 cold RAS 边界，保留
  `RASUF` 断言。现有 validator 对允许 fault 值与 active boundary 的
  `expected_state: {}` 检查通过；schema 语义是否需增加 execution-fault class
  留待独立 schema 任务，不在本次修改。

## 可复核命令与结果

在 `/home/holight/DADAO-0628` 执行：

```text
python3 scripts/validate_vectors.py
→ validate_vectors: 10 files, 213 cases, 87/87 opcodes covered OK

python3 scripts/validate_encoding.py tools/opcodes.yaml
→ validate_encoding: 87 records OK

python3 -c 'from pathlib import Path; import yaml; R={"mnemonic","format","class","encoding","input_state","wiki_cite"}; C={"encoding","legality","semantic","boundary","overlap"}; F={None,"ILLI","UNDI","MALIGN","IALIGN","RASOF","RASUF"}; xs=[c for p in sorted(Path("tests/vectors/isa").glob("*.yaml")) for c in (yaml.safe_load(p.read_text()) or [])]; assert all(R <= set(c) and isinstance(c["encoding"],dict) and "word" in c["encoding"] and c["class"] in C and c.get("expected_fault") in F for c in xs); assert all(c.get("status","active") != "deferred" or c.get("expected_state") is None for c in xs); assert all(c.get("status","active") != "active" or c["class"] not in {"semantic","boundary"} or c.get("expected_state") is not None for c in xs); print("schema_check: PASS")'
→ schema_check: PASS

git diff --check
→ PASS
```

未执行 QEMU、QEMU harness、LLVM、QEMU/LLVM/harness/contracts/docs/issues/wiki
相关修改，也未访问 `~/toolchain` 或 `~/knowledge-graph`。
