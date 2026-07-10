/* DADAO Sail rehearsal slice — decode + execute (spec §2–§5).
 *
 * Modelled instructions (ADR-0011 slice) + the harness scaffolding opcodes
 * (setzw/orw/halt) needed to set up and terminate a flat test binary. Every
 * clause is annotated with its spec §. Valid DADAO opcodes outside this slice
 * decode to UNMODELED (harness SKIP); truly reserved encodings decode to
 * RESERVED → UNDI (spec §2.5).
 */

/* ---- instruction AST ----------------------------------------------------- */
union instruction = {
  /* harness scaffolding (setzw/orw load inputs; halt=op0x00 terminates) */
  SETZW_RD : (bits(6), bits(2), bits(16)),   /* rdha, ww, imm16   (spec §3.13) */
  ORW_RD   : (bits(6), bits(2), bits(16)),   /* rdha, ww, imm16   (spec §3.13) */
  SETZW_RB : (bits(6), bits(2), bits(16)),   /* rbha, ww, imm16   (spec §4.6)  */
  ORW_RB   : (bits(6), bits(2), bits(16)),   /* rbha, ww, imm16   (spec §4.6)  */
  HALT     : bits(6),                        /* halt rdha (harness/SEE)        */
  /* rehearsal slice */
  ADD      : (bits(6), bits(6), bits(6), bits(6)),  /* rdha,rdhb,rdhc,rdhd §3.5 */
  ADDI     : (bits(6), bits(6), bits(12)),          /* rdha,rdhb,imms12    §3.6 */
  LDO      : (bits(6), bits(6), bits(12)),          /* rdha,rbhb,imms12    §3.1 */
  STO      : (bits(6), bits(6), bits(12)),          /* rdha,rbhb,imms12    §3.2 */
  BRZ      : (bits(6), bits(18)),                   /* rdha,imms18         §5.1 */
  CALL_I   : bits(24),                              /* imms24              §5.4 */
  RET      : (bits(6), bits(18)),                   /* rdha,imms18         §5.5 */
  SWYM     : unit,                                  /* nop                 §6.1 */
  UNIMP    : unit,                                  /* -> ILLI             §6.2 */
  /* fall-through buckets */
  UNMODELED : unit,     /* valid opcode, not in this rehearsal slice */
  RESERVED  : unit      /* reserved encoding -> UNDI (spec §2.5)     */
}

/* place a 16-bit immediate into wyde position ww, other wydes = 0 (spec §3.13).
 * ww: 0->[15:0] 1->[31:16] 2->[47:32] 3->[63:48]. */
function place_wyde(ww : bits(2), imm16 : bits(16)) -> bits(64) =
  match ww {
    0b00 => sail_zero_extend(imm16, 64),
    0b01 => sail_zero_extend(imm16 @ 0x0000, 64),
    0b10 => sail_zero_extend(imm16 @ 0x00000000, 64),
    0b11 => imm16 @ 0x000000000000
  }

/* Is op[7:0] a valid M1 opcode (spec §2.8 map)? Used to distinguish
 * "valid-but-unmodeled" (harness SKIP) from "reserved" (UNDI, spec §2.5). */
/* Row-granularity approximation of the M1 opcode map (spec §2.8): the populated
 * rows are 0x10-0x2F (misc/wyde/arith/cs/branch), 0x30-0x4F (RD/RB load/store +
 * RB row), 0x64-0x6E (jump/call/ret); 0x00 is the harness halt. Blank cells
 * inside a populated row are, per spec §2.5, reserved->UNDI; treating them as
 * "known" here only affects the UNMODELED-vs-RESERVED split for the rehearsal
 * (no vector exercises a reserved encoding). Encodings in fully-empty rows
 * (e.g. op=0x08) are correctly RESERVED->UNDI. */
function op_known(op : bits(8)) -> bool = {
  let n = unsigned(op);
  (n == 0)
  | (n >= 16  & n <= 47)     /* 0x10..0x2F */
  | (n >= 48  & n <= 79)     /* 0x30..0x4F */
  | (n >= 100 & n <= 110)    /* 0x64..0x6E */
}

/* ---- decode (spec §2.2 field layout) ------------------------------------- */
function decode(insn : bits(32)) -> instruction = {
  let op = insn[31 .. 24];
  let ha = insn[23 .. 18];
  let hb = insn[17 .. 12];
  let hc = insn[11 .. 6];
  let hd = insn[5 .. 0];
  let ww     : bits(2)  = insn[17 .. 16];
  let imm16  : bits(16) = insn[15 .. 12] @ hc @ hd;   /* rwii §2.3 */
  let imms12 : bits(12) = hc @ hd;
  let imms18 : bits(18) = hb @ hc @ hd;
  let imms24 : bits(24) = ha @ hb @ hc @ hd;
  match op {
    0x00 => HALT(ha),
    0x16 => SETZW_RD(ha, ww, imm16),
    0x14 => ORW_RD(ha, ww, imm16),
    0x4E => SETZW_RB(ha, ww, imm16),
    0x4C => ORW_RB(ha, ww, imm16),
    0x19 => ADDI(ha, hb, imms12),
    0x1A => ADD(ha, hb, hc, hd),
    0x33 => LDO(ha, hb, imms12),
    0x3B => STO(ha, hb, imms12),
    0x2A => BRZ(ha, imms18),
    0x6C => CALL_I(imms24),
    0x6E => RET(ha, imms18),
    0x10 => match ha {                     /* MISC-Norm subtable (spec §2.8.1) */
              0b000000 => SWYM(),
              0b111111 => UNIMP(),
              _        => UNMODELED()         /* other misc ops: not in slice */
            },
    _    => if op_known(op) then UNMODELED() else RESERVED()
  }
}

/* ---- RegRAS (spec §5.6) -------------------------------------------------- */
/* ra63 = stack top; [63:48]=refcount (0=invalid), [47:0]=return address. */
function ras_push(new_ra : bits(48)) -> unit = {
  let top = read_RA(0b111111);          /* ra63 */
  let rc  = top[63 .. 48];
  if rc == 0x0000 then {
    write_RA(0b111111, 0x0001 @ new_ra)                        /* first push  */
  } else if (unsigned(rc) >= 1 & unsigned(rc) <= 65534)
            & top[47 .. 0] == new_ra then {
    write_RA(0b111111, (rc + 1) @ new_ra)                      /* recursion   */
  } else {
    if read_RA(0b000001)[63 .. 48] != 0x0000
    then throw(Fault(F_RASOF));           /* stack full -> RASOF (precise) */
    foreach (i from 2 to 63) {
      write_RA(to_reg(i - 1), read_RA(to_reg(i)))              /* shift down  */
    };
    write_RA(0b111111, 0x0001 @ new_ra)
  }
}

function ras_pop() -> bits(48) = {
  let top = read_RA(0b111111);
  let rc  = top[63 .. 48];
  if unsigned(rc) > 1 then {
    write_RA(0b111111, sub_bits(rc, 0x0001) @ top[47 .. 0]);  /* recursion   */
    top[47 .. 0]
  } else if rc == 0x0001 then {
    let ret = top[47 .. 0];
    foreach (i from 62 downto 1) {
      write_RA(to_reg(i + 1), read_RA(to_reg(i)))              /* shift up    */
    };
    write_RA(0b000001, 0x0000000000000000);
    ret
  } else {
    throw(Fault(F_RASUF))                 /* empty stack -> RASUF (precise) */
  }
}

/* ---- effective address for RB-based load/store (spec §3.1/§3.2) ---------- */
/* ea[47:0] = (rbhb[47:0] + sext_12(imms12)) mod 2^48 */
function rb_ea(rbhb : bits(6), imms12 : bits(12)) -> bits(48) =
  read_RB(rbhb)[47 .. 0] + sail_sign_extend(imms12, 48)

/* ---- execute (spec §3–§6) ------------------------------------------------ */
function execute(instr : instruction) -> Ctl = {
  match instr {
    /* -- harness: setzw/orw load a register, wyde by wyde (spec §3.13/§4.6) - */
    SETZW_RD(r, ww, imm16) => {
      if r == 0b000000 then throw(Fault(F_ILLI));   /* rdha=rd0 -> ILLI §2.6.1 */
      write_RD(r, place_wyde(ww, imm16));
      Ctl_Continue()
    },
    ORW_RD(r, ww, imm16) => {
      if r == 0b000000 then throw(Fault(F_ILLI));
      write_RD(r, read_RD(r) | place_wyde(ww, imm16));
      Ctl_Continue()
    },
    SETZW_RB(r, ww, imm16) => {
      if r == 0b000000 then throw(Fault(F_ILLI));   /* rbha=rb0 -> ILLI §2.6.2 */
      write_RB(r, place_wyde(ww, imm16));
      Ctl_Continue()
    },
    ORW_RB(r, ww, imm16) => {
      if r == 0b000000 then throw(Fault(F_ILLI));
      write_RB(r, read_RB(r) | place_wyde(ww, imm16));
      Ctl_Continue()
    },

    /* -- add: 128-bit intermediate, dual destination (spec §3.5) ----------- */
    ADD(ha, hb, hc, hd) => {
      /* legality §2.6.1: not both dst rd0; dst not the same non-rd0 reg */
      if (ha == 0b000000 & hb == 0b000000) then throw(Fault(F_ILLI));
      if (ha == hb & ha != 0b000000)       then throw(Fault(F_ILLI));
      let a = read_RD(hc);                     /* source snapshot §2.7 */
      let b = read_RD(hd);
      let wide : bits(128) = sail_sign_extend(a, 128) + sail_sign_extend(b, 128);
      write_RD(ha, wide[127 .. 64]);           /* high half */
      write_RD(hb, wide[63 .. 0]);             /* low half  */
      Ctl_Continue()
    },

    /* -- addi: 64-bit add, single dest, rd0 dest illegal (spec §3.6) ------- */
    ADDI(ha, hb, imms12) => {
      if ha == 0b000000 then throw(Fault(F_ILLI));
      write_RD(ha, read_RD(hb) + sail_sign_extend(imms12, 64));
      Ctl_Continue()
    },

    /* -- ldo: 48-bit EA, big-endian octa load, MALIGN (spec §3.1/§2.1) ----- */
    LDO(ha, hb, imms12) => {
      if ha == 0b000000 then throw(Fault(F_ILLI));       /* §3.1 rdha!=rd0 */
      let ea = rb_ea(hb, imms12);
      if ea[2 .. 0] != 0b000 then throw(Fault(F_MALIGN)); /* 8-byte align §3.1 */
      write_RD(ha, read_octa_be(ea));
      Ctl_Continue()
    },

    /* -- sto: big-endian octa store, store-from-rd0 illegal (spec §3.2) ---- */
    STO(ha, hb, imms12) => {
      if ha == 0b000000 then throw(Fault(F_ILLI));       /* §3.2 rdha!=rd0 */
      let ea = rb_ea(hb, imms12);
      if ea[2 .. 0] != 0b000 then throw(Fault(F_MALIGN));
      write_octa_be(ea, read_RD(ha));
      Ctl_Continue()
    },

    /* -- brz: PC-relative conditional branch (spec §5.1) ------------------- */
    BRZ(ha, imms18) => {
      /* rdha is a condition source; rdha=rd0 reads 0 -> always taken §2.6.1 */
      if read_RD(ha) == 0x0000000000000000 then {
        let base = read_RB(0b000000)[47 .. 0];            /* rb0 = PC+4 */
        nextPC = base + sail_shiftleft(sail_sign_extend(imms18, 48), 2);
      };
      Ctl_Continue()
    },

    /* -- call (relative): push rb0 to RegRAS, PC-relative (spec §5.4/§5.6) - */
    CALL_I(imms24) => {
      let base = read_RB(0b000000)[47 .. 0];              /* rb0 = PC+4 */
      ras_push(base);                                     /* may throw RASOF */
      nextPC = base + sail_shiftleft(sail_sign_extend(imms24, 48), 2);
      Ctl_Continue()
    },

    /* -- ret: pop RegRAS, jump, return value in rdha (spec §5.5/§5.6) ------ */
    RET(ha, imms18) => {
      let target = ras_pop();                             /* may throw RASUF */
      nextPC = target;
      write_RD(ha, sail_sign_extend(imms18, 64));              /* rdha=rd0 discards */
      Ctl_Continue()
    },

    SWYM()   => Ctl_Continue(),                           /* nop §6.1 */
    UNIMP()  => throw(Fault(F_ILLI)),                     /* §6.2 */
    HALT(ha) => Ctl_Halt(read_RD(ha)[7 .. 0]),            /* harness exit code */

    UNMODELED() => Ctl_Unimpl(),
    RESERVED()  => throw(Fault(F_UNDI))                   /* §2.5 */
  }
}
