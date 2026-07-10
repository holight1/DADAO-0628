/* DADAO Sail model — register accessors + big-endian memory + conditions.
 * Semantics: spec §1.2 (rd0=0), §1.3/§4 (rb0=PC+4, RB write-back by class),
 * §2.1 (big-endian), Appendix B (condition flags). */

/* Memory lives in the C harness; Sail assembles multi-byte accesses big-endian
 * (spec §2.1). Only these two byte primitives cross the Sail/C boundary. */
val read_ram_byte  = impure "read_ram_byte"  : bits(48) -> bits(8)
val write_ram_byte = impure "write_ram_byte" : (bits(48), bits(8)) -> unit

/* Run-result reporting to the C harness (kind: 0=halt, 1=fault, 2=unimpl).
 * Terminal register state is read directly from the exported zRD/zRB globals. */
val set_result = impure "set_result" : (bits(8), bits(8)) -> unit

/* ---- RD accessors (spec §1.2) -------------------------------------------- */
/* rd0 hardwired zero: reads 0, writes discarded. rd0-as-destination legality is
 * enforced per-instruction (spec §2.6.1). */
function read_RD(r : bits(6)) -> bits(64) =
  if r == 0b000000 then 0x0000000000000000 else RD[unsigned(r)]

function write_RD(r : bits(6), v : bits(64)) -> unit =
  if r == 0b000000 then () else RD[unsigned(r)] = v

/* ---- RB accessors (spec §1.3, §4 write-back-by-class) -------------------- */
/* rb0 = current_PC + 4; during execute nextPC already holds PC+4, so rb0 reads
 * back nextPC (before any branch retargets it). rb0[63:48] = 0. */
function read_RB(r : bits(6)) -> bits(64) =
  if r == 0b000000 then sail_zero_extend(nextPC, 64) else RB[unsigned(r)]

/* Full 64-bit overwrite: memory->RB loads, reg-copy->RB, wyde-immediate RB
 * (spec §4 table: "Full 64-bit overwrite"; §4.6 "w3 legal"). */
function write_RB_full(r : bits(6), v : bits(64)) -> unit =
  if r == 0b000000 then () else RB[unsigned(r)] = v

/* Low-48 write, bits[63:48] preserved: RB arithmetic add/sub/addi/rela, control
 * flow (spec §4 table: "Low 48 only; bits[63:48] preserved"). */
function write_RB_lo48(r : bits(6), v : bits(64)) -> unit =
  if r == 0b000000 then () else RB[unsigned(r)] = RB[unsigned(r)][63 .. 48] @ v[47 .. 0]

/* ---- RA accessors (spec §1.5) -------------------------------------------- */
function read_RA(r : bits(6))  -> bits(64) = RA[unsigned(r)]
function write_RA(r : bits(6), v : bits(64)) -> unit = RA[unsigned(r)] = v

/* int (0..63) -> bits(6) register index (RegRAS shift loops, spec §5.6) */
function to_reg(i : int) -> bits(6) = get_slice_int(6, i, 0)

/* ---- big-endian data memory (spec §2.1) ---------------------------------- */
/* Load n (1/2/4/8) bytes big-endian into the low n*8 bits, high bits zero. */
function load_be(ea : bits(48), n : int) -> bits(64) = {
  var acc : bits(64) = 0x0000000000000000;
  foreach (i from 0 to (n - 1)) {
    acc = sail_shiftleft(acc, 8) | sail_zero_extend(read_ram_byte(ea + i), 64)
  };
  acc
}

/* Store the low n bytes of v big-endian (MSB of the n-byte field first). */
function store_be(ea : bits(48), n : int, v : bits(64)) -> unit = {
  foreach (i from 0 to (n - 1)) {
    let sh = (n - 1 - i) * 8;
    write_ram_byte(ea + i, sail_shiftright(v, sh)[7 .. 0])
  }
}

/* Misalignment test for a width-w access (spec §3.1 alignment table). */
function misaligned(ea : bits(48), w : int) -> bool =
  match w {
    1 => false,
    2 => ea[0 .. 0] != 0b0,
    4 => ea[1 .. 0] != 0b00,
    8 => ea[2 .. 0] != 0b000,
    _ => false
  }

/* instruction fetch: 4 bytes big-endian, bits[31:24] at the lowest address. */
function fetch(pc : bits(48)) -> bits(32) =
  read_ram_byte(pc)     @ read_ram_byte(pc + 1) @
  read_ram_byte(pc + 2) @ read_ram_byte(pc + 3)

/* ---- condition flags (Appendix B) ---------------------------------------- */
function condN(x : bits(64))  -> bool = x[63 .. 63] == 0b1              /* bit63=1     */
function condNN(x : bits(64)) -> bool = x[63 .. 63] == 0b0              /* bit63=0     */
function condZ(x : bits(64))  -> bool = x == 0x0000000000000000         /* all zero    */
function condNZ(x : bits(64)) -> bool = x != 0x0000000000000000         /* any nonzero */
function condP(x : bits(64))  -> bool = condNN(x) & condNZ(x)           /* bit63=0 & !=0 */
function condNP(x : bits(64)) -> bool = condN(x) | condZ(x)             /* bit63=1 | ==0 */

/* three-way compare -> -1/0/1 as bits(64) (spec §3.8/§3.9 semantics). */
function cmp3_signed(a : bits(64), b : bits(64)) -> bits(64) =
  if signed(a) < signed(b) then 0xFFFFFFFFFFFFFFFF
  else if a == b then 0x0000000000000000
  else 0x0000000000000001

function cmp3_unsigned(a : bits(64), b : bits(64)) -> bits(64) =
  if unsigned(a) < unsigned(b) then 0xFFFFFFFFFFFFFFFF
  else if a == b then 0x0000000000000000
  else 0x0000000000000001
