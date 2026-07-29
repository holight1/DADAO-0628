# KL-147a：K3 Linux 构建契约与 fresh `arch/dadao` 配置骨架

**状态**：PASS（独立 review 因额度限制待补）  
**日期**：2026-07-29  
**前置**：KL-146a  
**后续**：KL-148a（compile-to-link architecture substrate）

## 目标

1. 从零创建 Linux 5.4 `arch/dadao` 的 Kconfig/Makefile/defconfig 最小骨架；
2. 冻结项目内 Linux 构建工具路径、输出目录和命令；
3. 新增 fail-closed runner，证明 `dadao_defconfig` 与 `olddefconfig`
   可重复生成一致的 64-bit、single-hart、MMU-on、initramfs-ready 配置；
4. 将 Linux 源码改动提交为独立组件 patch，并纳入
   `components/linux/patches/series`。

## 构建契约

- source：`.work/source/linux`
- output：`.work/build/linux`
- `ARCH=dadao`
- `CC=.work/build/llvm/bin/clang --target=dadao`
- binutils：同一 `.work/build/llvm/bin` 下的 `ld.lld`、`llvm-ar`、
  `llvm-nm`、`llvm-objcopy`、`llvm-objdump`、`llvm-readelf`
- host tools：系统 `cc`/`c++`
- 本任务只运行配置阶段，不将 `prepare`、`vmlinux` 或 boot 升格为
  已完成。

## 验收

```text
python3 tests/scripts/run_kl147a_linux_skeleton.py
python3 scripts/manifest_check.py
git -C .work/source/linux status --porcelain=v1
```

runner 必须检查：

- Linux HEAD 以 manifest pin 为祖先且 worktree clean；
- active Linux patch series 非空并与组件 HEAD patch 数一致；
- `dadao_defconfig`、`olddefconfig` 均成功；
- `.config` 精确包含 `CONFIG_DADAO=y`、`CONFIG_64BIT=y`、
  `CONFIG_MMU=y`、`CONFIG_NR_CPUS=1`、`CONFIG_BLK_DEV_INITRD=y`、
  `CONFIG_BINFMT_ELF=y`；
- 两次 `olddefconfig` 后 `.config` SHA256 不漂移；
- 不存在 scenario SKIP。

## 非目标

- 不要求 `make prepare` 或 C/汇编编译；
- 不创建 boot entry、异常入口、页表或设备驱动；
- 不导入历史 `arch/dadao` 文件；
- 不修改 QEMU/gem5/LLVM/musl。

## 实施记录

- Linux component commit：
  `6dbd09a49be915128bb6a55360df79cf8c7c419a`（baseline 上 1 commit）。
- patch：
  `components/linux/patches/0001-dadao-add-K3-configuration-skeleton.patch`；
  series/commit count = 1/1。
- fresh `arch/dadao` 只有 4 个配置层文件：`Kconfig`、
  `Kconfig.debug`、`Makefile`、`configs/dadao_defconfig`；没有导入任何
  kernel/、mm/、include/asm/ 实现。
- runner 连续执行 `dadao_defconfig`、两次 `olddefconfig` 均成功：
  - Linux pin：
    `219d54332a09e8d8741c1e1982f5eae56099de85`；
  - Linux HEAD：
    `6dbd09a49be915128bb6a55360df79cf8c7c419a`；
  - config SHA256：
    `352b07252e9da0836a067b34b051c6fc30277168bf1ca4c91168570fe97d0932`；
  - required symbols 全部精确匹配；
  - 结果：`PASS: KL-147a Linux/DADAO configuration skeleton`。
- `python3 scripts/manifest_check.py` PASS；Linux worktree clean；
  `git diff --check` PASS。

## Review

KL-146a 的独立 subagent 已在任何检查前因账户 usage limit 退出；同一
额度条件仍在，因此本任务不重复消耗失败调用，也不伪造独立结论。

主控复核：

- patch 是 baseline 上单一可逆 commit，series 与 commit 数精确绑定；
- runner 在进入 Kconfig 前检查 pin ancestry、clean worktree、工具存在、
  patch payload 存在和 series/commit count；
- 配置验收检查实际 `.config` 值和二次 `olddefconfig` hash 稳定性，不
  依赖 exit code 单独判绿；
- 文档没有把 config-only 骨架升格为 compile/boot 能力。

结论：**KL-147a PASS**；独立 review 待额度恢复后补审。
