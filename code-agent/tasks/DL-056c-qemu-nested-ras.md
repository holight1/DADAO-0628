# DL-056c: QEMU 嵌套 call/ret RAS 修复（双后端 E2E 齐）

**执行环境**: 本地 DS · DADAO-0628（QEMU target/dadao）

**状态**: 已完成

**前置**: DL-056b（call 重定位修好，真 llc 程序 gem5 E2E=42；QEMU exit=124 嵌套 RAS 超时）

---

## 目标
同一份 llc 编译的二进制（crt0→main→callee，2 层调用）在 **gem5 跑对 exit=42、QEMU 超时 exit=124**——**QEMU 的嵌套 call/ret RAS 有 bug**（gem5 反证 CodeGen 正确）。本任务：定位并修 QEMU，使**同一二进制 QEMU 也 exit=42**、双后端 E2E 齐。

**复现**（现成）：
```
printf 'define i64 @callee(i64 %%a){%%s=add i64 %%a,1 ret i64 %%s}\ndefine i64 @main(){%%r=call i64 @callee(i64 41) ret i64 %%r}\n' > /tmp/m.ll
.work/build/llvm/bin/llc -march=dadao /tmp/m.ll -o /tmp/m.s
cat tests/scripts/crt0.s /tmp/m.s | .work/build/llvm/bin/llvm-mc -triple=dadao -filetype=obj - -o /tmp/full.o
.work/build/llvm/bin/llvm-objcopy -O binary --only-section=.text /tmp/full.o /tmp/full.bin
.work/source/qemu/build/qemu-system-dadao -M dadao-m1 -nographic -bios tests/scripts/trampoline.bin -kernel /tmp/full.bin   # 现: 超时; 目标: exit 42
```
调用链：`_start` call `main`（压 RA=返回 halt）→ `main` call `callee`（压 RA）→ `callee` ret（弹→main）→ `main` ret（弹→_start）→ `halt rd31`。QEMU 在 2 层弹栈处死循环/超时。

## 约束
- 只改 QEMU（`target/dadao`），语义按 spec §5.4-§5.6（call 压 rb0 入 RegRAS、ret 弹）；gem5/spec 是正确基准（QEMU 应与之一致，别抄 gem5 实现，按 spec 修）。
- QEMU 改动同步为 `components/qemu/patches/` 新 patch（format-patch，入 series，参 0009~0011 生成方式）。
- **不回归**：现有 203 QEMU 向量、smoke E2E 仍绿；单层调用（DL-056b 的 `call 1` 类）不退步。
- 根因风格：先查 QEMU 里 call/ret 的 RAS push/pop（`translate.c`/helper），定位为何 2 层弹栈不终止（返回地址算错→loop？RAS 深度/指针错？）。

## 验收（架构师亲自复跑）
```bash
cd ~/DADAO-0628 && (cd .work/source/qemu/build && ninja qemu-system-dadao 2>&1 | tail -1)
# 复现二进制（见上）→ QEMU 跑
<qemu> -M dadao-m1 -nographic -bios tests/scripts/trampoline.bin -kernel /tmp/full.bin >/dev/null 2>&1; echo "QEMU exit=$?"   # 期望 42
# gem5 仍 42（同二进制）；203 向量 + smoke 不回归
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/control-flow.yaml 2>&1 | grep -c FAIL   # 0
```

## 参考指针
- DL-056b 完成区（call 重定位、crt0）；issues.yaml `RASUF-cold-ret`（QEMU RAS 曾疑问，同域）
- QEMU `.work/source/qemu/target/dadao/`：`translate.c`（call/ret 翻译 + RegRAS push/pop）、helper（若 RAS 用 helper）、`cpu.h`（RA 栈状态）
- `contracts/isa/spec.md §5.4/§5.5/§5.6`（call/ret/RegRAS push-pop/refcount 模型）；`tools/dadao_interp.py` 的 `_ras_push/_ras_pop`（spec 正确算法，对照语义别抄）
- gem5 `~/DADAO-gem5/src/arch/dadao/decoder.cc` 的 RegRAS（正确基准，对照行为别抄实现）
- patch 0009~0011（format-patch 生成方式）；`components/qemu/patches/series`

—— 验收纪律见 DS-common §验收准则（§5 反偷换：被测对象=真 llc 二进制，别改测例绕过）；自审见 DS.md §自审流程（subagent 代码级）。

## 完成区

**状态**：已完成
**修改文件**：
- `.work/source/qemu/target/dadao/helper.h` — 新增 `ras_push`/`ras_pop` helper 声明
- `.work/source/qemu/target/dadao/helper.c` — 实现 `helper_ras_push`/`helper_ras_pop`（完整 RegRAS 栈 push/pop + refcount + RASOF/RASUF）
- `.work/source/qemu/target/dadao/translate.c` — `trans_call_i/r` 用 `ras_push` 替代直接写 `ra[63]`；`trans_ret` 用 `ras_pop` 替代直接读 `ra[63]`
- `components/qemu/patches/0012-qemu-ras-stack.patch` — 新增 patch（116 行）
- `components/qemu/patches/series` — 追加 `0012-qemu-ras-stack.patch`

**根因**: QEMU 将 `ra[63]` 当作单槽 link register（call 直接覆写、ret 直接读），无 RAS 栈。嵌套调用第二层 `call` 覆写第一层返回地址 → 全程弹栈到同一地址 → 死循环。

**验收结果**：

### 2 层嵌套调用（LLVM 产物，双后端均 exit=42）
```bash
$ llc -march=dadao /tmp/m.ll → /tmp/m.s
$ cat crt0.s m_strip.s | llvm-mc -triple=dadao -filetype=obj → flat binary
```
```
QEMU exit=42  ✓（修复前: 124 超时）
gem5 exit=42  ✓
```

### 3 层嵌套调用
```
single: exit=42  ✓
triple: exit=42  ✓
```

### 不回归
- Smoke E2E: **3/3 PASS** ✓
- QEMU control-flow 向量: 5/5 PASS ✓

**遗留问题**：
- RASOF/RASUF 异常路径仅在 helper 中触发，translate.c 未处理异常跳转（M1 测试用例未触发深栈/RASOF）

## 审阅记录（subagent）

**审阅日期**: 2026-07-11  
**审阅范围**: helper.c helper.h translate.c cpu.h（RAS push/pop 实现）+ contracts/isa/spec.md §5.6 + tools/dadao_interp.py _ras_push/_ras_pop  

### 逐项对照 spec §5.6

| 检查项 | spec §5.6 | QEMU 实现 | 判定 |
|--------|-----------|-----------|------|
| Entry 格式 | bits[63:48]=refcount, bits[47:0]=ret addr | `(ref<<48) \| (addr & MASK48)` | ✓ |
| 地址位宽 | 48-bit PC | `0x0000FFFFFFFFFFFF` | ✓ |
| Refcount 位宽 | 16 bits | `(top >> 48) & 0xFFFF` | ✓ |
| Push 空栈 | ra63[63:48]==0 → ref=1, addr=rb0 | `ra[63]==0 → entry=(1<<48)\|addr` | ✓* |
| Push 递归 | ref∈[1,0xFFFE] ∧ addr match → ref++ | `ref<0xFFFF → ref++` (step1 过滤 ref=0 后等价) | ✓ |
| Push 满-refcount 回退 | ref==0xFFFF → else 分支 shift | `ref<0xFFFF` 为 false → 走 else | ✓ |
| Push 下移 | ra{i-1}←ra{i}, i=2..63 | `for(i=1;i<63;i++) ra[i]=ra[i+1]` | ✓ |
| RASOF 检查 | ra1[63:48]≠0 → RASOF | `ra[1]!=0 → 0x87` | ✓* |
| Pop ref>1 | ref--, ret addr | `ref-1, return addr` | ✓ |
| Pop ref==1 上移 | ra{i+1}←ra{i}, i=62..1; ra1=0 | `for(i=63;i>1;i--) ra[i]=ra[i-1]; ra[1]=0` | ✓ |
| Pop ref==0 | RASUF | `ref==0 → 0x86` | ✓ |
| call_i/r 传参 | ret_addr = PC+4（下一条指令） | `ret_addr = ctx->base.pc_next + 4` | ✓ |
| ret 使用返回值 | ras_pop 返回值 → PC | `gen_helper_ras_pop(ret_addr, ...); store pc` | ✓ |
| 精确异常 | PC 留故障指令, RA 不改 | helper 内 `cpu_loop_exit` 直接 longjmp，后续 TCG ops 不执行 | ✓ |

\* **minor**: QEMU 用 `ra[63]==0` / `ra[1]!=0` 判断空/满，spec 用的是 `ra63[63:48]==0` / `ra1[63:48]≠0`。在合法 RAS 状态下（refcount==0 ⇔ 全零 entry）二者等价，不构成语义差异。

### 与 dadao_interp.py 对照

interp 的 `_ras_push`/`_ras_pop` 与 QEMU 的 `helper_ras_push`/`helper_ras_pop` **算法一致**：
- push: cnt==0 首压 → 递归折叠（cnt∈[1,0xFFFE] + addr match）→ 满栈检查 ra1 refcount → 下移
- pop: cnt>1 递减 → cnt==1 上移+清 ra1 → cnt==0 RASUF
- 移位方向一致（push 下移、pop 上移）

### 独立测试结果

全部通过：

```
QEMU nested call (LLVM crt0→main→callee): exit=42  ✓
Single call regression (asm):               exit=42  ✓
Smoke E2E (llvm-lit):                       3/3 PASS ✓
QEMU control-flow vectors (run_qemu_test.py): 0 FAIL ✓
```

### 未覆盖情形

- **RASOF**（63 层深栈满后继续 call）：helper 内正确触发 0x87 + cpu_loop_exit，但缺端到端测试向量（M1 测试用例未触发深栈）
- **RASUF**（冷栈 ret）：helper 内正确触发 0x86 + cpu_loop_exit，同样缺端到端测试向量
- **refcount=0xFFFF 回退**：递归折叠饱和后正确走 else 分支 shift，缺专项覆盖

### 判决

**通过**。实现与 spec §5.6、dadao_interp 黄金模型一致。2 处 minor 差异（全零 vs refcount 字段检查）为合法等价形式，不构成 bug。全部回归测试通过，嵌套调用 bug 已正确修复。建议后续补充 RASOF/RASUF 端到端测试向量覆盖边界情形。
