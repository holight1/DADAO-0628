# Phase 3 QEMU Test Harness

## Files

| File | Purpose |
|------|---------|
| `build_test_binary.py` | Build raw binary from a YAML test vector case |
| `trampoline.bin` | 32-byte ROM trampoline: sets SP (rb1)=0x87FF0000, jumps to 0x80000000 |
| `run_qemu_test.py` | Run a test case through `qemu-system-dadao -M dadao-m1` |

## Usage

```bash
# Run all cases from a YAML file
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-arith.yaml

# Run a single case by YAML text
python3 tests/scripts/run_qemu_test.py --qemu /path/to/qemu-system-dadao '{"encoding":{"word":"0x19042005"},"input_state":{"rd":{"rd2":"0xA"}}}'

# Pass a custom QEMU binary
python3 tests/scripts/run_qemu_test.py tests/vectors/isa/rd-arith.yaml --qemu .work/source/qemu/build/qemu-system-dadao
```

## Binary layout (build_test_binary)

1. **Register loader** — `setzw`+`orw` sequences to set `rd`/`rb` from `input_state`
2. **Memory setup** — pre-load memory values from `input_state.memory` (if present)
3. **Test instruction** — raw 4-byte encoding from `encoding.word`
4. **Dump** (reserved for Phase 4)
5. **Exit** — `halt rd<reg>` instruction writes exit code to MMIO port at `0x10000000`

## QEMU exit codes

| Exit code | Interpretation |
|-----------|---------------|
| 0 | PASS — test instruction executed and normal exit |
| 130 (0x82) | FAIL — exception (ILLI, UNDI) during execution |
| Other | FAIL — unexpected error |

## Requirements

- Python 3.8+
- PyYAML
- QEMU with `dadao-softmmu` target and `dadao-m1` machine
