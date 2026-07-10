/* DADAO Sail rehearsal slice — init, single-step, terminal-state dump.
 * The fetch-decode-execute loop itself lives in the C harness (sail-riscv
 * style): it calls dadao_step() until it returns false. */

/* Zero all architectural state; PC at the harness load base 0x80000000
 * (matches build_test_binary.BINARY_BASE / gen_min_elf LOAD_ADDR). RA all-zero
 * is the process-entry RegRAS init (spec §1.5). */
val dadao_init : unit -> unit
function dadao_init() = {
  foreach (i from 0 to 63) { RD[i] = 0x0000000000000000 };
  foreach (i from 0 to 63) { RB[i] = 0x0000000000000000 };
  foreach (i from 0 to 63) { RA[i] = 0x0000000000000000 };
  PC = 0x000080000000;
  nextPC = PC + 4;
}

/* Execute one instruction. Returns true to continue. On halt/fault/unimpl it
 * reports the outcome to the C harness via set_result(kind, code):
 *   kind 0x00 = halt  (code = exit code)
 *   kind 0x01 = fault (code = SE fault code; precise — no state was written)
 *   kind 0x02 = unimpl (code = 0x7F; opcode outside the rehearsal slice)
 * Precise exceptions (spec §2.7): PC is only advanced on Ctl_Continue, so a
 * faulting instruction leaves PC at itself and writes no destination. */
val dadao_step : unit -> bool
function dadao_step() = {
  let cur = PC;
  nextPC = cur + 4;
  let w = fetch(cur);
  let instr = decode(w);
  try {
    match execute(instr) {
      Ctl_Continue() => { PC = nextPC; true },
      Ctl_Halt(code) => { set_result(0x00, code); false },
      Ctl_Unimpl()   => { set_result(0x02, 0x7F); false }
    }
  } catch {
    Fault(k) => { set_result(0x01, fault_code(k)); false }
  }
}

/* Unused: the real driver is the C harness (main() in dadao_harness.c) calling
 * zdadao_step. This satisfies the generated model_main's zmain reference; the
 * generated C main() itself is suppressed via --c-no-main. */
function main() -> unit = ()
