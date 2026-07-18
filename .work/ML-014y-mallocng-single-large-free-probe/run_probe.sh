#!/usr/bin/env bash
set -uo pipefail

ROOT=/home/holight/DADAO-0628
WORK="$ROOT/.work/ML-014y-mallocng-single-large-free-probe"
BIN="$ROOT/.work/build/llvm/bin"
MUSL="$ROOT/.work/build/musl/lib"
SCRIPT="$ROOT/tests/scripts/dadao.ld"
SRC="$WORK/malloc_single_large_free.c"
OBJ="$WORK/malloc_single_large_free.o"
ELF="$WORK/malloc_single_large_free.elf"
FLAT="$WORK/malloc_single_large_free.bin"
MAP="$WORK/malloc_single_large_free.map"
WHY="$WORK/malloc_single_large_free.why-extract.tsv"
QEMU="$ROOT/.work/source/qemu/build/qemu-system-dadao"
TRAMP="$ROOT/tests/scripts/trampoline.bin"
GEM5=/home/holight/DADAO-gem5/build/DADAO/gem5.opt
GEM5_SE=/home/holight/DADAO-gem5/tests/dadao/dadao_se.py
LOCKED=("$BIN/clang" "$BIN/ld.lld" "$MUSL/crt1.o" "$MUSL/libc.a" "$SCRIPT")
FLAGS=(--target=dadao -std=c99 -nostdinc -ffreestanding -O0)

record_state() {
	{
		echo "date=$(date -Is)"
		echo "root_head=$(git -C "$ROOT" rev-parse HEAD)"
		echo "llvm_source_head=$(git -C "$ROOT/.work/source/llvm" rev-parse HEAD)"
		echo "qemu_source_head=$(git -C "$ROOT/.work/source/qemu" rev-parse HEAD)"
		echo "gem5_source_head=$(git -C /home/holight/DADAO-gem5 rev-parse HEAD)"
		echo '--- root status ---'
		git -C "$ROOT" status --short --branch --untracked-files=all
		echo '--- llvm source status ---'
		git -C "$ROOT/.work/source/llvm" status --short --branch
		echo '--- qemu source status ---'
		git -C "$ROOT/.work/source/qemu" status --short --branch
		echo '--- gem5 source status ---'
		git -C /home/holight/DADAO-gem5 status --short --branch
	} > "$WORK/baseline-state.txt"
}

record_state
sha256sum "${LOCKED[@]}" > "$WORK/locked.before.sha256"
stat -Lc '%n|size=%s|mtime=%y|inode=%i' "${LOCKED[@]}" \
	> "$WORK/locked.before.stat"
sha256sum "$QEMU" "$GEM5" "$TRAMP" > "$WORK/runtime-tools.before.sha256"
"$BIN/clang" --version > "$WORK/clang.version.txt"
{
	printf 'compile:'
	printf ' %q' "$BIN/clang" "${FLAGS[@]}" -c -o "$OBJ" "$SRC"
	printf '\nlink:'
	printf ' %q' "$BIN/ld.lld" -T "$SCRIPT" -Map="$MAP" \
		--why-extract="$WHY" --start-group "$MUSL/crt1.o" "$OBJ" \
		"$MUSL/libc.a" --end-group -o "$ELF"
	printf '\nobjcopy:'
	printf ' %q' "$BIN/llvm-objcopy" -O binary "$ELF" "$FLAT"
	printf '\nqemu:'
	printf ' %q' timeout 15s "$QEMU" -M dadao-m1 -nographic -bios "$TRAMP" \
		-kernel "$FLAT"
	printf '\ngem5:'
	printf ' %q' timeout 15s "$GEM5" --outdir="$WORK/m5out" \
		--debug-flags=Exec --debug-file=gem5.exec.trace "$GEM5_SE" "$ELF"
	printf '\n'
} > "$WORK/commands.txt"

set +e
"$BIN/clang" "${FLAGS[@]}" -c -o "$OBJ" "$SRC" \
	> "$WORK/compile.stdout" 2> "$WORK/compile.stderr"
compile_rc=$?
set -e
echo "$compile_rc" > "$WORK/compile.rc"
if (( compile_rc != 0 )); then exit "$compile_rc"; fi

"$BIN/llvm-nm" --undefined-only "$OBJ" > "$WORK/object.undefined.txt"
"$BIN/llvm-readobj" --file-header --sections --symbols --relocations "$OBJ" \
	> "$WORK/object.readobj.txt"
"$BIN/llvm-objdump" -dr --triple=dadao "$OBJ" \
	> "$WORK/object.disassembly.txt"

set +e
"$BIN/ld.lld" -T "$SCRIPT" -Map="$MAP" --why-extract="$WHY" \
	--start-group "$MUSL/crt1.o" "$OBJ" "$MUSL/libc.a" --end-group \
	-o "$ELF" > "$WORK/link.stdout" 2> "$WORK/link.stderr"
link_rc=$?
set -e
echo "$link_rc" > "$WORK/link.rc"
if (( link_rc != 0 )); then exit "$link_rc"; fi

set +e
"$BIN/llvm-objcopy" -O binary "$ELF" "$FLAT" \
	> "$WORK/objcopy.stdout" 2> "$WORK/objcopy.stderr"
objcopy_rc=$?
set -e
echo "$objcopy_rc" > "$WORK/objcopy.rc"
if (( objcopy_rc != 0 )); then exit "$objcopy_rc"; fi

"$BIN/llvm-readobj" --file-header --program-headers --sections --symbols \
	--relocations "$ELF" > "$WORK/elf.readobj.txt"
"$BIN/llvm-objdump" -d --triple=dadao "$ELF" > "$WORK/elf.disassembly.txt"
"$BIN/llvm-nm" "$ELF" > "$WORK/elf.nm.txt"
"$BIN/llvm-objdump" -d --disassemble-symbols=main --triple=dadao "$ELF" \
	> "$WORK/main.disassembly.txt"
"$BIN/llvm-objdump" -d --disassemble-symbols=free --triple=dadao "$ELF" \
	> "$WORK/free-wrapper.disassembly.txt"
"$BIN/llvm-objdump" -d --disassemble-symbols=__libc_free --triple=dadao "$ELF" \
	> "$WORK/libc-free.disassembly.txt"
"$BIN/llvm-objdump" -d --disassemble-symbols=munmap --triple=dadao "$ELF" \
	> "$WORK/munmap.disassembly.txt"
rg -o 'libc\.a\([^)]+\)' "$MAP" > "$WORK/libc-members.all.txt"
sort -u "$WORK/libc-members.all.txt" > "$WORK/libc-members.txt"
{
	rg -n 'malloc|free|__libc_free|munmap|__munmap' "$WHY" "$MAP" \
		"$WORK/elf.nm.txt" || true
} > "$WORK/allocator-link-focus.txt"
{
	rg -n 'printf|puts|write|snprintf|sprintf|vfprintf|vprintf' \
		"$WORK/object.undefined.txt" "$WORK/elf.nm.txt" "$WORK/libc-members.txt" \
		|| true
} > "$WORK/forbidden-output-dependencies.txt"
{
	rg -n 'call|stb|ldbu|setzw|orw|131051|1ffeb|ffeb|-21|phase_marker' \
		"$WORK/main.disassembly.txt" || true
} > "$WORK/main-control-memory-focus.txt"
{
	rg -n '80000200:.*call 1152|80001404:|80001404:.*call 1|8000140c:|800017b0:.*call 1260|80002b64:|trap' \
		"$WORK/main.disassembly.txt" "$WORK/free-wrapper.disassembly.txt" \
		"$WORK/libc-free.disassembly.txt" "$WORK/munmap.disassembly.txt" || true
} > "$WORK/free-munmap-call-focus.txt"

sha256sum "$SRC" "$OBJ" "$ELF" "$FLAT" "$MAP" "$WHY" \
	> "$WORK/artifacts.sha256"

set +e
timeout 15s "$QEMU" -M dadao-m1 -nographic -bios "$TRAMP" \
	-kernel "$FLAT" > "$WORK/qemu.stdout" 2> "$WORK/qemu.stderr"
qemu_rc=$?
set -e
echo "$qemu_rc" > "$WORK/qemu.rc"
if (( qemu_rc == 124 )); then echo timeout; else echo no-timeout; fi \
	> "$WORK/qemu.timeout"
{
	rg -n 'fault|Fault|panic|fatal|abort|segmentation|illegal|unimplemented' \
		"$WORK/qemu.stdout" "$WORK/qemu.stderr" || true
} > "$WORK/qemu.fault-focus.txt"

if [[ -d "$WORK/m5out" ]]; then
	find "$WORK/m5out" -mindepth 1 -delete
else
	mkdir "$WORK/m5out"
fi
set +e
timeout 15s "$GEM5" --outdir="$WORK/m5out" --debug-flags=Exec \
	--debug-file=gem5.exec.trace "$GEM5_SE" "$ELF" \
	> "$WORK/gem5.stdout" 2> "$WORK/gem5.stderr"
gem5_rc=$?
set -e
echo "$gem5_rc" > "$WORK/gem5.rc"
if (( gem5_rc == 124 )); then echo timeout; else echo no-timeout; fi \
	> "$WORK/gem5.timeout"
{
	rg -n 'SIM_END|trap-exit|fault|Fault|panic|fatal|abort|segmentation|illegal|unimplemented' \
		"$WORK/gem5.stdout" "$WORK/gem5.stderr" || true
} > "$WORK/gem5.result-focus.txt"

munmap_addr=$("$BIN/llvm-nm" "$ELF" | awk '$3 == "__munmap" { print $1; exit }')
free_addr=$("$BIN/llvm-nm" "$ELF" | awk '$3 == "free" { print $1; exit }')
libc_free_addr=$("$BIN/llvm-nm" "$ELF" | awk '$3 == "__libc_free" { print $1; exit }')
{
	echo "free_addr=0x$free_addr"
	echo "libc_free_addr=0x$libc_free_addr"
	echo "munmap_addr=0x$munmap_addr"
	if [[ -f "$WORK/m5out/gem5.exec.trace" ]]; then
		rg -n '@free |@__libc_free( |\+932)|@munmap( |\+36)' \
			"$WORK/m5out/gem5.exec.trace" || true
	fi
} > "$WORK/gem5.free-munmap-runtime-focus.txt"

sha256sum "${LOCKED[@]}" > "$WORK/locked.after.sha256"
stat -Lc '%n|size=%s|mtime=%y|inode=%i' "${LOCKED[@]}" \
	> "$WORK/locked.after.stat"
sha256sum "$QEMU" "$GEM5" "$TRAMP" > "$WORK/runtime-tools.after.sha256"
set +e
cmp "$WORK/locked.before.sha256" "$WORK/locked.after.sha256"
locked_cmp_rc=$?
cmp "$WORK/runtime-tools.before.sha256" "$WORK/runtime-tools.after.sha256"
runtime_tools_cmp_rc=$?
set -e
echo "$locked_cmp_rc" > "$WORK/locked-hash-cmp.rc"
echo "$runtime_tools_cmp_rc" > "$WORK/runtime-tools-hash-cmp.rc"
sha256sum "$ELF" "$FLAT" "$QEMU" "$GEM5" > "$WORK/runtime-inputs.sha256"

validation_rc=0
if (( qemu_rc != 42 || gem5_rc != 42 || locked_cmp_rc != 0 || \
	runtime_tools_cmp_rc != 0 )); then
	validation_rc=1
fi
if ! rg -q '^ +U free$' "$WORK/object.undefined.txt" || \
	! rg -q '^ +U malloc$' "$WORK/object.undefined.txt" || \
	[[ $(wc -l < "$WORK/object.undefined.txt") -ne 2 ]]; then
	validation_rc=1
fi
if ! rg -q '80000200:.*call 1152' "$WORK/main.disassembly.txt" || \
	! rg -q '80001404:.*call 1' "$WORK/free-wrapper.disassembly.txt" || \
	! rg -q '800017b0:.*call 1260' "$WORK/libc-free.disassembly.txt" || \
	! rg -q '80002b88:.*trap 2, 0' "$WORK/munmap.disassembly.txt" || \
	! rg -q 'libc\.a\(free\.o\)' "$WHY" || \
	! rg -q 'libc\.a\(munmap\.o\)' "$WHY"; then
	validation_rc=1
fi
if rg -q 'stb .*,-21|ldbu .*,-21|stb .* -21|ldbu .* -21' \
	"$WORK/main.disassembly.txt" || \
	[[ -s "$WORK/forbidden-output-dependencies.txt" ]]; then
	validation_rc=1
fi
if ! rg -q '@free .*call' "$WORK/gem5.free-munmap-runtime-focus.txt" || \
	! rg -q '@__libc_free .*addi' "$WORK/gem5.free-munmap-runtime-focus.txt" || \
	! rg -q '@munmap .*addi' "$WORK/gem5.free-munmap-runtime-focus.txt" || \
	! rg -q '@munmap\+36 .*trap' "$WORK/gem5.free-munmap-runtime-focus.txt"; then
	validation_rc=1
fi
echo "$validation_rc" > "$WORK/validation.rc"
{
	echo "compile_rc=$compile_rc"
	echo "link_rc=$link_rc"
	echo "objcopy_rc=$objcopy_rc"
	echo "qemu_rc=$qemu_rc"
	echo "qemu_timeout=$(<"$WORK/qemu.timeout")"
	echo "gem5_rc=$gem5_rc"
	echo "gem5_timeout=$(<"$WORK/gem5.timeout")"
	echo "locked_cmp_rc=$locked_cmp_rc"
	echo "runtime_tools_cmp_rc=$runtime_tools_cmp_rc"
	echo "validation_rc=$validation_rc"
} > "$WORK/result.txt"

exit "$validation_rc"
