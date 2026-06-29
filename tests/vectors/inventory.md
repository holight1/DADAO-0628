# Test Vector Inventory

Coverage is keyed by opcode identity, not mnemonic+format, so RD/RB variants are tracked independently.
A check mark means at least one case of that explicit class exists; every case also carries an encoding word.

| Opcode identity | Instruction | File | encoding | legality | semantic | boundary | overlap | Notes |
|---|---|---|---|---|---|---|---|---|
| 0x10/ha=0x00 | swym (oiii) | misc.yaml | ✓ | — | ✓ | — | — |  |
| 0x10/ha=0x08 | and (orrr) | rd-logic.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x09 | orr (orrr) | rd-logic.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x0A | xor (orrr) | rd-logic.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x0B | xnor (orrr) | rd-logic.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x11 | shlu (orrr) | rd-shift-extend.yaml | — | ✓ | ✓ | — | — |  |
| 0x10/ha=0x12 | shrs (orrr) | rd-shift-extend.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x13 | shru (orrr) | rd-shift-extend.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x14 | exts (orrr) | rd-shift-extend.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x15 | extz (orrr) | rd-shift-extend.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x19 | shlu (orri) | rd-shift-extend.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x1A | shrs (orri) | rd-shift-extend.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x1B | shru (orri) | rd-shift-extend.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x1C | exts (orri) | rd-shift-extend.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x1D | extz (orri) | rd-shift-extend.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x24 | cmps (orrr) | rd-compare.yaml | — | — | ✓ | ✓ | — |  |
| 0x10/ha=0x25 | cmpu (orrr) | rd-compare.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x28 | rd2rd (orri) | rd-wyde-block.yaml | — | ✓ | ✓ | — | — |  |
| 0x10/ha=0x29 | rd2rb (orri) | rd-wyde-block.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x2A | rb2rd (orri) | rd-wyde-block.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x2B | rb2rb (orri) | rd-wyde-block.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x2D | cmp (orrr) | rb-ops.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x2E | add (orrr) | rb-ops.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x2F | sub (orrr) | rb-ops.yaml | — | — | ✓ | — | — |  |
| 0x10/ha=0x3F | unimp (oiii) | misc.yaml | ✓ | ✓ | — | — | — |  |
| 0x12 | cmps (rrii) | rd-compare.yaml | — | ✓ | ✓ | — | — |  |
| 0x13 | cmpu (rrii) | rd-compare.yaml | — | — | ✓ | — | — |  |
| 0x14 | orw (rwii) | rd-wyde-block.yaml | — | — | ✓ | — | — |  |
| 0x15 | andnw (rwii) | rd-wyde-block.yaml | — | — | ✓ | — | — |  |
| 0x16 | setzw (rwii) | rd-wyde-block.yaml | — | — | ✓ | — | — |  |
| 0x17 | setow (rwii) | rd-wyde-block.yaml | — | — | ✓ | — | — |  |
| 0x19 | addi (rrii) | rd-arith.yaml | — | ✓ | ✓ | ✓ | — |  |
| 0x1A | add (rrrr) | rd-arith.yaml | — | ✓ | ✓ | ✓ | — |  |
| 0x1B | sub (rrrr) | rd-arith.yaml | — | — | ✓ | — | — |  |
| 0x1C | muls (rrrr) | rd-arith.yaml | — | — | ✓ | — | — |  |
| 0x1D | mulu (rrrr) | rd-arith.yaml | — | — | ✓ | — | — |  |
| 0x1E | divs (rrrr) | rd-arith.yaml | — | ✓ | ✓ | — | — |  |
| 0x1F | divu (rrrr) | rd-arith.yaml | — | — | ✓ | — | — |  |
| 0x20 | csn (rrrr) | rd-cond-assign.yaml | — | — | ✓ | — | deferred C-27 |  |
| 0x22 | csz (rrrr) | rd-cond-assign.yaml | — | — | ✓ | — | deferred C-27 |  |
| 0x24 | csp (rrrr) | rd-cond-assign.yaml | — | — | ✓ | — | deferred C-27 |  |
| 0x26 | cseq (rrrr) | rd-cond-assign.yaml | — | — | ✓ | — | deferred C-27 |  |
| 0x27 | csne (rrrr) | rd-cond-assign.yaml | — | — | ✓ | — | deferred C-27 |  |
| 0x28 | brn (riii) | control-flow.yaml | — | — | ✓ | — | — |  |
| 0x29 | brnn (riii) | control-flow.yaml | — | — | ✓ | — | — |  |
| 0x2A | brz (riii) | control-flow.yaml | — | — | ✓ | ✓ | — |  |
| 0x2B | brnz (riii) | control-flow.yaml | — | — | ✓ | — | — |  |
| 0x2C | brp (riii) | control-flow.yaml | — | — | ✓ | — | — |  |
| 0x2D | brnp (riii) | control-flow.yaml | — | — | ✓ | — | — |  |
| 0x2E | breq (rrii) | control-flow.yaml | — | — | ✓ | — | — |  |
| 0x2F | brne (rrii) | control-flow.yaml | — | — | ✓ | — | — |  |
| 0x30 | ldbs (rrii) | rd-load-store.yaml | — | ✓ | ✓ | — | — |  |
| 0x31 | ldws (rrii) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x32 | ldts (rrii) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x33 | ldo (rrii) | rd-load-store.yaml | — | — | ✓ | ✓ | — |  |
| 0x34 | ldmbs (rrri) | rd-load-store.yaml | — | ✓ | ✓ | — | — |  |
| 0x35 | ldmws (rrri) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x36 | ldmts (rrri) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x37 | ldmo (rrri) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x38 | stb (rrii) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x39 | stw (rrii) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x3A | stt (rrii) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x3B | sto (rrii) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x3C | stmb (rrri) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x3D | stmw (rrri) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x3E | stmt (rrri) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x3F | stmo (rrri) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x40 | ldbu (rrii) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x41 | ldwu (rrii) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x42 | ldtu (rrii) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x43 | ldo (rrii) | rb-ops.yaml | — | ✓ | ✓ | — | — |  |
| 0x44 | ldmbu (rrri) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x45 | ldmwu (rrri) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x46 | ldmtu (rrri) | rd-load-store.yaml | — | — | ✓ | — | — |  |
| 0x47 | ldmo (rrri) | **MISSING** | — | — | — | — | — | No vector case for this opcode identity. |
| 0x48 | rela (riii) | rb-ops.yaml | — | — | ✓ | — | — |  |
| 0x49 | addi (rrii) | rb-ops.yaml | — | — | ✓ | ✓ | — |  |
| 0x4B | sto (rrii) | rb-ops.yaml | — | — | ✓ | — | — |  |
| 0x4C | orw (rwii) | rd-wyde-block.yaml | — | — | ✓ | — | — |  |
| 0x4D | andnw (rwii) | **MISSING** | — | — | — | — | — | No vector case for this opcode identity. |
| 0x4E | setzw (rwii) | rd-wyde-block.yaml | — | — | ✓ | — | — |  |
| 0x4F | stmo (rrri) | rb-ops.yaml | — | ✓ | ✓ | — | — |  |
| 0x64 | jump (iiii) | control-flow.yaml | — | — | ✓ | — | — |  |
| 0x65 | jump (rrii) | control-flow.yaml | — | — | ✓ | — | — |  |
| 0x6C | call (iiii) | control-flow.yaml | — | — | ✓ | — | — |  |
| 0x6D | call (rrii) | control-flow.yaml | — | — | ✓ | — | — |  |
| 0x6E | ret (riii) | control-flow.yaml | — | — | ✓ 2 | — | — |  |
