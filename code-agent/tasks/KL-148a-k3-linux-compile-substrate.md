# KL-148a：K3 Linux compile-to-object substrate

**状态**：PASS（独立 review 因额度限制待补）  
**日期**：2026-07-29  
**前置**：KL-147a  
**后续**：KL-149a（linked image + reset handoff）

## 目标

1. 为 fresh `arch/dadao` 增加足以支撑 Linux generic C 编译的最小 ABI
   headers；
2. 使用当前 DADAO clang/LLD 工具完成 `make prepare`；
3. 实际编译 upstream `init/main.c` 为 DADAO ELF relocatable object；
4. 把所有 architecture source 变更封装为 Linux patch 0002；
5. 新增 fail-closed runner 和可追溯日志。

## 验收

```text
python3 tests/scripts/run_kl148a_linux_compile.py
```

必须满足：

- 先复跑 KL-147a；
- Linux source clean，series/commit count = 2/2；
- series 中每个 patch 的 stable patch-id 与对应 component commit 一致；
- `make prepare` 成功；
- `make init/main.o` 成功；
- `make init/version.o` 成功，以覆盖 `asm/current.h` 已先定义时的
  architecture-header include order；
- 编译命令显式固定 `KCFLAGS=-O0`；默认 `-O2` 的
  `TargetInstrInfo::insertBranch` 缺口由 KL-148b 跟踪，不混入本任务；
- `llvm-readobj --file-headers init/main.o` 明确是 elf64-dadao、
  big-endian、Machine=0xDA0；
- evidence 中保存完整命令/stdout/stderr；
- 不允许 SKIP。

## 范围边界

- custom header 只冻结当前 Linux 编译所需的 ABI 类型、page/thread/
  ptrace/ELF 基础布局和与 K2 一致的 PTE 几何/位定义；trap、context
  switch、PTBR/TLB 操作和 Linux page-fault policy 仍未实现；
- asm-generic 可用接口由显式 Kbuild 列表生成，不复制其他 architecture
  的实现文件；
- 不创建 boot entry，不链接 vmlinux，不声称 kernel 可运行；
- Linux `include/linux/kbuild.h` 仅允许增加 `__dadao__` 下的 `%c0`
  常量格式分支，以消除 `.ascii` 与 DADAO `$` 立即数前缀的语法冲突；
- Linux 5.4 全局对 clang 强加 `-no-integrated-as`，DADAO 尚无 GNU
  binutils assembler；`arch/dadao/Makefile` 必须在架构 flags 中以
  `-integrated-as` 覆盖；
- 不修改 QEMU/gem5/LLVM/musl。
- 不声称默认 `-O2` 可编译，不声称 `init/main.o` 已可链接或运行。

## 实施记录

- Linux component commit：
  `c06b6f93a3c33968145f001859f29702e47f3244`（baseline 上第 2
  commit）；patch：
  `components/linux/patches/0002-dadao-add-Linux-compile-substrate.patch`。
- series/commit = 2/2；patch 0001/0002 的 stable patch-id 分别为
  `14ef129f2b38c5bd058f38316bf00de9e72a13a3` /
  `728747dae1a19c159825459a485c624e403f9d6e`，均与对应 component
  commit 精确相等。
- 新增最小 architecture compile substrate：
  - 64-bit big-endian UAPI、`pt_regs`/signal/ELF 基础布局；
  - 64 KiB page、两级各 8192 项、P/SP/D/A/X/W/R 与 8-bit fragment
    leaf protection；
  - single-CPU interrupt-masked atomic64 和显式 `dadao_current` contract；
  - thread/task stack、uaccess range、generic-header Kbuild 和空
    `asm-offsets.c`；
  - `kbuild.h` 的 DADAO `%c0` constant formatter，以及 Linux 5.4
    `-no-integrated-as` 的 arch-local override。
- runner 先执行 KL-147a，随后 clean output、`make prepare`、真实编译
  upstream `init/main.c`；最终：
  - Linux pin：
    `219d54332a09e8d8741c1e1982f5eae56099de85`；
  - Linux HEAD：
    `c06b6f93a3c33968145f001859f29702e47f3244`；
  - config SHA256：
    `d3bf0b702b42145360fc53c6bfa170a433e2d64c5dd692507cb5886cd486792f`；
  - `init/main.o`：48,824 bytes，SHA256
    `eeee5a27b765c80a25a4b7b08db224a899cbf60dae0bc13435f037507dff239d`；
  - `init/version.o`：2,072 bytes，SHA256
    `996e8af937fd394e6174e4acc5e170fc33a29cf9b9a186f376e2f2ececc20304`；
  - ELF：64-bit、big-endian、ET_REL、Machine=`0xDA0`；
  - `PASS: KL-148a Linux/DADAO compile-to-object substrate`。
- `make prepare`/compile 唯二 warning 是 Linux 5.4
  `checksyscalls.sh` 报 `fstat`/`clone3` 尚未实现；本任务未把 warning
  隐藏为全 syscall 支持。
- 默认 `-O2` 首次真实编译暴露
  `TargetInstrInfo::insertBranch` assertion，已创建 KL-148b 精确记录；
  按既定优化级别边界，本任务使用 `KCFLAGS=-O0` 继续基本链路。
- `manifest_check.py` PASS；DADAO E2E `smoke_add.test` 1/1 PASS；
  Linux worktree clean；Python compile、`git diff --check` PASS。

## Review

独立 review 的账户 usage limit 与 KL-146a/KL-147a 相同，本轮没有重复
启动注定失败的 agent，也没有把主控复核写成独立结论。

主控逐项复核了 patch、生成对象和 fail-closed runner，并在复核中修正：

1. `llvm-readobj` 对 project-custom `EM_DADAO` 显示
   `elf64-unknown/Arch: unknown`，因此验收改为检查真正稳定的
   `AddressSize=64bit`、`BigEndian`、`ET_REL`、`Machine=0xDA0`，没有
   伪造工具字符串；`llvm-objdump --triple=dadao` 可正常反汇编对象。
2. `pte_modify()` 必须保留硬件 A/D 状态，`_PAGE_CHG_MASK` 已从仅 PFN
   修为 PFN+A+D。
3. generic `USER_DS=TASK_SIZE-1` 与本实现的 exclusive range check
   会拒绝最后一个合法字节，已由 arch 显式冻结
   `USER_DS=TASK_SIZE`。
4. runner 增加逐 patch stable patch-id 比对和 clean 后重编译，防止
   “patch 文件存在但与 component commit 漂移”或旧对象假绿。
5. KL-149a 首次全链接暴露 include-order sensitivity：
   `atomic64_cmpxchg()` 的局部变量 `current` 会被 `asm/current.h` 的
   同名宏替换。已改为 `observed`，并把 `init/version.o` 纳入 KL-148a
   门禁，确保该头文件顺序持续受测。

结论：**KL-148a 在明确的 `-O0` compile-to-object 范围内 PASS**。
它不代表 vmlinux 可链接、kernel 可启动、PTBR/TLB/page fault 可用或
默认 `-O2` 可用；独立 review 待额度恢复后补审。
