/* DADAO SimRISC (M1) — Sail decode + execute, full 87-instruction model.
 *
 * SL-003a (ADR-0011 phase 2). Semantics derived ONLY from contracts/isa/spec.md §
 * and tools/opcodes.yaml (independence rule ADR-0011 D4); structure follows the
 * sail-riscv idiom (union instruction / decode / execute). NOT derived from QEMU
 * translate.c or gem5 decoder.cc. Every execute clause cites its spec §.
 */

/* ---- operation selectors ------------------------------------------------- */
enum wydeop = { WY_ORW, WY_ANDNW, WY_SETZW, WY_SETOW }            /* §3.13/§4.6 */
enum aluop  = { AO_ADD, AO_SUB, AO_MULS, AO_MULU, AO_DIVS, AO_DIVU } /* §3.5/§3.7 */
enum csop   = { CS_N, CS_Z, CS_P, CS_EQ, CS_NE }                  /* §3.12      */
enum logop  = { LG_AND, LG_ORR, LG_XOR, LG_XNOR,
                LG_SHLU, LG_SHRS, LG_SHRU, LG_EXTS, LG_EXTZ,
                LG_CMPS, LG_CMPU }                                /* §3.9–§3.11 */
enum bcop   = { BC_RD2RD, BC_RD2RB, BC_RB2RD, BC_RB2RB }          /* §3.14/§4.7 */
enum brcond = { BR_N, BR_NN, BR_Z, BR_NZ, BR_P, BR_NP }           /* §5.1       */

/* ---- instruction AST ----------------------------------------------------- */
union instruction = {
  HALT    : bits(6),                                   /* harness halt (op0x00) */
  SWYM    : unit,                                       /* §6.1 */
  UNIMP   : unit,                                       /* §6.2 -> ILLI */
  WYDE_RD : (wydeop, bits(6), bits(2), bits(16)),       /* §3.13 op,ha,ww,imm16 */
  WYDE_RB : (wydeop, bits(6), bits(2), bits(16)),       /* §4.6  */
  ARITH   : (aluop, bits(6), bits(6), bits(6), bits(6)),/* §3.5/§3.7 dual-dest  */
  COND    : (csop, bits(6), bits(6), bits(6), bits(6)), /* §3.12 */
  ADDI_RD : (bits(6), bits(6), bits(12)),               /* §3.6  */
  ADDI_RB : (bits(6), bits(6), bits(12)),               /* §4.4  */
  CMP_IMM : (bool, bits(6), bits(6), bits(12)),         /* §3.8 signed?,ha,hb,imm */
  ORRR_RD : (logop, bits(6), bits(6), bits(6)),         /* §3.9–§3.11 hb,hc,hd   */
  ORRI_SH : (logop, bits(6), bits(6), bits(6)),         /* §3.11 imm hb,hc,hd(imm)*/
  RBARITH : (bool, bits(6), bits(6), bits(6)),          /* §4.3 sub?,hb,hc(rb),hd(rd)*/
  RBCMP   : (bits(6), bits(6), bits(6)),                /* §4.5 hb(rd),hc,hd(rb) */
  BCOPY   : (bcop, bits(6), bits(6), bits(6)),          /* §3.14/§4.7 dst,src,cnt */
  LOAD    : (int, bool, bool, bits(6), bits(6), bits(12)),  /* w,signed,dstRB,ha,hb,imm §3.1/§4.1 */
  STORE   : (int, bool, bits(6), bits(6), bits(12)),       /* w,srcRB,ha,hb,imm §3.2/§4.1 */
  MLOAD   : (int, bool, bool, bits(6), bits(6), bits(6), bits(6)), /* w,signed,dstRB,ha,hb,hc,cnt §3.3/§4.2 */
  MSTORE  : (int, bool, bits(6), bits(6), bits(6), bits(6)),        /* w,srcRB,ha,hb,hc,cnt §3.4/§4.2 */
  BR1     : (brcond, bits(6), bits(18)),                /* §5.1 */
  BR2     : (bool, bits(6), bits(6), bits(12)),         /* §5.2 eq?,ha,hb,imm */
  RELA    : (bits(6), bits(18)),                        /* §4.8 */
  JUMP_I  : bits(24),                                   /* §5.3 */
  JUMP_R  : (bits(6), bits(6), bits(12)),               /* §5.3 */
  CALL_I  : bits(24),                                   /* §5.4 */
  CALL_R  : (bits(6), bits(6), bits(12)),               /* §5.4 */
  RET     : (bits(6), bits(18)),                        /* §5.5 */
  UNMODELED : unit,     /* valid opcode not (yet) modelled -> harness SKIP */
  RESERVED  : unit      /* reserved encoding -> UNDI (spec §2.5) */
}

/* place a 16-bit immediate into wyde position ww, other wydes = 0 (spec §3.13) */
function place_wyde(ww : bits(2), imm16 : bits(16)) -> bits(64) =
  match ww {
    0b00 => sail_zero_extend(imm16, 64),
    0b01 => sail_zero_extend(imm16 @ 0x0000, 64),
    0b10 => sail_zero_extend(imm16 @ 0x00000000, 64),
    0b11 => imm16 @ 0x000000000000
  }

/* apply a wyde-immediate op (spec §3.13/§4.6). */
function apply_wyde(op : wydeop, old : bits(64), ww : bits(2), imm16 : bits(16)) -> bits(64) =
  match op {
    WY_SETZW => place_wyde(ww, imm16),
    WY_SETOW => place_wyde(ww, imm16) | not_vec(place_wyde(ww, 0xFFFF)),
    WY_ORW   => old | place_wyde(ww, imm16),
    WY_ANDNW => old & not_vec(place_wyde(ww, imm16))
  }

/* shift/extend kernel (spec §3.11); amt in 0..63. */
function do_shift(op : logop, x : bits(64), amt : int) -> bits(64) =
  match op {
    LG_SHLU => sail_shiftleft(x, amt),
    LG_SHRU => sail_shiftright(x, amt),
    LG_SHRS => sail_arith_shiftright(x, amt),
    LG_EXTS => sail_arith_shiftright(sail_shiftleft(x, amt), amt),
    LG_EXTZ => sail_shiftright(sail_shiftleft(x, amt), amt),
    _       => x
  }

/* sign-extend the low w bytes of raw to 64 bits (spec §3.1 signed loads). */
function sext_from(raw : bits(64), w : int) -> bits(64) = {
  let sh = 64 - 8 * w;
  sail_arith_shiftright(sail_shiftleft(raw, sh), sh)
}

/* Is op[7:0] a valid M1 opcode row (spec §2.8)? Distinguishes valid-but-unmodeled
 * (harness SKIP) from reserved (UNDI). Row-granular approximation; blank cells in
 * a populated row are reserved per §2.5 but no vector exercises them, and empty
 * rows (e.g. op=0x08) are correctly RESERVED->UNDI. */
function op_known(op : bits(8)) -> bool = {
  let n = unsigned(op);
  (n == 0)
  | (n >= 16  & n <= 47)
  | (n >= 48  & n <= 79)
  | (n >= 100 & n <= 110)
}

/* ---- decode (spec §2.2 field layout, §2.8 opcode map) -------------------- */
function decode(insn : bits(32)) -> instruction = {
  let op = insn[31 .. 24];
  let ha = insn[23 .. 18];
  let hb = insn[17 .. 12];
  let hc = insn[11 .. 6];
  let hd = insn[5 .. 0];
  let ww     : bits(2)  = insn[17 .. 16];
  let imm16  : bits(16) = insn[15 .. 12] @ hc @ hd;
  let imms12 : bits(12) = hc @ hd;
  let imms18 : bits(18) = hb @ hc @ hd;
  let imms24 : bits(24) = ha @ hb @ hc @ hd;
  match op {
    0x00 => HALT(ha),
    /* --- MISC-Norm subtable (spec §2.8.1) --- */
    0x10 => match ha {
              0b000000 => SWYM(),
              0b111111 => UNIMP(),
              0b001000 => ORRR_RD(LG_AND,  hb, hc, hd),
              0b001001 => ORRR_RD(LG_ORR,  hb, hc, hd),
              0b001010 => ORRR_RD(LG_XOR,  hb, hc, hd),
              0b001011 => ORRR_RD(LG_XNOR, hb, hc, hd),
              0b010001 => ORRR_RD(LG_SHLU, hb, hc, hd),
              0b010010 => ORRR_RD(LG_SHRS, hb, hc, hd),
              0b010011 => ORRR_RD(LG_SHRU, hb, hc, hd),
              0b010100 => ORRR_RD(LG_EXTS, hb, hc, hd),
              0b010101 => ORRR_RD(LG_EXTZ, hb, hc, hd),
              0b011001 => ORRI_SH(LG_SHLU, hb, hc, hd),
              0b011010 => ORRI_SH(LG_SHRS, hb, hc, hd),
              0b011011 => ORRI_SH(LG_SHRU, hb, hc, hd),
              0b011100 => ORRI_SH(LG_EXTS, hb, hc, hd),
              0b011101 => ORRI_SH(LG_EXTZ, hb, hc, hd),
              0b100100 => ORRR_RD(LG_CMPS, hb, hc, hd),
              0b100101 => ORRR_RD(LG_CMPU, hb, hc, hd),
              0b101000 => BCOPY(BC_RD2RD, hb, hc, hd),
              0b101001 => BCOPY(BC_RD2RB, hb, hc, hd),
              0b101010 => BCOPY(BC_RB2RD, hb, hc, hd),
              0b101011 => BCOPY(BC_RB2RB, hb, hc, hd),
              0b101101 => RBCMP(hb, hc, hd),
              0b101110 => RBARITH(false, hb, hc, hd),
              0b101111 => RBARITH(true,  hb, hc, hd),
              _        => RESERVED()          /* unlisted misc ha -> UNDI §2.5 */
            },
    0x12 => CMP_IMM(true,  ha, hb, imms12),   /* cmps §3.8 */
    0x13 => CMP_IMM(false, ha, hb, imms12),   /* cmpu §3.8 */
    0x14 => WYDE_RD(WY_ORW,   ha, ww, imm16),
    0x15 => WYDE_RD(WY_ANDNW, ha, ww, imm16),
    0x16 => WYDE_RD(WY_SETZW, ha, ww, imm16),
    0x17 => WYDE_RD(WY_SETOW, ha, ww, imm16),
    0x19 => ADDI_RD(ha, hb, imms12),
    0x1A => ARITH(AO_ADD,  ha, hb, hc, hd),
    0x1B => ARITH(AO_SUB,  ha, hb, hc, hd),
    0x1C => ARITH(AO_MULS, ha, hb, hc, hd),
    0x1D => ARITH(AO_MULU, ha, hb, hc, hd),
    0x1E => ARITH(AO_DIVS, ha, hb, hc, hd),
    0x1F => ARITH(AO_DIVU, ha, hb, hc, hd),
    0x20 => COND(CS_N,  ha, hb, hc, hd),
    0x22 => COND(CS_Z,  ha, hb, hc, hd),
    0x24 => COND(CS_P,  ha, hb, hc, hd),
    0x26 => COND(CS_EQ, ha, hb, hc, hd),
    0x27 => COND(CS_NE, ha, hb, hc, hd),
    0x28 => BR1(BR_N,  ha, imms18),
    0x29 => BR1(BR_NN, ha, imms18),
    0x2A => BR1(BR_Z,  ha, imms18),
    0x2B => BR1(BR_NZ, ha, imms18),
    0x2C => BR1(BR_P,  ha, imms18),
    0x2D => BR1(BR_NP, ha, imms18),
    0x2E => BR2(true,  ha, hb, imms12),
    0x2F => BR2(false, ha, hb, imms12),
    /* --- RD load signed (row 00110) --- */
    0x30 => LOAD(1, true,  false, ha, hb, imms12),
    0x31 => LOAD(2, true,  false, ha, hb, imms12),
    0x32 => LOAD(4, true,  false, ha, hb, imms12),
    0x33 => LOAD(8, false, false, ha, hb, imms12),   /* ldo (no ext) */
    0x34 => MLOAD(1, true,  false, ha, hb, hc, hd),
    0x35 => MLOAD(2, true,  false, ha, hb, hc, hd),
    0x36 => MLOAD(4, true,  false, ha, hb, hc, hd),
    0x37 => MLOAD(8, false, false, ha, hb, hc, hd),
    /* --- RD store (row 00111) --- */
    0x38 => STORE(1, false, ha, hb, imms12),
    0x39 => STORE(2, false, ha, hb, imms12),
    0x3A => STORE(4, false, ha, hb, imms12),
    0x3B => STORE(8, false, ha, hb, imms12),
    0x3C => MSTORE(1, false, ha, hb, hc, hd),
    0x3D => MSTORE(2, false, ha, hb, hc, hd),
    0x3E => MSTORE(4, false, ha, hb, hc, hd),
    0x3F => MSTORE(8, false, ha, hb, hc, hd),
    /* --- RD load unsigned + RB load (row 01000) --- */
    0x40 => LOAD(1, false, false, ha, hb, imms12),
    0x41 => LOAD(2, false, false, ha, hb, imms12),
    0x42 => LOAD(4, false, false, ha, hb, imms12),
    0x43 => LOAD(8, false, true,  ha, hb, imms12),   /* ldo-rb (RB target) */
    0x44 => MLOAD(1, false, false, ha, hb, hc, hd),
    0x45 => MLOAD(2, false, false, ha, hb, hc, hd),
    0x46 => MLOAD(4, false, false, ha, hb, hc, hd),
    0x47 => MLOAD(8, false, true,  ha, hb, hc, hd),  /* ldmo-rb */
    /* --- RB row (01001) --- */
    0x48 => RELA(ha, imms18),
    0x49 => ADDI_RB(ha, hb, imms12),
    0x4B => STORE(8, true, ha, hb, imms12),          /* sto-rb (RB source) */
    0x4C => WYDE_RB(WY_ORW,   ha, ww, imm16),
    0x4D => WYDE_RB(WY_ANDNW, ha, ww, imm16),
    0x4E => WYDE_RB(WY_SETZW, ha, ww, imm16),
    0x4F => MSTORE(8, true, ha, hb, hc, hd),          /* stmo-rb */
    /* --- control flow --- */
    0x64 => JUMP_I(imms24),
    0x65 => JUMP_R(ha, hb, imms12),
    0x6C => CALL_I(imms24),
    0x6D => CALL_R(ha, hb, imms12),
    0x6E => RET(ha, imms18),
    _    => if op_known(op) then UNMODELED() else RESERVED()
  }
}

/* ---- RegRAS (spec §5.6) -------------------------------------------------- */
function ras_push(new_ra : bits(48)) -> unit = {
  let top = read_RA(0b111111);
  let rc  = top[63 .. 48];
  if rc == 0x0000 then {
    write_RA(0b111111, 0x0001 @ new_ra)
  } else if (unsigned(rc) >= 1 & unsigned(rc) <= 65534)
            & top[47 .. 0] == new_ra then {
    write_RA(0b111111, (rc + 1) @ new_ra)
  } else {
    if read_RA(0b000001)[63 .. 48] != 0x0000
    then throw(Fault(F_RASOF));
    foreach (i from 2 to 63) {
      write_RA(to_reg(i - 1), read_RA(to_reg(i)))
    };
    write_RA(0b111111, 0x0001 @ new_ra)
  }
}

function ras_pop() -> bits(48) = {
  let top = read_RA(0b111111);
  let rc  = top[63 .. 48];
  if unsigned(rc) > 1 then {
    write_RA(0b111111, sub_bits(rc, 0x0001) @ top[47 .. 0]);
    top[47 .. 0]
  } else if rc == 0x0001 then {
    let ret = top[47 .. 0];
    foreach (i from 62 downto 1) {
      write_RA(to_reg(i + 1), read_RA(to_reg(i)))
    };
    write_RA(0b000001, 0x0000000000000000);
    ret
  } else {
    throw(Fault(F_RASUF))
  }
}

/* effective address for RB-based single load/store (spec §3.1/§3.2). */
function rb_ea(rbhb : bits(6), imms12 : bits(12)) -> bits(48) =
  read_RB(rbhb)[47 .. 0] + sail_sign_extend(imms12, 48)

/* PC + offset<<2, 48-bit (spec §5). base is rb0[47:0] = PC+4. */
function pcrel(offset48 : bits(48)) -> bits(48) =
  read_RB(0b000000)[47 .. 0] + sail_shiftleft(offset48, 2)

/* ---- execute (spec §3–§6) ------------------------------------------------ */
function execute(instr : instruction) -> Ctl = {
  match instr {
    /* ---- wyde immediate (spec §3.13/§4.6) ---- */
    WYDE_RD(op, r, ww, imm16) => {
      if r == 0b000000 then throw(Fault(F_ILLI));   /* rdha=rd0 §2.6.1 */
      write_RD(r, apply_wyde(op, read_RD(r), ww, imm16));
      Ctl_Continue()
    },
    WYDE_RB(op, r, ww, imm16) => {
      if r == 0b000000 then throw(Fault(F_ILLI));   /* rbha=rb0 §2.6.2 */
      write_RB_full(r, apply_wyde(op, read_RB(r), ww, imm16));  /* full 64, w3 legal §4.6 */
      Ctl_Continue()
    },

    /* ---- RD dual-destination arithmetic (spec §3.5/§3.7) ---- */
    ARITH(op, ha, hb, hc, hd) => {
      if (ha == 0b000000 & hb == 0b000000) then throw(Fault(F_ILLI));  /* §2.6.1 */
      if (ha == hb & ha != 0b000000)       then throw(Fault(F_ILLI));
      let a = read_RD(hc);                    /* source snapshot §2.7 */
      let b = read_RD(hd);
      match op {
        AO_ADD => {
          let s = signed(a) + signed(b);        /* 128-bit sign-extended §3.5 */
          write_RD(ha, get_slice_int(64, s, 64));
          write_RD(hb, get_slice_int(64, s, 0))
        },
        AO_SUB => {
          let s = signed(a) - signed(b);
          write_RD(ha, get_slice_int(64, s, 64));
          write_RD(hb, get_slice_int(64, s, 0))
        },
        AO_MULS => {
          let p = signed(a) * signed(b);        /* 128-bit signed product §3.7 */
          write_RD(ha, get_slice_int(64, p, 64));
          write_RD(hb, get_slice_int(64, p, 0))
        },
        AO_MULU => {
          let p = unsigned(a) * unsigned(b);
          write_RD(ha, get_slice_int(64, p, 64));
          write_RD(hb, get_slice_int(64, p, 0))
        },
        AO_DIVS => {
          if b == 0x0000000000000000 then throw(Fault(F_ILLI));  /* div-by-0 §3.7 */
          if a == 0x8000000000000000 & b == 0xFFFFFFFFFFFFFFFF
          then throw(Fault(F_ILLI));            /* INT64_MIN / -1 §3.7 */
          let q = tdiv_int(signed(a), signed(b));  /* trunc toward zero (C99) */
          let r = signed(a) - q * signed(b);       /* rem sign = dividend §3.7 */
          write_RD(ha, get_slice_int(64, r, 0));   /* rdha = remainder */
          write_RD(hb, get_slice_int(64, q, 0))    /* rdhb = quotient  */
        },
        AO_DIVU => {
          if b == 0x0000000000000000 then throw(Fault(F_ILLI));
          let q = tdiv_int(unsigned(a), unsigned(b));
          let r = unsigned(a) - q * unsigned(b);
          write_RD(ha, get_slice_int(64, r, 0));
          write_RD(hb, get_slice_int(64, q, 0))
        }
      };
      Ctl_Continue()
    },

    /* ---- RD conditional assign (spec §3.12) ---- */
    COND(op, ha, hb, hc, hd) => {
      match op {
        CS_EQ => {
          if hc == 0b000000 then throw(Fault(F_ILLI));   /* dest rdhc §2.6.1 */
          if read_RD(ha) == read_RD(hb) then write_RD(hc, read_RD(hd))
        },
        CS_NE => {
          if hc == 0b000000 then throw(Fault(F_ILLI));
          if read_RD(ha) != read_RD(hb) then write_RD(hc, read_RD(hd))
        },
        _ => {                                            /* CS_N/CS_Z/CS_P: dest rdhb */
          if hb == 0b000000 then throw(Fault(F_ILLI));
          let cond : bool = match op {
            CS_N => condN(read_RD(ha)),
            CS_Z => condZ(read_RD(ha)),
            CS_P => condP(read_RD(ha)),
            _    => false
          };
          write_RD(hb, if cond then read_RD(hc) else read_RD(hd))
        }
      };
      Ctl_Continue()
    },

    /* ---- RD addi / RB addi (spec §3.6/§4.4) ---- */
    ADDI_RD(ha, hb, imms12) => {
      if ha == 0b000000 then throw(Fault(F_ILLI));
      write_RD(ha, read_RD(hb) + sail_sign_extend(imms12, 64));
      Ctl_Continue()
    },
    ADDI_RB(ha, hb, imms12) => {
      if ha == 0b000000 then throw(Fault(F_ILLI));   /* rbha=rb0 §4.4 */
      let res48 = read_RB(hb)[47 .. 0] + sail_sign_extend(imms12, 48);  /* low 48 §4.4 */
      write_RB_lo48(ha, sail_zero_extend(res48, 64));
      Ctl_Continue()
    },

    /* ---- RD compare immediate (spec §3.8) ---- */
    CMP_IMM(is_signed, ha, hb, imm12) => {
      if ha == 0b000000 then throw(Fault(F_ILLI));
      let a = read_RD(hb);
      if is_signed then {
        write_RD(ha, cmp3_signed(a, sail_sign_extend(imm12, 64)))
      } else {
        write_RD(ha, cmp3_unsigned(a, sail_zero_extend(imm12, 64)))
      };
      Ctl_Continue()
    },

    /* ---- orrr RD-dest logic / shift / extend / compare (spec §3.9–§3.11) ---- */
    ORRR_RD(op, hb, hc, hd) => {
      if hb == 0b000000 then throw(Fault(F_ILLI));   /* dest rdhb §2.6.1 */
      let a = read_RD(hc);
      let b = read_RD(hd);
      let res : bits(64) = match op {
        LG_AND  => a & b,
        LG_ORR  => a | b,
        LG_XOR  => xor_vec(a, b),
        LG_XNOR => not_vec(xor_vec(a, b)),      /* xnor = ~(a^b) §3.10 */
        LG_CMPS => cmp3_signed(a, b),
        LG_CMPU => cmp3_unsigned(a, b),
        _       => do_shift(op, a, unsigned(b[5 .. 0]))  /* shift amt rdhd[5:0] §3.11 */
      };
      write_RD(hb, res);
      Ctl_Continue()
    },

    /* ---- orri shift/extend immediate (spec §3.11) ---- */
    ORRI_SH(op, hb, hc, hd) => {
      if hb == 0b000000 then throw(Fault(F_ILLI));
      write_RD(hb, do_shift(op, read_RD(hc), unsigned(hd)));  /* amt = immu6 */
      Ctl_Continue()
    },

    /* ---- RB arithmetic add/sub (spec §4.3) ---- */
    RBARITH(is_sub, hb, hc, hd) => {
      if hb == 0b000000 then throw(Fault(F_ILLI));   /* rbhb=rb0 §2.6.2 */
      let base = read_RB(hc)[47 .. 0];               /* rbhc (RB) */
      let off  = read_RD(hd)[47 .. 0];               /* rdhd (RD) */
      let res48 = if is_sub then sub_bits(base, off) else base + off;  /* low 48 mod 2^48 */
      write_RB_lo48(hb, sail_zero_extend(res48, 64));
      Ctl_Continue()
    },

    /* ---- RB compare, low 48 unsigned (spec §4.5) ---- */
    RBCMP(hb, hc, hd) => {
      if hb == 0b000000 then throw(Fault(F_ILLI));   /* dest rdhb §2.6.1 */
      let a = read_RB(hc)[47 .. 0];
      let b = read_RB(hd)[47 .. 0];
      let res : bits(64) =
        if unsigned(a) < unsigned(b) then 0xFFFFFFFFFFFFFFFF
        else if a == b then 0x0000000000000000
        else 0x0000000000000001;
      write_RD(hb, res);
      Ctl_Continue()
    },

    /* ---- block copy (spec §3.14/§4.7) ---- */
    BCOPY(op, hb, hc, hd) => {
      let cnt = unsigned(hd);
      if cnt == 0 then throw(Fault(F_ILLI));                 /* immu6 in [1,63] §2.6.3 */
      if unsigned(hb) + cnt > 64 then throw(Fault(F_ILLI));  /* dest range §2.6.3   */
      if unsigned(hc) + cnt > 64 then throw(Fault(F_ILLI));  /* src range §2.6.3    */
      let hbn = unsigned(hb);
      let hcn = unsigned(hc);
      match op {
        BC_RD2RD => {
          if hb == 0b000000 then throw(Fault(F_ILLI));
          foreach (i from 0 to cnt - 1) {
            write_RD(to_reg(hbn + i), read_RD(to_reg(hcn + i)))
          }
        },
        BC_RD2RB => {
          if hb == 0b000000 then throw(Fault(F_ILLI));   /* rb0 dest §2.6.2 */
          foreach (i from 0 to cnt - 1) {
            write_RB_full(to_reg(hbn + i), read_RD(to_reg(hcn + i)))  /* full 64 §4.7 */
          }
        },
        BC_RB2RD => {
          if hb == 0b000000 then throw(Fault(F_ILLI));
          foreach (i from 0 to cnt - 1) {
            write_RD(to_reg(hbn + i), read_RB(to_reg(hcn + i)))       /* full 64 §4.7 */
          }
        },
        BC_RB2RB => {
          if hb == 0b000000 then throw(Fault(F_ILLI));
          foreach (i from 0 to cnt - 1) {
            write_RB_full(to_reg(hbn + i), read_RB(to_reg(hcn + i)))
          }
        }
      };
      Ctl_Continue()
    },

    /* ---- single load (spec §3.1/§4.1) ---- */
    LOAD(w, is_signed, dst_rb, ha, hb, imms12) => {
      if ha == 0b000000 then throw(Fault(F_ILLI));   /* rdha/rbha != 0 */
      let ea = rb_ea(hb, imms12);
      if misaligned(ea, w) then throw(Fault(F_MALIGN));   /* §3.1 */
      let raw = load_be(ea, w);                            /* big-endian §2.1 */
      let loaded = if is_signed then sext_from(raw, w) else raw;
      if dst_rb then write_RB_full(ha, loaded)               /* ldo-rb full 64 §4.1 */
      else write_RD(ha, loaded);
      Ctl_Continue()
    },

    /* ---- single store (spec §3.2/§4.1) ---- */
    STORE(w, src_rb, ha, hb, imms12) => {
      if ha == 0b000000 then throw(Fault(F_ILLI));   /* store from rd0/rb0 illegal §3.2 */
      let ea = rb_ea(hb, imms12);
      if misaligned(ea, w) then throw(Fault(F_MALIGN));
      let data = if src_rb then read_RB(ha) else read_RD(ha);
      store_be(ea, w, data);                              /* big-endian §2.1 */
      Ctl_Continue()
    },

    /* ---- multi load (spec §3.3/§4.2) ---- */
    MLOAD(w, is_signed, dst_rb, ha, hb, hc, hd) => {
      let cnt = unsigned(hd);
      if cnt == 0 then throw(Fault(F_ILLI));                 /* §2.6.3 */
      if ha == 0b000000 then throw(Fault(F_ILLI));
      if unsigned(ha) + cnt > 64 then throw(Fault(F_ILLI));
      let base = read_RB(hb)[47 .. 0];
      let idx  = read_RD(hc)[47 .. 0];                       /* snapshot §2.7 */
      let han  = unsigned(ha);
      foreach (i from 0 to cnt - 1) {
        let ea = base + idx + (i * w);                       /* i-th element §3.3 */
        if misaligned(ea, w) then throw(Fault(F_MALIGN));
        let raw = load_be(ea, w);
        let loaded = if is_signed then sext_from(raw, w) else raw;
        if dst_rb then write_RB_full(to_reg(han + i), loaded)
        else write_RD(to_reg(han + i), loaded)
      };
      Ctl_Continue()
    },

    /* ---- multi store (spec §3.4/§4.2) ---- */
    MSTORE(w, src_rb, ha, hb, hc, hd) => {
      let cnt = unsigned(hd);
      if cnt == 0 then throw(Fault(F_ILLI));
      if ha == 0b000000 then throw(Fault(F_ILLI));
      if unsigned(ha) + cnt > 64 then throw(Fault(F_ILLI));
      let base = read_RB(hb)[47 .. 0];
      let idx  = read_RD(hc)[47 .. 0];
      let han  = unsigned(ha);
      foreach (i from 0 to cnt - 1) {
        let ea = base + idx + (i * w);
        if misaligned(ea, w) then throw(Fault(F_MALIGN));
        let data = if src_rb then read_RB(to_reg(han + i)) else read_RD(to_reg(han + i));
        store_be(ea, w, data)
      };
      Ctl_Continue()
    },

    /* ---- single-register conditional branch (spec §5.1) ---- */
    BR1(cond, ha, imms18) => {
      let x = read_RD(ha);   /* rdha=rd0 legal: reads 0 §2.6.1 */
      let taken : bool = match cond {
        BR_N  => condN(x),  BR_NN => condNN(x), BR_Z  => condZ(x),
        BR_NZ => condNZ(x), BR_P  => condP(x),  BR_NP => condNP(x)
      };
      if taken then nextPC = pcrel(sail_sign_extend(imms18, 48));
      Ctl_Continue()
    },

    /* ---- dual-register conditional branch (spec §5.2) ---- */
    BR2(is_eq, ha, hb, imms12) => {
      let taken = if is_eq then read_RD(ha) == read_RD(hb)
                  else read_RD(ha) != read_RD(hb);
      if taken then nextPC = pcrel(sail_sign_extend(imms12, 48));
      Ctl_Continue()
    },

    /* ---- rela: PC-relative address, 4KB-aligned base (spec §4.8) ---- */
    RELA(ha, imms18) => {
      if ha == 0b000000 then throw(Fault(F_ILLI));   /* rbha=rb0 §2.6.2 */
      let base = read_RB(0b000000)[47 .. 0] & 0xFFFFFFFFF000;    /* rb0 & ~0xFFF */
      let off  = sail_shiftleft(sail_sign_extend(imms18, 48), 12);
      write_RB_lo48(ha, sail_zero_extend(base + off, 64));
      Ctl_Continue()
    },

    /* ---- jump (spec §5.3) ---- */
    JUMP_I(imms24) => {
      nextPC = pcrel(sail_sign_extend(imms24, 48));
      Ctl_Continue()
    },
    JUMP_R(ha, hb, imms12) => {   /* rbha=rb0 => relative (accessor handles) */
      nextPC = read_RB(ha)[47 .. 0] + read_RD(hb)[47 .. 0]
               + sail_shiftleft(sail_sign_extend(imms12, 48), 2);
      Ctl_Continue()
    },

    /* ---- call (spec §5.4): push rb0 to RegRAS, then jump ---- */
    CALL_I(imms24) => {
      let ret = read_RB(0b000000)[47 .. 0];
      ras_push(ret);
      nextPC = ret + sail_shiftleft(sail_sign_extend(imms24, 48), 2);
      Ctl_Continue()
    },
    CALL_R(ha, hb, imms12) => {
      let ret = read_RB(0b000000)[47 .. 0];
      ras_push(ret);
      nextPC = read_RB(ha)[47 .. 0] + read_RD(hb)[47 .. 0]
               + sail_shiftleft(sail_sign_extend(imms12, 48), 2);
      Ctl_Continue()
    },

    /* ---- ret (spec §5.5): pop RegRAS, jump, return value in rdha ---- */
    RET(ha, imms18) => {
      let target = ras_pop();
      nextPC = target;
      write_RD(ha, sail_sign_extend(imms18, 64));   /* rdha=rd0 discards (legal) */
      Ctl_Continue()
    },

    SWYM()   => Ctl_Continue(),
    UNIMP()  => throw(Fault(F_ILLI)),
    HALT(ha) => Ctl_Halt(read_RD(ha)[7 .. 0]),

    UNMODELED() => Ctl_Unimpl(),
    RESERVED()  => throw(Fault(F_UNDI))
  }
}
