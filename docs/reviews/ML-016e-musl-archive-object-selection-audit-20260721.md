# ML-016e worker evidence：musl archive object selection audit（2026-07-21）

## 审计范围与 ownership

本轮严格按 code-agent/tasks/ML-016e-musl-archive-object-selection-audit.md 执行，只读检查当前 .work/source/musl、.work/build/musl/obj、.work/build/musl/lib/libc.a、生成后的 Makefile/config 和仓库 Makefile；独立编译与 archive 试验全部写入 /tmp/ml-016e-musl-archive-object-selection-audit-20260721/。没有修改主 obj、主 archive、musl source、LLVM/QEMU/gem5 或其他受保护文件，未运行 QEMU/Gem5（本任务的 build/archive 层证据不需要 runtime 验证）。

审计时 source 状态检查原始 git status 为 rc=0，source HEAD 为 4741d4d1105849adf551a7998503866ed4f8b961。主 source Makefile SHA-256 为 58c8b95c68d5326c747e26e7b4ff51560d72fc881fa5492d85f8dcf9af17ab9e；主 .work/build/musl/config.mak SHA-256 为 cf64c040bbb00d29aadf8d6ae138c0b103e5f605cc7c1279cad03323a65e6266。

## 结论

**Audit-accepted-with-findings / Completed**。

结论分成两个边界：

1. Makefile 输入选择没有排除 stdio source。116 个 src/stdio/*.c 都有对应的预期 obj/src/stdio/<name>.o；当前缺失的 28 个全部首次在 object/编译输出层消失。
2. archive 还不是当前 obj 目录的完整快照：3 个已经存在的 aio object 不在主 archive。独立临时打包复现证明 llvm-ar 会打包实际传入的 object；历史 archive 为什么漏掉它们因没有保留的构建/打包日志不能进一步归因。

因此没有 manifest 或源码修复结论；最小后续边界是受控的 partial rebuild + archive regeneration，并保留逐对象命令/退出码，然后再做 link/runtime 复验。

## 1. Makefile/生成清单证据

源码 Makefile 的关键规则为 Makefile:21-35：

    SRC_DIRS = $(addprefix $(srcdir)/,src/* src/malloc/$(MALLOC_DIR) crt ldso $(COMPAT_SRC_DIRS))
    BASE_GLOBS = $(addsuffix /*.c,$(SRC_DIRS))
    BASE_SRCS = $(sort $(wildcard $(BASE_GLOBS)))
    BASE_OBJS = $(patsubst $(srcdir)/%,%.o,$(basename $(BASE_SRCS)))
    ALL_OBJS = $(addprefix obj/, $(filter-out $(REPLACED_OBJS), $(sort $(BASE_OBJS) $(ARCH_OBJS))))
    LIBC_OBJS = $(filter obj/src/%,$(ALL_OBJS)) $(filter obj/compat/%,$(ALL_OBJS))
    AOBJS = $(LIBC_OBJS)

实际命令：

    make -C .work/build/musl --no-print-directory --eval='print-vars: ; @printf ...' print-vars

原始 rc=0。展开结果为：BASE_SRCS=1352、ALL_OBJS=1353、LIBC_OBJS=1346、src/stdio expected object=116。主生成 config 的 srcdir 指向 .work/source/musl，CC 为项目内 DADAO clang，arch/dadao/arch.mak 附加 -fno-optimize-sibling-calls -O0。

lib/libc.a 的 musl 原生规则在 source Makefile:165-168 是 $(AR) rc $@ $(AOBJS)；仓库顶层 Makefile:112-117 另有 best-effort 路径，先使用 make -k，再用 find $(MUSL_BUILD)/obj/src $(MUSL_BUILD)/obj/compat -name '*.o' 手工打包。该顶层 recipe 本身会抑制其 make 子命令的失败状态，且当前 .work/build/musl 没有保留逐对象 build log，所以不能从历史产物反推出每个缺失 object 当时是 skipped 还是 compile failure；本轮没有使用该 recipe，也没有使用 || true 隐藏任何本轮退出码。

## 2. 完整 src/stdio/*.c -> expected object -> archive member 对照

当前 source .c 数量为 116；预期 object 是同 basename 的 obj/src/stdio/<name>.o。当前有 object 的以下 88 项全部也有 archive member：

    __fclose_ca.o __fopen_rb_ca.o __lockfile.o __overflow.o __stdio_close.o
    __stdio_exit.o __stdio_read.o __stdio_seek.o __stdio_write.o __stdout_write.o
    __toread.o __towrite.o __uflow.o asprintf.o clearerr.o dprintf.o ext.o ext2.o
    feof.o ferror.o fgetc.o fgetpos.o fgetws.o flockfile.o fprintf.o fputc.o fputs.o
    fputwc.o fputws.o fread.o fscanf.o fsetpos.o ftell.o ftrylockfile.o funlockfile.o
    fwide.o fwprintf.o fwrite.o fwscanf.o getc.o getc_unlocked.o getchar.o
    getchar_unlocked.o getline.o gets.o getw.o getwc.o getwchar.o ofl.o pclose.o
    printf.o putc.o putc_unlocked.o putchar.o putchar_unlocked.o putw.o putwc.o
    putwchar.o remove.o rename.o rewind.o scanf.o setbuf.o setbuffer.o setlinebuf.o
    setvbuf.o snprintf.o sprintf.o sscanf.o stderr.o stdin.o stdout.o swprintf.o
    swscanf.o tmpfile.o ungetc.o ungetwc.o vdprintf.o vprintf.o vscanf.o vsnprintf.o
    vsprintf.o vswprintf.o vwprintf.o vwscanf.o wprintf.o wscanf.o

以下 28 项均满足：source 存在；Makefile expected object 存在；主 obj 缺失；主 archive member 缺失。因此每项首次缺失层级都是 object/编译输出层，而不是 archive selection 层：

| source | expected object | main obj | main archive | /tmp compile rc |
|---|---|---:|---:|---:|
| __fdopen.c | __fdopen.o | missing | missing | 0 |
| __fmodeflags.c | __fmodeflags.o | missing | missing | 0 |
| fclose.c | fclose.o | missing | missing | 0 |
| fflush.c | fflush.o | missing | missing | 0 |
| fgetln.c | fgetln.o | missing | missing | 0 |
| fgets.c | fgets.o | missing | missing | 0 |
| fgetwc.c | fgetwc.o | missing | missing | 0 |
| fileno.c | fileno.o | missing | missing | 0 |
| fmemopen.c | fmemopen.o | missing | missing | 0 |
| fopen.c | fopen.o | missing | missing | 0 |
| fopencookie.c | fopencookie.o | missing | missing | 0 |
| freopen.c | freopen.o | missing | missing | 0 |
| fseek.c | fseek.o | missing | missing | 0 |
| getdelim.c | getdelim.o | missing | missing | 0 |
| ofl_add.c | ofl_add.o | missing | missing | 0 |
| open_memstream.c | open_memstream.o | missing | missing | 0 |
| open_wmemstream.c | open_wmemstream.o | missing | missing | 0 |
| perror.c | perror.o | missing | missing | 0 |
| popen.c | popen.o | missing | missing | 0 |
| puts.c | puts.o | missing | missing | 2 |
| tempnam.c | tempnam.o | missing | missing | 0 |
| tmpnam.c | tmpnam.o | missing | missing | 0 |
| vasprintf.c | vasprintf.o | missing | missing | 0 |
| vfprintf.c | vfprintf.o | missing | missing | 2 |
| vfscanf.c | vfscanf.o | missing | missing | 2 |
| vfwprintf.c | vfwprintf.o | missing | missing | 0 |
| vfwscanf.c | vfwscanf.o | missing | missing | 0 |
| vsscanf.c | vsscanf.o | missing | missing | 0 |

主 archive 的 llvm-ar t 原始 rc=0，member 数为 1002；llvm-nm -A 原始 rc=0。关键 archive member 结果：fputs.o、fwrite.o、__stdio_write.o、__stdout_write.o、stdout.o 存在；fflush.o、fileno.o、__fdopen.o 不存在。主 archive SHA-256 为 1b62bd670f481b0b46808639a65072021eca8f6d03d81adafa520e5c13ca07ee，mtime 为 2026-07-18 15:00:32.375253784 +0800。

## 3. 主 obj/archive 快照一致性

实际命令为：

    find .work/build/musl/obj/src .work/build/musl/obj/compat -type f -name '*.o'
    llvm-ar t .work/build/musl/lib/libc.a

主 obj 文件数为 1005，主 archive member 数为 1002。按 member basename 对照，obj 中有而 archive 中没有的恰好是：

    aio.o aio_suspend.o lio_listio.o

archive 中没有 obj basename 之外的 member。三个 object 的实际时间戳分别为 2026-07-18 14:54:48 +0800 附近，SHA-256 为：

    aio.o         8f30d48356cc0a41f3aff909d8687a47eb2e3690ab4bc22270a395b01ec478c8
    aio_suspend.o 389802d4137000bbf22c8459692ea79e15a8891caf280015b408970f011772a6
    lio_listio.o  f234a563b4f1c4d94e732fb22fc1714080e9ccfa0e453f3347847374cf08fdc1

这把 archive 层的首次缺失明确为 archive packaging/input snapshot 层，而不是当前 filesystem object 层。由于没有主构建日志，不能再断言具体是陈旧 archive、不同的历史 find 输入，还是后续对象生成顺序；不能把它写成确定的单一根因。

## 4. /tmp 独立编译复现

试验目录：

    /tmp/ml-016e-musl-archive-object-selection-audit-20260721/repro-20260721-1/

2026-07-21 14:11:24 +0800 复制 source，并用主 config 的同一 clang、target、include、-fno-optimize-sibling-calls -O0 生成临时 build。每个目标都执行了如下实际命令形状，并把完整 stdout/stderr 写入各自 .make.raw：

    make -C /tmp/.../repro-20260721-1/build --no-print-directory -j1 obj/src/stdio/<name>.o

结果为 25 个原始 rc=0、3 个原始 rc=2。puts.o 的原始诊断是 error in backend: Cannot select ... sign_extend_inreg；vfprintf.o 和 vfscanf.o 的原始诊断是 error in backend: unsupported library call operation。这三个失败不属于本轮要修复的 archive selection；它们的失败原文和完整命令仍在 puts.make.raw、vfprintf.make.raw、vfscanf.make.raw。

与 ML-016d 直接相关的三个 source 都在独立副本成功编译：

| source | original compile rc | temp object stat | temp object SHA-256 |
|---|---:|---|---|
| __fdopen.c | 0 | 3192 bytes, 14:11:25.693482239 +0800 | ff281f2a5844acc9f6c5d198d380f7e6637d75f98bb557f82c4e78c3fa823ef2 |
| fflush.c | 0 | 2488 bytes, 14:11:25.912482261 +0800 | c25cb171aa9eaea0ad59ee59a9327284c26a6a8f6aeb82dfbfaa43fcb2b00b56 |
| fileno.c | 0 | 1384 bytes, 14:11:26.216482291 +0800 | 3730dc2349a7b2c9093535c97e11786fe455145338c3b7da32fcdd04cdbdd6d3 |

对应主 source 的 mtime 都是 2026-07-17 04:56:20 +0800；source SHA-256 为：

    __fdopen.c 709b39da1b9ef5a8b9bf7f1dba17355f9743300c7142069d7a5c9ebbd3f0e565
    fflush.c   856ac1841cdeeeb3df3f47bfbea5fae0746b5c9ac67d9113588f8d1375f6eb55
    fileno.c   239efa861cffcc71a4d11691a8b7e367905ffca70e310180ece1db20d20203ff

完整 116 行 source stat/hash/object/archive 矩阵在临时文件 /tmp/ml-016e-musl-archive-object-selection-audit-20260721/stdio-matrix.tsv，SHA-256 为 0cd0be26b26f01d0e9b0dca5a1a7a22ad5304153271c5d9cc26a17901296adc1。

## 5. /tmp archive packaging 复现

复制主 obj 快照后，实际执行与顶层 packaging 同形状的命令：

    find /tmp/.../pack-input/obj/src /tmp/.../pack-input/obj/compat -type f -name '*.o'
    llvm-ar rc /tmp/.../pack-current/libc.a $(find ... -name '*.o' 2>/dev/null)
    llvm-ranlib /tmp/.../pack-current/libc.a
    llvm-ar t /tmp/.../pack-current/libc.a

原始结果：find rc=1（obj/compat 不存在，但 stdout 仍列出 1005 个 src objects）、llvm-ar rc=0、llvm-ranlib=0、llvm-ar t=0，临时 archive 有 1005 个 member，SHA-256 为 8d79688938aa458a17f5edcc4eaf2e19eef7ce2ac5d35a3fd0c1e7d5237eaf7c，并包含 aio.o、aio_suspend.o、lio_listio.o。这说明打包命令本身会收录实际输入，主 archive 的 1002 member 不是当前 1005 object 的完整再现。

第二轮把独立编译成功的 25 个 stdio object 加入同一临时输入目录后再次打包：find rc=1、llvm-ar rc=0、llvm-ranlib=0、llvm-ar t=0，输入/member 均为 1030，archive SHA-256 为 5c5bc70069d3ecdf6d04001bc6d51c37cab8a0da5442c2e95f33e4b7d90854c2。第二轮包含 __fdopen.o、fflush.o、fileno.o 等 25 个新 object，但仍不包含 puts.o、vfprintf.o、vfscanf.o，与编译结果完全一致。

主 obj 输入的完整 path/size/mtime/SHA-256 清单在：
/tmp/ml-016e-musl-archive-object-selection-audit-20260721/repro-20260721-1/setup-and-inputs.raw

## 6. 最小后续边界与限制

- 不改 Makefile wildcard、source 或 manifest；当前 evidence 不支持 manifest selection bug。
- 新任务应在隔离 build 目录 clean/controlled 地重建缺失 object，逐对象保存 clang 原始 rc，再以该 object 清单重建 archive；主 archive 不在本任务中重建。
- 对 puts/vfprintf/vfscanf 的 LLVM backend rc=2 应作为独立 codegen/build finding 处理，不能混入 fflush/fileno/__fdopen 的 archive 归因。
- 本轮没有做 link、QEMU、Gem5 或 stdio runtime 验收；补齐 object/member 只说明 build/archive 层边界被定位，不说明 writev responder、stdio 高层输出或 ML-014a 已修复。
