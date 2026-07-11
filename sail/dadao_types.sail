/* DADAO SimRISC (M1) — Sail rehearsal slice: core types, state, exceptions.
 *
 * SL-002a / ADR-0011 M2b. Semantics derived ONLY from contracts/isa/spec.md §
 * and tools/opcodes.yaml (independence rule ADR-0011 D4); structure follows the
 * sail-riscv idiom (register vectors, union instruction, exception throw/try).
 * NOT derived from QEMU translate.c / gem5 decoder.cc.
 */

default Order dec

$include <prelude.sail>

/* ---- architectural state (spec §1) --------------------------------------- */
/* Four banks of 64 x 64-bit registers (spec §1.1). rd0/rb0 have special
 * semantics applied in the accessor wrappers below, not in storage. */
register RD : vector(64, dec, bits(64))   /* data registers   (spec §1.2) */
register RB : vector(64, dec, bits(64))   /* base registers   (spec §1.3) */
register RA : vector(64, dec, bits(64))   /* RegRAS           (spec §1.5) */

register PC     : bits(48)                /* 48-bit program counter (spec §5) */
register nextPC : bits(48)                /* PC of the next instruction; also
                                             the value read back as rb0 = PC+4
                                             during execute (spec §1.3, §5.1) */

/* ---- precise exceptions (spec §2.5–§2.7) --------------------------------- */
enum fault_kind = { F_ILLI, F_MALIGN, F_UNDI, F_RASOF, F_RASUF }

union exception = { Fault : fault_kind }

/* SE fault codes, shared with the QEMU/gem5 harnesses (run_qemu_test.py
 * FAULT_CODES). spec §2.6 ILLI, §3.1 MALIGN, §2.5 UNDI, §5.6 RASOF/RASUF. */
function fault_code(k : fault_kind) -> bits(8) =
  match k {
    F_ILLI   => 0x82,
    F_MALIGN => 0x81,
    F_UNDI   => 0x83,
    F_RASOF  => 0x84,
    F_RASUF  => 0x85
  }

/* Control outcome of executing one instruction. */
union Ctl = {
  Ctl_Continue : unit,
  Ctl_Halt     : bits(8),   /* harness halt (op=0x00), carries exit code   */
  Ctl_Unimpl   : unit       /* valid DADAO opcode not modelled in this slice */
}
