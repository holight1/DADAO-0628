#!/usr/bin/env python3
"""Generate raw binary for e2e smoke tests — no llvm-mc dependency."""
import struct, sys, os

# Available test binaries
SMOKE_ARITH = b''.join(struct.pack('>I', w) for w in [
    (0x19 << 24) | (1 << 18) | (42 & 0xFFF),  # addi rd1, rd0, 42
    (0x00 << 24) | (1 << 18),                 # halt rd1
])

SMOKE_ADD = b''.join(struct.pack('>I', w) for w in [
    (0x19 << 24) | (1 << 18) | (10 & 0xFFF),  # addi rd1, rd0, 10
    (0x19 << 24) | (2 << 18) | (32 & 0xFFF),  # addi rd2, rd0, 32
    (0x1A << 24) | (0 << 18) | (3 << 12) | (1 << 6) | 2,  # add rd0, rd3, rd1, rd2
    (0x00 << 24) | (3 << 18),                 # halt rd3
])

SMOKE_JUMP = b''.join(struct.pack('>I', w) for w in [
    (0x64 << 24) | 1,                         # jump_i 1
    (0x00 << 24) | (1 << 18),                 # halt rd1 (skipped)
    (0x19 << 24) | (1 << 18) | 0,             # addi rd1, rd0, 0
    (0x00 << 24) | (1 << 18),                 # halt rd1 (exit 0)
])

BINARIES = {
    'smoke_arith': (SMOKE_ARITH, 42),
    'smoke_add':   (SMOKE_ADD, 42),
    'smoke_jump':  (SMOKE_JUMP, 0),
}

if __name__ == '__main__':
    name = sys.argv[1]
    binary, expected_exit = BINARIES[name]
    out_path = sys.argv[2]
    import shutil
    if os.path.isdir(out_path):
        out_path = os.path.join(out_path, name + '.bin')
    with open(out_path, 'wb') as f:
        f.write(binary)
