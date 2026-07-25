# KL-106a：`ldmo-ra`/`stmo-ra`（整 bank RA 访问指令）完整语义调研

**日期**：2026-07-25　　**范围**：本地只读调研；未修改 QEMU、gem5、LLVM、
kernel、`contracts/`、`docs/issues.yaml` 或 `~/DADAO-wiki`，未运行测试。
本任务是 `KL-105a`（`docs/reviews/kernel-regras-save-restore-20260721.md`）
的直接后续。

**证据标签**：`[正式契约]`=wiki 原文或 `contracts/` 现有约定；`[已有实现]`=
当前仓库源码/patch 事实；`[推断]`=据此给出的判断或尚待架构确认的结论。

**wiki pin 核对**：`manifests/spec.lock.toml:6` 锁定
`commit = "9f378f4426e131903d60a208766086ae74a53c89"`；`~/DADAO-wiki` 当前
`git rev-parse HEAD` = 同一 commit，`git status --short` 干净，无本地改动。
以下所有引用均针对这一 pin。

```bash
cd ~/DADAO-wiki && git rev-parse HEAD && git status --short
# → 9f378f4426e131903d60a208766086ae74a53c89 / (clean)
```

## 结论先行

**混合判定，不是纯粹的情形 A 或情形 B**。`ldmo-ra`/`stmo-ra` 在当前 wiki pin
里**不是**只有名字/排除记录的占位符——`SimRISC-02-地址类指令.md` §存取RA寄存器
（47-63 行）给出了完整的编码格式、指令语法、对齐要求和越界/非法操作数的
ILLI/MALIGN 规则，且这些规则与已经被 `contracts/isa/spec.md` 正式采纳的
同构指令 `ldmo-rb`/`stmo-rb`（§4.2）、RD `ldmo`/`stmo`（§3.3/3.4）完全对齐，
可以直接类比复用。

但有**一个关键维度是 wiki 沉默的**：**引用计数（`bits[63:48]`）在
`ldmo-ra`/`stmo-ra` 整 bank 搬移时如何处理**——wiki 在
`SimRISC-02-地址类指令.md:11-19` 专门给出了一张「高16位行为」分类表，逐一列出
了 RB 所有相关指令类别（含 `ra2rd`/`rd2ra` 单槽搬移：明确标注"全 64 位覆盖，
bits[63:48] 正常读写"），**唯独没有 `ldmo-ra`/`stmo-ra`（RA↔内存）这一行**。
这不是小事——这正是 K1 的核心正确性要求：KL-105a 的 oracle #1（全槽 round-trip）
明确要求"尤其不得丢 `bits[63:48]` 引用计数"，而这条要求目前没有 wiki 原文
可以直接引用来证明。

因此：**K1 不需要为编码/对齐/越界这些维度重新做 spec 设计（这些可以直接
"启用既有定义 + 类比同构指令"）；但需要为"整 bank 搬移时引用计数是否原样
拷贝"这一个具体点单独做一次 spec 决策**，因为 wiki 对此保持沉默。已按任务
要求在 `docs/wiki-deviations.md` 补记第 8 条（见本报告末尾）。

## 1. 编码格式（§目标1 第一子项）

`[正式契约]` `SimRISC-00-指令系统设计.md:103-104`（QFC 总表）：

```
| 0110-0xxx | ... | jump-iiii | jump-rrii |         | ldmo-ra-rrri |
| 0110-1xxx | ... | call-iiii | call-rrii | ret-riii | stmo-ra-rrri |
```

行标签 `0110-0xxx`/`0110-1xxx` = `op[7:4]`+`op[3]`；列标签 `xxxx-x111` =
`op[2:0]=111`（`SimRISC-00-指令系统设计.md:89`）。据此可机械推出：

- `ldmo-ra`：`op[7:0] = 0110_0111 = 0x67`
- `stmo-ra`：`op[7:0] = 0110_1111 = 0x6F`

格式为 `rrri`（三寄存器 + 6 位立即数），字段布局规则见
`SimRISC-00-指令系统设计.md:44`（`rrri`：`ha`=reg1，`hb`=reg2，`hc`=reg3，
`hd`=immu6）——这与 `contracts/isa/spec.md:130` 的 `rrri` 定义完全一致。

`[正式契约]` `SimRISC-02-地址类指令.md:47-63`（§存取RA寄存器）给出具体语法：

```
ldmo    raha, rbhb, rdhc, immu6
stmo    raha, rbhb, rdhc, immu6
```

字段角色（对照已被 `contracts/isa/spec.md:1090` 采纳的 `ldmo-rb` 记录
`ha=rbha, hb=rbhb, hc=rdhc, hd=immu6(hd)`，结构完全同构）：

- `ha`（`raha`）= 目的/源 bank 首寄存器（RA bank，本指令特有：目标 bank 从
  RB 换成 RA，其余字段角色不变）
- `hb`（`rbhb`）= 基址寄存器（恒为 RB bank，与 RD/RB 版本一致）
- `hc`（`rdhc`）= 地址偏移寄存器（恒为 RD bank，与 RD/RB 版本一致）
- `hd`（`immu6`）= 寄存器个数（1-63，`SimRISC-00-指令系统设计.md:152` 通用规则）

**`contracts/isa/spec.md` 当前完全没有为 `ldmo-ra`/`stmo-ra` 建立编码记录**
——Appendix A 的 `0110-0xxx`/`0110-1xxx` 两行（`contracts/isa/spec.md:1104-1117`）
只列了 `jump`/`call`/`ret`，没有 `0x67`/`0x6F`；§2.8 M1-covered opcode map
（`contracts/isa/spec.md:285-289`）同理只列 `jump-iiii/rrii`、
`call-iiii/rrii`、`ret-riii`，跳过了 `op[2:0]=111` 这一列。这与 M1 排除
状态一致（§7 排除的指令不需要在"M1 covered"清单里出现），**但也说明 K1
若要启用它们，contracts 里目前是空白，需要新增（不是改错，是补一段新章节）**。

**判定：编码格式维度 = 情形 A（wiki 已有完整定义，可直接照抄，不需要 spec
decision）**。

## 2. 单次访存槽位数/宽度（§目标1 第二子项）

`[正式契约]` `SimRISC-02-地址类指令.md:60`："`immu6` = 0 时触发 ILLI 异常"；
`:61`："`raha + immu6 > 64` 时触发 ILLI 异常（超出 ra63）"。这与
`contracts/isa/spec.md:210-217`（§2.6.3 Multi-Register Range Rules）已经
明确把 `ldmo-ra`/`stmo-ra` 和其它多寄存器指令并列在同一条通用规则里的表述
完全一致：

```
For all multi-register instructions (ldm/stm*, rd2rd, rd2rb, rb2rd, rb2rb,
rd2ra, ra2rd, ldmo-rb, stmo-rb, ldmo-ra, stmo-ra):
- immu6 = 0 → ILLI.
- first_reg + immu6 > 64 (exceeds bank boundary) → ILLI. No wrap, no truncation.
```

也就是说：**"整 bank"不是一次搬 64 槽，而是每条指令最多搬 63 槽**
（`immu6` 有效范围 1-63，`SimRISC-00-指令系统设计.md:152`）；覆盖完整
`ra0-ra63`（64 个寄存器）需要至少两条指令（例如 `raha=0,immu6=63` 覆盖
`ra0-ra62`，再补一条覆盖 `ra63`，或任意能凑满 64 槽且不越界的两段划分）。
`raha`（起始寄存器）没有专属 ILLI 规则排除 `ra0`（不像 `rd0`/`rb0` 有专门的
硬件特殊语义排斥规则，见 `contracts/isa/spec.md:174-208` §2.6.1/2.6.2），
即 `ra0` 可以正常出现在 `ldmo-ra`/`stmo-ra` 的寄存器范围内——这点由 wiki
正文直接给出（没有额外排除条款），与 `contracts/isa/spec.md §1.5` 关于
`ra0` 是 MemRAS 指针/计数（而非硬件特殊访问限制寄存器）的描述不矛盾。

**判定：槽位数/宽度维度 = 情形 A**。

## 3. 槽位顺序、字节序交互（§目标1 第三子项）

`[正式契约]` wiki 没有为 `ldmo-ra`/`stmo-ra` 单独重复 EA 计算公式（这点与
RB 章节的 `ldmo-rb`/`stmo-rb` 相同——RB 章节本身也没有重复公式，是靠
`SimRISC-01-数据类指令.md:12-13` 在 RD 章节给出的通用陈述"另一种操作数类型
为：`rrri`，属于多load/store类型，地址计算公式为基址寄存器 + 数据寄存器"
和 `SimRISC-01-数据类指令.md:64`"`rdha`用来指定第一个寄存器，`rbhb+rdhc`
用来指定地址"来类比适用）。

`contracts/isa/spec.md:693` 已经把这条通用公式形式化为
`ldmo-rb`/`stmo-rb` 的正式契约（未逐字引用 wiki 行号，是作者基于同构格式
的显式推导，已被接受为 §4.2 正文）：

```
EA for register i: (rbhb[47:0] + rdhc[47:0] + i × 8) mod 2^48
```

`SimRISC-02-地址类指令.md:62`（RA 章节自己的限制条款）："源和目的寄存器
范围可以重叠。硬件按序号递增逐对处理，每对先读后写"——这与 RD/RB 版本的
措辞逐字一致（`SimRISC-01-数据类指令.md:63`、`SimRISC-02-地址类指令.md:44`），
确认处理顺序是**寄存器序号递增**，即 `ra(ha+i)` ↔ `ea_i = base + i×8`，
寄存器序号越大对应地址越高。数据端序遵循 §2.1 一般规则（大端序，
`SimRISC-00-指令系统设计.md:15`；`contracts/isa/spec.md:94-96`），无 RA
专属的字节序例外条款。

**判定：槽位顺序维度 = 情形 A（通过与 RD/RB 同构指令的直接类比得出，wiki
未对 RA 重复此文字，但类比强度与 contracts 已接受的 `ldmo-rb` 处理方式
相同标准）**。

## 4. 引用计数字段处理（§目标1 第四子项）—— **wiki 沉默，唯一的真实缺口**

`[正式契约]` `SimRISC-02-地址类指令.md:9-21` 的高 16 位行为分类表：

```
| 操作类别 | 指令 | 高 16 位行为 |
| 存取类指令 | ldo/ldmo/sto/stmo（内存→RB） | 全 64 位覆盖，bits[63:48] 正常读写 |
| 赋值类指令-寄存器 | rd2rb/rb2rb/ra2rd/rd2ra | 全 64 位覆盖，bits[63:48] 正常读写 |
| 赋值类指令-立即数 | setzw-rb/orw-rb/andnw-rb | 全 64 位覆盖... |
| 算术运算类指令-加减 | add-rb/sub-rb/addi-rb/rela | 低 48 位...bits[63:48] 保持不变 |
| 算术运算类指令-比较 | cmp-rb | ...bits[63:48] 不影响比较运算 |
| 控制流指令-跳转 | br*/jump | ...bits[63:48] 保持不变 |
| 控制流指令-函数支持 | call/ret | ...bits[63:48] 做为引用计数 |
```

（行号：`SimRISC-02-地址类指令.md:13,14,15,16,17,18,19`）

这张表**逐类枚举了几乎所有涉及 RB/RA 高 16 位的指令**，包括单槽 RA↔RD
搬移（`ra2rd`/`rd2ra`，明确"全 64 位覆盖"）和 `call`/`ret`（明确"高 16 位
做为引用计数"、见 §5 压栈/弹栈流程 `DADAO-11-AEE-应用程序运行环境.md:195-219`
的具体位操作）。**唯独没有 `ldmo-ra`/`stmo-ra`（RA↔内存）这一行**——该表
第一行"存取类指令 | ldo/ldmo/sto/stmo（内存→RB）"明确写的是"内存→**RB**"，
不包含 `-ra` 后缀变体。

`[已有实现/推断]` 全文（`~/DADAO-wiki` 15 个文件）grep `ldmo-ra`/`stmo-ra`
只有 2 处命中，均在 `SimRISC-00-指令系统设计.md:103-104` 的 opcode 表格里；
`SimRISC-02-地址类指令.md` §存取RA寄存器（47-63 行）本身也没有补一句类似
"引用计数原样搬移"或"引用计数被清零/校验"的文字。`DADAO-11-AEE-应用程序
运行环境.md:189`（"进程切换时，操作系统须保存和恢复全部 `ra0-ra63` 寄存器"）
和 `:185`（fork 需复制全部 ra 寄存器）都只陈述 OS 责任，**没有指明用什么
指令实现、也没有说明引用计数是否要求逐位保真**。全文（`DADAO-21/22/23-*`
ABI/SBI/HBI 三个二进制接口文档）grep 均无 `ldmo-ra`/`stmo-ra`/RA 相关命中：

```bash
cd ~/DADAO-wiki
grep -rn "ldmo-ra\|stmo-ra\|ldmo_ra\|stmo_ra" *.md
# → 仅 SimRISC-00-指令系统设计.md:103,104（opcode 表）
grep -n "RA\b\|ra0\|ra63\|返回地址" DADAO-22-SBI-主管系统二进制接口.md
# → 0 matches
```

`[推断]` 一个支持"应该是全 64 位原样拷贝"的类比证据：`ra2rd`/`rd2ra`
（单槽 RA↔RD 搬移）已被 wiki 明确列为"全 64 位覆盖"；同一份文件里，
`contracts/isa/spec.md:959` 给 `rd2ra`/`ra2rd` 的排除记录额外写了一句
"ISA semantics clear per SimRISC-02 §RA↔RD"，但给 `ldmo-ra`/`stmo-ra`
的排除记录（`contracts/isa/spec.md:958`）**没有**类似的"语义清晰"限定语——
这与本报告独立发现的缺口方向一致（**不作为独立证据，只作为交叉印证**：
`contracts/isa/spec.md` 原作者当时可能已经注意到这个不对称，但没有展开）。
但这只是类比，不是 wiki 的显式条款——"引用计数是否原样搬移"仍然是一个
需要显式决策的点，理由如下：整 bank 搬移的语义完全可能是"只搬低 48 位、
高 16 位清零重建"（比如把内存看作纯地址栈的序列化格式，恢复时重新用某种
规则填充引用计数），wiki 没有排除这种可能性。

**判定：引用计数处理维度 = 情形 B（wiki 沉默，需要 spec decision）**。

## 5. 原子性（§目标1 第五子项）

`[正式契约]` `contracts/isa/spec.md:236-240`（§2.7）："All ISA-defined
exceptions (ILLI, UNDI, MALIGN, IALIGN, RASOF, RASUF) are precise: the
faulting instruction has no architectural side effect...RA is not modified"
——这是通用规则，逐字覆盖所有指令（包括 `ldmo-ra`/`stmo-ra`，若启用）。
`[推断]` 实践中这条规则对多寄存器指令不构成"部分执行后回滚"的额外负担：
`ldmo-ra`/`stmo-ra` 唯二的 fault 来源是 `immu6=0`/越界 ILLI（这是执行前
的静态范围检查，见 §2.6.3，不依赖循环执行到一半）和 MALIGN（固定 8 字节
步长下，若起始地址对齐，则每个槽地址都对齐；若起始地址不对齐，则第一个
槽就会先失败——不存在"前几个槽已经不对齐检测通过、后面才触发"的场景，
因为对齐检查在 8 的整数倍步长下对所有槽是同一个真值）。`ldmo-ra`/`stmo-ra`
本身不触碰 RegRAS push/pop 语义（见下第 6 节的 `pushra`/`popra` 历史区分），
不会触发 `RASOF`/`RASUF`。

**判定：原子性维度 = 情形 A（由已被 contracts 采纳的通用精确异常规则 +
固定步长对齐检查的数学性质保证，不是 RA 专属的额外设计点）**。

## 6. 对齐要求、越界/非法访问（§目标1 第六子项）

`[正式契约]` `SimRISC-02-地址类指令.md:56`："需 8 字节地址对齐，未对齐
触发 MALIGN 异常。" `:60-61`：`immu6=0` → ILLI；`raha+immu6>64` → ILLI。
与 `ldmo-rb`/`stmo-rb`（`contracts/isa/spec.md:696-699`，8-byte alignment
+ 同款 ILLI 规则）完全同构。

**判定：对齐/越界维度 = 情形 A**。

## 7. 与现有 §1.5/§2.6.3/§2.7 RA 模型的兼容性（§目标1 第七子项）

- `contracts/isa/spec.md §1.5`（63-81 行）：RA 寄存器高 16 位=引用计数、
  低 48 位=返回地址，`ra0` 例外（MemRAS 指针+计数）——`ldmo-ra`/`stmo-ra`
  的 wiki 定义（原样按 64 位寄存器整体搬移，未排除 `ra0`）与此模型不冲突，
  只是"引用计数如何在内存里编码/是否保真"这一具体行为未定义（即第 4 节
  的缺口）。
- `contracts/isa/spec.md §2.6.3`：已经把 `ldmo-ra`/`stmo-ra` 正式列入通用
  多寄存器 ILLI 规则，**无冲突，是已经生效的正式文本**（虽然这两条指令
  本身被 §7 排除在 M1 之外，但§2.6.3 的规则文本已经把它们纳入了"if this
  instruction were enabled"的统一表述里，说明 contracts 作者已经预判过
  这一天）。
- `contracts/isa/spec.md §2.7`：精确异常规则通用覆盖，无冲突（见第 5 节）。

**判定：兼容性维度 = 情形 A（无冲突，第 4 节的引用计数缺口是"未定义"而非
"冲突"）**。

## 8. 历史版本核查（§目标2）

`[已有实现/推断]` 只读 `~/DADAO-wiki` git 历史（未修改任何文件）：

```bash
cd ~/DADAO-wiki
git log --oneline -- SimRISC-02-地址类指令.md   # 21 commits，文件创建于 a05261a
git log --oneline --all -S"存取RA寄存器" -- SimRISC-02-地址类指令.md
# → 仅命中改名 commit 5b0a105（Unicode连字符→ASCII），标题字符串本身从
#   创建起从未被增删
git show a05261a:SimRISC-RBRA.md | sed -n '23,35p'   # 最初版本（2024-04-17）
```

最初版本（`a05261a`，2024-04-17，文件名 `SimRISC-RBRA.md`）里，这两条指令
的助记符是 `ldmra`/`stmra`（不是现在的 `ldmo`/`stmo` 命名法），限制条款
只有一句"`immu6`不能为`0`"，**没有对齐规则、没有越界 ILLI、没有引用计数
条款**。此后经过若干次"批量补齐"提交（例如 `054c043` 新增 MALIGN 异常
补全所有存取指令对齐要求、`61a68fa` 补齐 `immu6=0`/越界 ILLI），RA 章节
才逐步获得了和 RB 章节对等的对齐/越界规则——**但引用计数条款在这整个演进
过程中从未被补上**，即便是在专门"补齐高16位规则统一表"的提交
（`c1c4e44`，`SimRISC-02: RB高16位规则统一5类12行表`）里也没有把 RA↔内存
这一类纳入表格。这进一步支持第 4 节的判断：**这不是文档疏漏后来被删掉的
内容，是从一开始到现在持续未覆盖的维度**。

另有一个相关但不同的历史发现：`git show aa38d0b -- "SimRISC*"` 显示曾经
存在（且在删除前已经是 HTML 注释、非渲染可见内容）一对 `pushra`/`popra`
指令，其注释头写明"pushra/popra 为返回地址栈操作，ldmo/stmo 为寄存器堆
操作，ra2rd/rd2ra 同为寄存器堆操作"——**这句话明确把 `ldmo`/`stmo`（含
`-ra` 变体）定性为"寄存器堆的扁平化访存"，而不是"返回地址栈语义的
push/pop"**。这条已删除的注释间接确认了 `ldmo-ra`/`stmo-ra` 的设计意图
一直是原始寄存器堆搬移（与 `ldmo-rb` 同构），不牵涉 `call`/`ret` 那种
带引用计数递增/递归判断的栈语义——但它同样没有回答"扁平搬移时引用计数
位怎么处理"这个具体问题，只是排除了"应该走 push/pop 语义"这个候选答案。

```bash
cd ~/DADAO-wiki
git log --all --oneline -S"popra" -- SimRISC-02-地址类指令.md
git show aa38d0b -- "SimRISC*" | grep -n -B2 -A20 "pushra"
```

**判定：历史版本核查 = 未发现任何时点存在比当前 pin 更完整的定义；引用
计数缺口是原生的、持续存在的，不是回归。**

## 9. 逐维度判定汇总（§目标3）

| 维度 | 判定 | 依据 |
|------|------|------|
| 编码格式（opcode/format/字段） | **情形 A** | `SimRISC-00-指令系统设计.md:103-104`；`SimRISC-02-地址类指令.md:47-63` |
| 单次访存槽位数/宽度 | **情形 A** | `SimRISC-02-地址类指令.md:60-61`；`contracts/isa/spec.md:210-217` |
| 槽位顺序（含大端序交互） | **情形 A**（类比 RD/RB 同构指令，标准与 contracts 已接受的 `ldmo-rb` 处理一致） | `SimRISC-01-数据类指令.md:12-13,64`；`SimRISC-02-地址类指令.md:62`；`contracts/isa/spec.md:693` |
| **引用计数字段处理** | **情形 B（wiki 沉默）** | `SimRISC-02-地址类指令.md:9-21` 高16位分类表缺 RA↔内存行；全文 grep 无补充说明 |
| 原子性 | **情形 A** | `contracts/isa/spec.md:236-240`（§2.7 通用精确异常）+ 固定步长对齐的数学性质 |
| 对齐要求/越界 fault | **情形 A** | `SimRISC-02-地址类指令.md:56,60-61` |
| 与 §1.5/§2.6.3/§2.7 兼容性 | **情形 A（无冲突）** | 见第 7 节 |

**总体判定：6/7 维度情形 A，1/7 维度情形 B。但这唯一的情形 B 维度
（引用计数处理）恰好是 K1 最关心的正确性要求**——KL-105a 的 oracle #1
（全槽 round-trip）显式要求"尤其不得丢 `bits[63:48]` 引用计数"，这条
要求目前没有 wiki 原文支撑，必须先做一次显式 spec decision（"整 bank
搬移时引用计数原样拷贝" vs "特殊处理"），不能由实现任务自行假定。

## 10. 对 K1 下一步的建议（`[推断]`，非任务范围内的决策）

1. **编码/对齐/越界/顺序**：可以直接把 `SimRISC-02-地址类指令.md:47-63`
   + `SimRISC-00-指令系统设计.md:103-104` 形式化为 `contracts/isa/spec.md`
   新增 §4.x（"RA Multi Load/Store"，仿 §4.2 `ldmo-rb`/`stmo-rb` 的写法），
   不需要用户拍板。
2. **引用计数处理**：需要用户/架构师明确二选一（或其它选项）：
   - (a) 全 64 位原样拷贝（类比 `ra2rd`/`rd2ra`/`ldo`/`ldmo`(RB) 已有的
     "全 64 位覆盖"惯例，最小改动、最符合"扁平寄存器堆访存"定位）；
   - (b) 其它语义（例如只搬低 48 位、高位由硬件重建）——目前没有任何
     wiki 或 contracts 证据支持这一选项，若采用需要给出独立理由。
   本报告不代为拍板，只指出这是唯一需要用户决策的点；(a) 是唯一有直接
   类比证据支持的选项。

## 附：可复核命令汇总（只读）

```bash
cd /home/holight/DADAO-0628
nl -ba contracts/isa/spec.md | sed -n '63,81p;210,240p;947,959p;1104,1117p'
nl -ba manifests/spec.lock.toml

cd ~/DADAO-wiki
git rev-parse HEAD
git status --short
grep -rn "ldmo-ra\|stmo-ra\|ldmo_ra\|stmo_ra" *.md
nl -ba SimRISC-00-指令系统设计.md | sed -n '85,106p'
nl -ba SimRISC-02-地址类指令.md | sed -n '1,63p'
nl -ba DADAO-11-AEE-应用程序运行环境.md | sed -n '167,219p'
grep -n "RA\b\|ra0\|ra63\|返回地址" DADAO-22-SBI-主管系统二进制接口.md DADAO-23-HBI-超管系统二进制接口.md

git log --oneline -- SimRISC-02-地址类指令.md
git log --oneline --all -S"存取RA寄存器" -- SimRISC-02-地址类指令.md
git show a05261a:SimRISC-RBRA.md | sed -n '23,35p'
git log --all --oneline -S"popra" -- SimRISC-02-地址类指令.md
git show aa38d0b -- "SimRISC*" | grep -n -B2 -A20 "pushra"
```

## 已补录 `docs/wiki-deviations.md`

见该文件"8. `ldmo-ra`/`stmo-ra` 整 bank 搬移时引用计数字段处理未定义
（KL-106a，2026-07-25）"条目，`wiki 状态`=SILENT，`状态`=OPEN，等待 K1
的 spec decision。
