#!/usr/bin/env python3
"""Generate DADAO assembly for RAS overflow (RASOF) E2E test.

RAS has 63 slots (ra[1]-ra[63]). We create 64 nested calls with different
return addresses so that the 64th call overflows: ra[1] is non-zero and a
new entry cannot be shifted in → RASOF (0x84).
"""
import sys

n = 64  # call depth — 1 push from _start + 62 shifts + 1 overflow

sys.stdout.write('''.text
.globl _start
_start:
\tcall f1
\thalt rd30
''')

for i in range(1, n):
    sys.stdout.write(f'f{i}:\n')
    sys.stdout.write(f'\tcall f{i+1}\n')
    sys.stdout.write('\tret rd0, 0\n')

sys.stdout.write(f'f{n}:\n')
sys.stdout.write('\tret rd0, 0\n')
