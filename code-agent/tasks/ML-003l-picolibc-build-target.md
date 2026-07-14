# ML-003l: picolibc 构建加入 Makefile，测试改为依赖外部构建产物（不入库二进制）

**执行环境**: 本地 DS · DADAO-0628（构建基础设施 + lit 测试调整）

**状态**: 待执行

**前置**：ML-003k（架构师亲自修复跳转表悬空条目真根因，`.work/llvm` commit `4b4af3758863`/patch 0031，goal① 已在无 workaround 情况下真实验证通过：`vfprintf.c` 真编译 + 完整链路真跑出 "hello, dadao"+exit=0，E2E 28/28、四方 200/0）。**本任务只是把这个已验证工作的手动流程正规化进构建系统**，不涉及任何新的 codegen/MC 修复。

---

## 背景 / 决策
`printf_hello.test`（`tests/lit/E2E/printf_hello.test`，architect 已建但**未提交**，见 ML-003k 完成区）需要一个 picolibc 编译出的 `libc.a`。picolibc 全量构建较慢（meson+ninja 数分钟），不适合每次 lit 跑都重新编译；但把编译产物（二进制）提交进 git 树，和本仓库一贯的"改动走 patch series 可复现"惯例不一致，且后端改动后容易忘记重新构建导致回归静默失效。**用户决策（2026-07-14）**：改为外部构建步骤，不把二进制入库。

## architect 已验证的手动流程（直接照抄自动化，别重新设计）
```bash
# 1. picolibc meson 配置（cross-file 已由 architect 建好，无 -fno-jump-tables）
cd .work/picolibc
meson setup build-dadao --cross-file scripts/cross-dadao-unknown-elf.txt \
  -Dmultilib=false -Dtests=false -Dsemihost=false -Dpicocrt=false \
  --buildtype=plain -Dprefix=$(pwd)/install-dadao
ninja -C build-dadao   # -O0 全量编译，~810/1102 通过（既有 234 个失败是别的已知问题，非本任务范围）

# 2. 打包 libc.a（从已编出的 .o 全部打包）
llvm-ar rcs <target>/libc.a $(find build-dadao/libc.a.p -name "*.o")
```
Architect 验证过用这个 `libc.a` + `crt0.s` + `tests/scripts/stdout_min.c` + `tests/lit/E2E/Inputs/printf_hello.c` + `pico_stubs.s` 链接，QEMU 真跑出 "hello, dadao" + exit=0。

## 做什么
1. **Makefile 加一个构建 target**（如 `build-picolibc`）：跑上面的 meson+ninja 流程（若 `build-dadao` 已存在/够新则跳过，支持增量），产出 `libc.a` 到某个约定路径（如 `.work/picolibc/build-dadao/libc.a` 或 `tests/scripts/libc_dadao.a`——**注意后者若用这个路径，必须在 `.gitignore` 里排除，不能被 git 追踪**）。
2. **`printf_hello.test` 的 lit RUN 行**：确认引用的 `libc.a` 路径指向构建产物位置（不是仓库内检入的二进制）；测试文档/注释里注明"运行本测试前需先 `make build-picolibc`"。
3. **`.gitignore` 确认排除**构建产物路径（`.work/` 已经整体被排除的话检查一下这条链路上有没有漏网之鱼；如果 target 路径是 `tests/scripts/libc_dadao.a` 之类不在 `.work/` 下的位置，必须显式加进 `.gitignore`）。
4. **文档**：`docs/development-roadmap.md` 或对应位置提一句"picolibc 库需要 `make build-picolibc` 预构建，不随仓库检入"。
5. **验证**：
   - 全新 clone（或删掉构建产物）后跑 `make build-picolibc`，产出 `libc.a`。
   - `llvm-lit tests/lit/E2E/printf_hello.test` 真 PASS（真输出 "hello, dadao" + exit=0）。
   - 全 E2E 28/28、四方 200/0 不回归。
   - **确认没有二进制文件被 git 追踪**（`git status`/`git ls-files` 检查 `libc.a`/`libc_dadao.a` 等不在版本控制里）。

## 约束
- **不修改任何 codegen/MC 代码**——ML-003k 的修复已经足够，本任务纯粹是构建系统/测试基础设施整理。
- **禁止把任何 `.a`/`.o` 编译产物提交进 git**（这是本任务存在的理由）。
- 不回归：E2E 28/28、四方 200/0。

## 验收（架构师亲跑）
```bash
cd ~/DADAO-0628
rm -rf .work/picolibc/build-dadao   # 模拟全新环境
make build-picolibc                 # 应该重新构建出 libc.a
.work/build/llvm/bin/llvm-lit -v tests/lit/E2E/printf_hello.test 2>&1 | grep -E "PASS|FAIL"
.work/build/llvm/bin/llvm-lit tests/lit/E2E/ 2>&1 | tail
python3 tools/run_differential.py 2>&1 | tail -3
git status --short   # 确认无二进制产物被追踪
```

## 参考指针
- ML-003k 完成区（architect 手动验证过的完整流程、meson/ninja 命令、libc.a 打包方式）
- `tests/scripts/{crt0.s,pico_stubs.s,stdout_min.c,dadao.ld}`；`tests/lit/E2E/Inputs/printf_hello.c`；`tests/lit/E2E/printf_hello.test`（architect 已建，未提交）
- `.work/picolibc/scripts/cross-dadao-unknown-elf.txt`（cross-file，已修好无 workaround）

—— 自审见 DS.md §自审流程（subagent 代码级 · 强制；审阅记录占位必填——**AC/零 finding 也写实质记录**）。**subagent 必须真删构建产物模拟全新环境、真跑 make target、真跑测试验证**，别只检查 Makefile 语法。
