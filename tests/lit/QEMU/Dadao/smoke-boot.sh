#!/bin/bash
# Minimal smoke test: qemu-system-dadao starts and doesn't crash

QEMU_BIN="${QEMU_BIN:-qemu-system-dadao}"

if ! command -v "$QEMU_BIN" &>/dev/null; then
    echo "SKIP: $QEMU_BIN not found in PATH"
    exit 0
fi

# Expect exit code 8 (SIGILL or unmapped access on empty ROM)
"$QEMU_BIN" -machine m1 -nographic -nodefaults -d unimp -v -M none 2>&1
RC=$?
echo "qemu-system-dadao exited with code $RC"
exit $RC
