"""Generate trampoline.bin — 32 bytes.

Sets SP (rb1) = 0x87FF0000, then jumps to 0x80000000 (RAM entry).
"""

import struct
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from build_test_binary import write_rwii, write_rrii


def gen():
    out = bytearray()
    write_rwii(out, 0x4E, 1, 1, 0x87FF)
    write_rwii(out, 0x4E, 2, 1, 0x8000)
    write_rrii(out, 0x65, 2, 0, 0)
    swym = struct.pack('>I', 0x10000000)
    while len(out) < 32:
        out.extend(swym)
    return bytes(out)


if __name__ == '__main__':
    data = gen()
    path = os.path.join(os.path.dirname(__file__), 'trampoline.bin')
    with open(path, 'wb') as f:
        f.write(data)
    print(f'Wrote {len(data)} bytes to {path}')
