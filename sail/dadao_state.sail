/* DADAO Sail rehearsal slice — register accessors + big-endian memory.
 * Semantics: spec §1.2 (rd0=0), §1.3 (rb0=PC+4, 48-bit), §2.1 (big-endian). */

/* Memory lives in the C harness; Sail assembles multi-byte accesses big-endian
 * (spec §2.1). These are the only primitives crossing the Sail/C boundary for
 * memory, mirroring sail-riscv's read_ram/write_ram platform hooks. */
val read_ram_byte  = impure "read_ram_byte"  : bits(48) -> bits(8)
val write_ram_byte = impure "write_ram_byte" : (bits(48), bits(8)) -> unit

/* Run-result reporting to the C harness (kind: 0=halt, 1=fault, 2=unimpl).
 * Terminal register state is read directly from the exported zRD/zRB globals by
 * the C harness, so no per-register callback is needed. */
val set_result = impure "set_result" : (bits(8), bits(8)) -> unit

/* ---- RD accessors (spec §1.2) -------------------------------------------- */
/* rd0 hardwired zero: reads return 0, writes are discarded (no-op). Legality
 * of rd0 as a destination is enforced per-instruction (spec §2.6.1). */
function read_RD(r : bits(6)) -> bits(64) =
  if r == 0b000000 then 0x0000000000000000 else RD[unsigned(r)]

function write_RD(r : bits(6), v : bits(64)) -> unit =
  if r == 0b000000 then () else RD[unsigned(r)] = v

/* ---- RB accessors (spec §1.3) -------------------------------------------- */
/* rb0 = current_PC + 4 (hardware-maintained). During execute, nextPC already
 * holds PC+4, so rb0 reads back nextPC (before any branch retargets it).
 * rb0[63:48] = 0; general RB writes keep the 48-bit effective width. */
function read_RB(r : bits(6)) -> bits(64) =
  if r == 0b000000 then sail_zero_extend(nextPC, 64) else RB[unsigned(r)]

function write_RB(r : bits(6), v : bits(64)) -> unit =
  if r == 0b000000 then () else RB[unsigned(r)] = sail_zero_extend(v[47 .. 0], 64)

/* ---- RA accessors (spec §1.5) -------------------------------------------- */
function read_RA(r : bits(6))  -> bits(64) = RA[unsigned(r)]
function write_RA(r : bits(6), v : bits(64)) -> unit = RA[unsigned(r)] = v

/* int (0..63) -> bits(6) register index (for RegRAS shift loops, spec §5.6) */
function to_reg(i : int) -> bits(6) = get_slice_int(6, i, 0)

/* ---- big-endian data memory (spec §2.1) ---------------------------------- */
/* 64-bit load/store, MSB at the lowest address. */
function read_octa_be(ea : bits(48)) -> bits(64) =
  read_ram_byte(ea)     @ read_ram_byte(ea + 1) @
  read_ram_byte(ea + 2) @ read_ram_byte(ea + 3) @
  read_ram_byte(ea + 4) @ read_ram_byte(ea + 5) @
  read_ram_byte(ea + 6) @ read_ram_byte(ea + 7)

function write_octa_be(ea : bits(48), v : bits(64)) -> unit = {
  write_ram_byte(ea,     v[63 .. 56]);
  write_ram_byte(ea + 1, v[55 .. 48]);
  write_ram_byte(ea + 2, v[47 .. 40]);
  write_ram_byte(ea + 3, v[39 .. 32]);
  write_ram_byte(ea + 4, v[31 .. 24]);
  write_ram_byte(ea + 5, v[23 .. 16]);
  write_ram_byte(ea + 6, v[15 .. 8]);
  write_ram_byte(ea + 7, v[7 .. 0])
}

/* instruction fetch: 4 bytes big-endian, bits[31:24] at the lowest address
 * (spec §2.1). */
function fetch(pc : bits(48)) -> bits(32) =
  read_ram_byte(pc)     @ read_ram_byte(pc + 1) @
  read_ram_byte(pc + 2) @ read_ram_byte(pc + 3)
