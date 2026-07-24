# Wiki 待确认问题清单

来源：`contracts/isa/spec.md §Appendix C`
版本：spec.md 0.4.0（2026-06-29，基于 Wiki `13a414d`）
状态：绝大多数问题已由 Wiki 0.4.1 解决；C-14 已由架构决策关闭；3 项仍需 Wiki 确认。

---

## 仍待确认

### 1. ~~rd2ra/ra2rd M1 Scope（C-14）~~ → **已关闭（架构决策 2026-06-29）**

Excluded：M1 scope 决策；ISA 语义清楚（SimRISC-02 §RA↔RD）但非变参标量 ABI 所需。
见 Scope Matrix 和 `docs/open-spec-issues.md`。

### 2. 条件赋值重叠 snapshot（C-27）

spec.md §3.12 断言：csn/csz/csp/cseq/csne 在 src/dst 重叠时所有源寄存器先读后写。
**Wiki 来源未找到**；现有 Wiki C-12（SimRISC-01 L203）仅明确 muls/mulu/divs/divu 的 snapshot，不覆盖条件赋值。

需确认：SimRISC-01 是否对 rrrr-format 条件赋值有同等 snapshot 规定。
阻断：条件赋值 src=dst 重叠测试向量无法定论。

### 3. SBZ 字段非零 fault 类型

spec.md §2.6.4 未确定 non-zero SBZ 触发 ILLI 还是 UNDI。
需确认：Wiki 是否在任何地方声明 SBZ 的 fault 类型。
阻断：QEMU 诊断模式 SBZ 处理。

### 4. 硬件复位初值（C-18）

Wiki 已明确：
- `rb0` 复位初值 = `cfx_power_hypv_excp_vector`（SEE §2.1）
- `rb0[63:48]` 恒为 0
- RA process-entry 初始化 = 全零
- RB 高 16 位初值 = 全 0

未明确：
- RD `rd1`–`rd63` 硬件复位值
- RB `rb1`–`rb63` 硬件复位值
- RA `ra0`–`ra63` 硬件复位值（process-entry 初始化 ≠ 硬件复位）
- RF `rf1`–`rf63` 硬件复位值（如 M1 需要）

### 5. 变参保存区基址与栈布局顺序自相矛盾（DL-072a，2026-07-23）

`DADAO-21-ABI-应用程序二进制接口.md` §可变参数 同时给出两条规则：

- "栈上参数区域按地址从低到高排列：**寄存器溢出参数区 → 局部变量 → varargs 保存区**"
  ——varargs 保存区在整个帧里地址**最高**。
- `va_start(ap, last_named_arg)`：`ap = (char*)sp + N * 8`，`sp` 为**调用点 sp**
  （即 callee 的 incoming stack pointer）——意味着保存区紧跟在 incoming_sp **之后**
  （地址范围里偏低的部分），而不是在"局部变量"之后的高地址处。

这两条规则无法同时成立：如果保存区基址就是 incoming_sp（第二条），它就不可能同时
在"局部变量"之后的高地址（第一条）——除非"局部变量"实际指的是别的东西，或者
"从低到高"描述的是另一个不同的地址区间。

**当前处置**（DL-072a，`components/llvm/patches/0050-...patch`）：保留
incoming_sp 作为 `va_start` 的锚点（callee 唯一能拿到的稳定基址），未强行满足
"局部变量之后"这条排列描述；固定参数溢出区放在保存区前、变参尾巴自身的溢出副本
放在保存区后。**未阻断**当前实现（`varargs_overflow.test` 等已验证固定/未命名
溢出场景均正确），但这条文字矛盾本身需要 wiki 团队确认到底哪条规则是权威的，还是
两条描述的是不同的抽象层次（本任务的理解可能有误）。

### 6. 聚合类型 RD-split "高位块先入高寄存器" 字节序方向不明确（ML-031a，2026-07-24）

`DADAO-21-ABI-应用程序二进制接口.md` §聚合类型参数"不满足 HFA/HPA 条件"一条：

> ≤ 32 字节：拆分为 1-4 个 8 字节块，放入 RD bank，**高位块先入高寄存器**

与本节其它每一条规则不同，这一条**没有配worked example**（HFA/HPA 各自都有一张
展开后的寄存器映射表，唯独这条只有一句话）。字面读法有两种：

- 读法 A（反序）：把整个聚合体的原始字节序列看成一个连续的大端整数，地址最低的
  8 字节块（"高位"，因为大端序下地址低=数值高）应该进入**编号最高**的那个寄存器
  （该聚合体分配到的寄存器区间里最后一个），后续块依次进入更低编号的寄存器——即
  寄存器编号与内存地址**反向**递增。
- 读法 B（顺序/自然序）：第一个内存块进入该参数分配到的**第一个（最低编号）**
  寄存器，后续块进入依次递增编号的寄存器——即与 CCState 处理参数时寄存器分配的
  自然顺序一致，零改动即可通过 Clang 的 `[N x i64]` coerce 类型机制自动获得。

**当前处置**：采用读法 B（自然升序）。理由：
1. 同一小节内 HFA/HPA 的展开表全部是自然升序（`struct{void *p,*q;}` → `p`→RB16,
   `q`→RB17，字段声明顺序对应寄存器编号顺序），若 RD-split 采用相反约定，会是
   本节内部唯一的例外，缺乏动机。
2. 这条规则缺 worked example，与本节其它每条规则形成对照，暗示这里的文字本身
   可能不够精确/未经充分校对。
3. 读法 B 是 Clang `ABIArgInfo::getDirect` + `[N x i64]` coerce 类型机制的
   零成本默认行为（`CreateCoercedLoad` 按内存地址升序读出各 8 字节块，`CCState`
   按声明顺序把这些块依次分配到升序寄存器编号）；读法 A 需要额外反转寄存器分配
   顺序的自定义 backend 代码，且本节没有其它证据支持这种反转是有意为之的设计。

**验证方法说明**：由于当前工程里 DADAO 只有这一套编译器实现（没有独立的第二个
工具链可交叉验证寄存器编号约定"应该"是哪一种），无法用差分测试确定哪种读法是
wiki 原意——两种读法在"caller/callee 使用同一套约定"的前提下都能自洽通过端到端
测试（`tests/lit/E2E/agg_args_named.test` 的 `Pair16`/`Five20`/`Quad32` 用例只
验证了字段值读回正确，不区分具体走了哪个寄存器编号）。这条歧义本身需要 wiki
团队确认，本实现选择读法 B 并如实记录。

### 7. 聚合类型变参在保存区内的字节对齐方向未定义（ML-031a，2026-07-24）

wiki §大端序 slot 布局明确规定**标量**窄类型在 8 字节 slot 内右对齐（`byte
8-N 至 7` 为有效值，`byte 0 至 8-N-1` 为符号/零扩展位）。但对**聚合类型变参**
（§可变参数"大于 8 字节的聚合变参"）尺寸不是 8 的整数倍时（例如 5 字节、20 字节）
最后一个不足 8 字节的块该往哪边对齐，wiki 全文未提及——"大于 8 字节的聚合变参"
一条只讲了"按自然对齐拆成多个 8 字节单元"，没有说尺寸不整除 8 时最后一块如何
填充。

**当前处置**：聚合类型（含变参）采用**左对齐**（真实字节在前，填充字节在后），
与标量的右对齐规则**不同**。理由：
1. 这与 `clang/lib/CodeGen/CGCall.cpp` 里 `CreateCoercedLoad`/coercion-through-
   memory 机制的默认行为完全一致（把源结构体的真实字节从临时缓冲区偏移 0 开始
   放置，尾部未初始化）——采用这个默认行为意味着 ABI 分类代码（`DADAO.cpp`）不
   需要为聚合体单独写一套反向填充逻辑。
2. `clang/lib/CodeGen/ABIInfoImpl.cpp` 的 `emitVoidPtrDirectVAArg` 本身已经
   内置了这个区分：右对齐分支的判断条件是 `!DirectTy->isStructTy() ||
   ForceRightAdjust`——即**默认情况下结构体类型被排除在右对齐之外**，只有标量
   才右对齐，这是上游共享基础设施本就预期的方向，本任务只是让 `ForceRightAdjust`
   参数如实反映这个区分（此前 DL-072a 硬编码 `true`，因为当时只覆盖标量，从未
   触发这个分支）。
3. 已通过真实探针验证自洽：`strct-stdarg-1.c`（5 字节 struct 变参）在此实现下
   双后端跑通；若改成右对齐会导致读出的字段值与写入值不匹配（已在实现过程中
   通过临时改错验证过这一点，见任务完成区）。

这条同样是 wiki 文本本身没有覆盖到的边界情况（不是内部矛盾，是缺失），如实记录
以便未来 wiki 补充措辞时对照。

---

## 附：已确认（Wiki 0.4.1 / commit 13a414d 已明确）

| 编号 | 事项 | Wiki 来源 |
|------|------|----------|
| C-01 | 指令大端序 | SimRISC-00 §指令设计 L15 |
| C-02 | 保留编码 → UNDI 异常 | SimRISC-00 §SimRISC QFC 表头注 |
| C-03 | RB 高 16 位分类规则表 | SimRISC-02 L7–L21 |
| C-04 | 存取类 RB → 全 64 位覆盖写 | SimRISC-02 L13 |
| C-05 | 算术类 RB → 低 48 位，高 16 位不变 | SimRISC-02 L16 |
| C-06 | 控制流 PC 48 位，rb0[63:48]=0 | SimRISC-02 L168 |
| C-07 | RASOF/RASUF 精确异常，RA 不提交 | DADAO-11-AEE L183 |
| C-08 | 除零 → ILLI | SimRISC-01 L199 |
| C-09 | divs truncate-toward-zero，remainder = dividend 符号 | SimRISC-01 L200 |
| C-10 | INT64_MIN ÷ -1 → ILLI | SimRISC-01 L201 |
| C-11 | fault 时 rdha/rdhb 无写入 | SimRISC-01 L202 |
| C-12 | 操作数重叠 → source snapshot | SimRISC-01 L203 |
| C-13 | RA process-entry 全零初始化 | DADAO-11-AEE L185 |
| C-15 | swym 除 PC 外无架构副作用 | SimRISC-04 L30 |
| C-16 | 多寄存器超界 → ILLI（不环绕） | SimRISC-01 L65 |
| C-17 | immu6=0 → ILLI | SimRISC-01 L64 |
| C-19 | 有效地址 = 低 48 位 mod 2^48 | SimRISC-02 L7 |
| C-20 | rb0[63:48] 恒为 0 | DADAO-11-AEE §基址寄存器 |
| C-21 | rela 高 16 位保持不变 | SimRISC-02 L161 |
| C-23 | PC[1:0]≠00 → IALIGN | SimRISC-00 L13 |
| C-24 | MALIGN 精确异常（SEE 确认所有同步异常精确） | SEE §2.4 |
| C-25 | rd0 为目的触发 ILLI（双目的有例外） | SimRISC-01 L7 |
| C-26 | 双目标同一非 rd0 → ILLI | SimRISC-01 L147 |
