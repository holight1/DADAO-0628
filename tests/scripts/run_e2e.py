#!/usr/bin/env python3
import subprocess, sys

qemu = sys.argv[1]
trampoline = sys.argv[2]
binary = sys.argv[3]

r = subprocess.run([qemu, '-M', 'dadao-m1', '-nographic',
                     '-bios', trampoline, '-kernel', binary],
                   capture_output=True, timeout=10)
sys.exit(r.returncode)
