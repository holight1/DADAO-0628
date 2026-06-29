# Test Vector Schema

Schema for `tests/vectors/isa/*.yaml` files.

## YAML Structure

Each file contains a YAML list. Each element is a test case with the
following fields:

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `mnemonic` | string | Instruction mnemonic (matches `tools/opcodes.yaml`) |
| `format` | string | Instruction format type (matches `tools/opcodes.yaml`) |
| `class` | string | Vector class: `encoding` / `legality` / `semantic` / `boundary` / `overlap` |
| `encoding.word` | string | Full 32-bit instruction word in hex, e.g. `"0x1A000000"` |
| `input_state` | object | Pre-execution register/memory state (only relevant fields) |
| `wiki_cite` | string | Source spec section |

### Optional / Conditional Fields

| Field | Type | Condition | Description |
|-------|------|-----------|-------------|
| `expected_state` | object or null | Required for active `semantic`/`boundary`/`overlap`; null for `encoding`, `legality`, and deferred cases | Post-execution register/memory state |
| `expected_fault` | string or null | Optional | Expected fault: `null` / `ILLI` / `UNDI` / `MALIGN` / `IALIGN` / `RASOF` / `RASUF` |
| `status` | string | Optional, default `active` | `active` or `deferred` |
| `deferred_reason` | string | Required if `status=deferred` | Reason string (e.g. `"C-27"`) |
| `notes` | string | Optional | Human-readable notes |

### input_state / expected_state Format

Register state: bank name → architectural register name (lowercase, including bank prefix) → 64-bit hex string.

```yaml
input_state:
  rd:
    rd1: "0x0000000000000001"
    rd2: "0x0000000000000002"
  rb:
    rb0: "0x0000000000100000"   # PC (next instruction address)
    rb2: "0x0000000000100000"
```

Memory state (when relevant):
```yaml
input_state:
  memory:
    - address: "0x0000000000100000"
      value: "0x1234567890ABCDEF"
      width: 8
```

### class Definitions

| class | expected_state | expected_fault | Purpose |
|-------|---------------|----------------|---------|
| `encoding` | null or N/A | null | Verify word matches opcodes.yaml mask/value |
| `legality` | null | ILLI | Illegal operand combination |
| `semantic` | required | null | Normal operation, correct results |
| `boundary` | required | null or ILLI | Edge cases (min/max/zero/overflow) |
| `overlap` | required or null | null or ILLI | src=dst register overlap |

### Fault Types

| Fault | Meaning |
|-------|---------|
| `ILLI` | Illegal instruction |
| `UNDI` | Reserved encoding |
| `MALIGN` | Misaligned memory access |
| `IALIGN` | Misaligned instruction fetch |
| `RASOF` | RegRAS overflow |
| `RASUF` | RegRAS underflow |
