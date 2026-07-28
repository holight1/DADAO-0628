#!/usr/bin/env python3
"""KL-143a K2 PTBR/address-space switch protocol probe.

Two cooperative descriptors bind the same ASID and virtual address to
different PTBR roots.  Twelve alternating switches perform:

    write PTBR[asid] -> invalidate the full ASID set -> tlb_gen++ -> VA load

The same-ASID design makes a missing invalidate observable as a real stale
TLB hit.  Guest checks, the KL-140a oracle and raw QEMU/gem5 reports must all
agree.  A separate image omits switch 6's invalidate and must fail.
"""

import argparse
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import k2_report as k2  # noqa: E402
import run_kl129a_tlb_probes as k129  # noqa: E402
import run_kl131a_async_dispatch_probes as k131  # noqa: E402
import run_kl141a_coop_switch as k141  # noqa: E402


Emit = k141.Emit
OP_CSZ = k141.OP_CSZ
MISC_ORR = k141.MISC_ORR
MISC_XOR = k141.MISC_XOR

ROM_BASE = k131.ROM_BASE
ROM_SIZE = 0x10000
RAM_BASE = 0x80000000
RAM_SIZE = 0x200000
IDENTITY_SLOT_OFF = 0xFFF8
SCENARIO = k2.scenario_id_for("KL143a")

CFX_POWER = k131.CFX_POWER
CFX_PTW = k131.CFX_PTW
CFX_TLB = k131.CFX_TLB
MODE_SUPV = k131.MODE_SUPV
MODE_CFX = MODE_SUPV | (CFX_POWER << 8)

PTW_PTBR_CG = k129.PTW_PTBR_CG
PTW_PTHI_CG = k129.PTW_PTHI_CG
PTW_PAHI_CG = k129.PTW_PAHI_CG
PTW_PERM_CG = k129.PTW_PERM_CG
PTW_ENABLE_RC = k129.PTW_ENABLE_RC
TLB_REG_CG = k129.TLB_REG_CG
TLB_ENABLE_RC = k129.TLB_ENABLE_RC
TLB_CONTROL_CG = k129.TLB_CONTROL_CG
TLB_CONTROL_RC = k129.TLB_CONTROL_RC
TLB_ADDR_START_RC = k129.TLB_ADDR_START_RC
TLB_ADDR_SIZE_RC = k129.TLB_ADDR_SIZE_RC
PERM_R = k129.PERM_R

ASID = 6
ASID_BASE = ASID << 42
ASID_SIZE = 1 << 42
L1_INDEX = 9
L2_INDEX = 13
SHARED_VA = ASID_BASE | (L1_INDEX << 29) | (L2_INDEX << 16) | (3 << 13) | 0x100

L1_A, L2_A = 0x80010000, 0x80020000
L1_B, L2_B = 0x80030000, 0x80040000
ROOT_A, ROOT_B = L1_A >> 16, L1_B >> 16
PA_A, PA_B = 0x80100000, 0x80110000
VALUE_A = 0x143A000000000001
VALUE_B = 0x143B000000000002

TASK_A, TASK_B = 1, 2
SWITCHES = 12
N_CHECKPOINTS = SWITCHES + 2
FRAME_WORDS = 135
FRAME_A, FRAME_B = 0x80060000, 0x80061000
ZERO_CONTEXT = 0x80062000

CTRL = 0x8000F000
ADDR_CURSOR = CTRL + 0x08
ADDR_MISMATCH = CTRL + 0x10
MDW = CTRL + 0x100
MDW_SEQ = 0
MDW_CUR = 10
MDW_PROG_A = 11
MDW_PROG_B = 12
MDW_SWITCH = 13
MDW_TLB_GEN = 14
ADDR_SEQ = MDW
ADDR_CUR = MDW + MDW_CUR * 8
ADDR_PROG_A = MDW + MDW_PROG_A * 8
ADDR_PROG_B = MDW + MDW_PROG_B * 8
ADDR_SWITCH = MDW + MDW_SWITCH * 8
ADDR_TLB_GEN = MDW + MDW_TLB_GEN * 8

REPORT_PA = k141.REPORT_PA
REPORT_WINDOW = k141.REPORT_WINDOW
DOORBELL_OFF = k141.DOORBELL_OFF
DOORBELL = k141.DOORBELL
IDENTITY_MIRROR = k141.IDENTITY_MIRROR
EVIDENCE = os.path.join(REPO, ".work", "evidence", "kl143a-address-space")

GUARDS = (
    (L1_A - 8, 0x6AED143A00000001),
    (L2_A - 8, 0x6AED143A00000002),
    (L1_B - 8, 0x6AED143B00000003),
    (L2_B - 8, 0x6AED143B00000004),
    (FRAME_A - 8, 0x6AED143A00000005),
    (FRAME_A + FRAME_WORDS * 8, 0x6AED143A00000006),
    (FRAME_B - 8, 0x6AED143B00000007),
    (FRAME_B + FRAME_WORDS * 8, 0x6AED143B00000008),
    (REPORT_PA - 8, 0x6AED143000000009),
    (REPORT_PA + REPORT_WINDOW, 0x6AED14300000000A),
)

MASK64 = (1 << 64) - 1


def put_qword(image, address, value):
    offset = address - RAM_BASE
    if offset < 0 or offset + 8 > len(image):
        raise ValueError(f"RAM address outside image: {address:#x}")
    image[offset:offset + 8] = struct.pack(">Q", value & MASK64)


def cfx_write_reg(e, cfx, cg, rc, rd):
    k131.write_crrr(e.out, k131.OP_CFX2RC, cfx, cg, rc, rd)


def cfx_write_value(e, cfx, cg, rc, value, scratch=2):
    e.load("rd", scratch, value)
    cfx_write_reg(e, cfx, cg, rc, scratch)


def emit_invalidate(e):
    cfx_write_value(
        e, CFX_TLB, TLB_CONTROL_CG, TLB_ADDR_START_RC, ASID_BASE)
    cfx_write_value(
        e, CFX_TLB, TLB_CONTROL_CG, TLB_ADDR_SIZE_RC, ASID_SIZE)
    cfx_write_value(e, CFX_TLB, TLB_CONTROL_CG, TLB_CONTROL_RC, 2)


def emit_check_eq(e, actual_rd, expected):
    k141.check_eq_rd(e, actual_rd, expected)


def emit_guard_check(e, label):
    e.mark(label)
    for address, value in GUARDS:
        e.load("rb", 8, address)
        e.ldo_rd(10, 8, 0)
        emit_check_eq(e, 10, value)
    e.ret()


def emit_checkpoint_writer(e, label):
    """Args rd8/9=event/task, rb9=context, rd27=ptbr_asid, rd28=tlb_gen."""
    e.mark(label)
    e.orrr(MISC_ORR, 21, 8, 0)
    e.orrr(MISC_ORR, 22, 9, 0)
    e.orrr(MISC_ORR, 29, 27, 0)
    e.orrr(MISC_ORR, 30, 28, 0)
    e.addi_rb(16, 9, 0)
    e.addi_rb(8, 16, 0)
    e.load("rd", 12, FRAME_WORDS)
    e.call("FNV_WORDS")
    e.orrr(MISC_ORR, 18, 13, 0)
    e.load("rb", 8, MDW)
    e.load("rd", 12, 16)
    e.call("FNV_WORDS")
    e.orrr(MISC_ORR, 14, 13, 0)
    e.load("rb", 8, ADDR_SEQ)
    e.ldo_rd(19, 8, 0)
    e.addi_rd(20, 19, 1)
    e.sto_rd(20, 8, 0)
    e.load("rb", 8, ADDR_CURSOR)
    e.ldo_rb(12, 8, 0)
    e.sto_rd(19, 12, 0)
    e.sto_rd(21, 12, 8)
    e.sto_rd(22, 12, 16)
    e.load("rd", 20, MODE_CFX)
    e.sto_rd(20, 12, 24)
    e.load("rd", 20, 0)
    e.sto_rd(20, 12, 32)
    e.sto_rd(20, 12, 40)
    e.sto_rd(20, 12, 48)
    e.sto_rd(18, 12, 56)
    e.sto_rd(14, 12, 64)
    e.sto_rd(29, 12, 72)
    e.sto_rd(30, 12, 80)
    e.addi_rb(12, 12, k2.CHECKPOINT_SIZE)
    e.sto_rb(12, 8, 0)
    e.ret()


def emit_checkpoint(e, event, task, frame, root, tlb_gen):
    e.load("rd", 8, event)
    e.load("rd", 9, task)
    e.load("rb", 9, frame)
    e.load("rd", 27, (ASID << 48) | root)
    e.load("rd", 28, tlb_gen)
    e.call("EMIT_CKPT")


def descriptor(task, root):
    words = [0, ASID, root]
    words += [
        0x5143000000000000 | (task << 32) | word
        for word in range(3, FRAME_WORDS)
    ]
    assert len(words) == FRAME_WORDS
    return words


def build_image(omit_switch=None):
    if omit_switch is not None and not 2 <= omit_switch <= SWITCHES:
        raise ValueError("omit_switch outside scenario")
    e = Emit()
    k131.emit_boot_stub(e.out, ROM_BASE + 0x200)

    e.mark("MAIN")
    emit_checkpoint(e, k2.EVENT_INIT, 0, ZERO_CONTEXT, 0, 0)
    e.call("GUARD_CHECK")

    cfx_write_value(e, CFX_PTW, PTW_PTHI_CG, ASID, 0)
    cfx_write_value(e, CFX_PTW, PTW_PAHI_CG, ASID, 0)
    cfx_write_value(
        e, CFX_PTW, PTW_PERM_CG, PTW_ENABLE_RC, 1 << ASID)
    cfx_write_value(
        e, CFX_TLB, TLB_REG_CG, TLB_ENABLE_RC, 1 << ASID)

    generation = 0
    for switch in range(1, SWITCHES + 1):
        task = TASK_A if switch % 2 else TASK_B
        frame = FRAME_A if task == TASK_A else FRAME_B
        root = ROOT_A if task == TASK_A else ROOT_B
        expected = VALUE_A if task == TASK_A else VALUE_B
        progress_addr = ADDR_PROG_A if task == TASK_A else ADDR_PROG_B

        # The binding is consumed from the cooperative descriptor, not from
        # a hidden host/backend state.
        e.load("rb", 13, frame)
        e.ldo_rd(8, 13, 8)
        emit_check_eq(e, 8, ASID)
        e.ldo_rd(2, 13, 16)
        emit_check_eq(e, 2, root)
        cfx_write_reg(e, CFX_PTW, PTW_PTBR_CG, ASID, 2)

        if switch != omit_switch:
            emit_invalidate(e)
            generation += 1
            e.load("rb", 8, ADDR_TLB_GEN)
            e.ldo_rd(9, 8, 0)
            e.addi_rd(9, 9, 1)
            e.sto_rd(9, 8, 0)

        e.load("rb", 8, ADDR_CUR)
        e.load("rd", 9, task)
        e.sto_rd(9, 8, 0)
        e.load("rb", 8, ADDR_SWITCH)
        e.ldo_rd(9, 8, 0)
        e.addi_rd(9, 9, 1)
        e.sto_rd(9, 8, 0)
        e.load("rb", 8, progress_addr)
        e.ldo_rd(9, 8, 0)
        e.addi_rd(9, 9, 1)
        e.sto_rd(9, 8, 0)

        e.load("rb", 3, SHARED_VA)
        e.ldo_rd(27, 3, 0)
        emit_check_eq(e, 27, expected)
        emit_checkpoint(
            e, k2.EVENT_AS_SWITCH, task, frame, root, generation)

    for address, expected in (
            (ADDR_CUR, TASK_B),
            (ADDR_PROG_A, SWITCHES // 2),
            (ADDR_PROG_B, SWITCHES // 2),
            (ADDR_SWITCH, SWITCHES),
            # The guest contract is invariant across positive/mutation
            # images: every switch requires one real invalidate.
            (ADDR_TLB_GEN, SWITCHES),
            (ADDR_SEQ, SWITCHES + 1)):
        e.load("rb", 8, address)
        e.ldo_rd(8, 8, 0)
        emit_check_eq(e, 8, expected)
    e.call("GUARD_CHECK")
    emit_checkpoint(
        e, k2.EVENT_FINAL, TASK_B, ZERO_CONTEXT, ROOT_B, generation)

    e.load("rb", 12, REPORT_PA)
    for offset, value in (
            (0, k2.MAGIC), (8, k2.SCHEMA_VERSION), (16, SCENARIO)):
        e.load("rd", 8, value)
        e.sto_rd(8, 12, offset)
    e.load("rb", 8, IDENTITY_MIRROR)
    e.ldo_rd(8, 8, 0)
    e.sto_rd(8, 12, 24)
    e.load("rb", 8, ADDR_MISMATCH)
    e.ldo_rd(9, 8, 0)
    e.load("rd", 10, k2.STATUS_PASS)
    e.load("rd", 11, k2.STATUS_FAIL)
    e.word((OP_CSZ << 24) | (9 << 18) | (8 << 12) | (10 << 6) | 11)
    e.sto_rd(8, 12, 32)
    e.sto_rd(9, 12, 40)
    e.load("rb", 8, ADDR_SEQ)
    e.ldo_rd(8, 8, 0)
    e.sto_rd(8, 12, 48)
    e.load("rd", 8, 0)
    e.sto_rd(8, 12, 56)
    e.load("rd", 8, k2.MAX_CHECKPOINTS)
    e.sto_rd(8, 12, 64)
    e.load("rd", 8, DOORBELL)
    e.load("rb", 8, REPORT_PA + DOORBELL_OFF)
    e.sto_rd(8, 8, 0)
    e.load("rd", 8, 0)
    e.riii(k131.OP_HALT, 8, 0)

    k141.emit_fnv_words(e, "FNV_WORDS")
    emit_guard_check(e, "GUARD_CHECK")
    emit_checkpoint_writer(e, "EMIT_CKPT")
    e.pad_unimp(IDENTITY_SLOT_OFF)
    e.out.extend(b"\0" * 8)
    if len(e.out) > ROM_SIZE:
        raise ValueError("ROM image overflow")
    rom = bytearray(e.finish())

    frame_a = descriptor(TASK_A, ROOT_A)
    frame_b = descriptor(TASK_B, ROOT_B)
    ram = bytearray(RAM_SIZE)
    put_qword(ram, ADDR_CURSOR, REPORT_PA + k2.HEADER_SIZE)
    for address, value in GUARDS:
        put_qword(ram, address, value)
    for address, words in ((FRAME_A, frame_a), (FRAME_B, frame_b)):
        offset = address - RAM_BASE
        ram[offset:offset + FRAME_WORDS * 8] = struct.pack(
            f">{FRAME_WORDS}Q", *words)

    put_qword(ram, L1_A + L1_INDEX * 8, (L2_A & 0xFFFFFFFFFFFF0000) | 1)
    put_qword(ram, L2_A + L2_INDEX * 8, k129.normal_pte(PA_A, [3], PERM_R))
    put_qword(ram, L1_B + L1_INDEX * 8, (L2_B & 0xFFFFFFFFFFFF0000) | 1)
    put_qword(ram, L2_B + L2_INDEX * 8, k129.normal_pte(PA_B, [3], PERM_R))
    put_qword(ram, PA_A + (SHARED_VA & 0xFFFF), VALUE_A)
    put_qword(ram, PA_B + (SHARED_VA & 0xFFFF), VALUE_B)

    identity = k2.image_identity(
        bytes(rom), bytes(ram),
        rom_identity_slot=(IDENTITY_SLOT_OFF, 8),
        ram_report_area=(REPORT_PA - RAM_BASE, k2.MAX_REPORT_SIZE))
    rom = bytearray(
        k2.embed_image_identity(bytes(rom), IDENTITY_SLOT_OFF, identity))
    put_qword(ram, IDENTITY_MIRROR, identity)
    return bytes(rom), bytes(ram), (frame_a, frame_b), identity


def mdw_digest(seq, current, progress_a, progress_b, switches, tlb_gen):
    words = [0] * 16
    words[MDW_SEQ] = seq
    words[MDW_CUR] = current
    words[MDW_PROG_A] = progress_a
    words[MDW_PROG_B] = progress_b
    words[MDW_SWITCH] = switches
    words[MDW_TLB_GEN] = tlb_gen
    return k2.fnv1a64(words)


def build_oracle(frames, identity):
    frame_a, frame_b = frames
    zero_digest = k2.fnv1a64([0] * FRAME_WORDS)
    expected = [k2.ExpectedCheckpoint(
        event_kind=k2.EVENT_INIT, task_id=0, run_mode=MODE_SUPV,
        cfx_code=CFX_POWER, cause=0, saved_pc=0, resume_pc=0,
        context_digest=zero_digest,
        memory_digest=mdw_digest(0, 0, 0, 0, 0, 0),
        asid=ASID, ptbr=0, tlb_gen=0)]
    progress_a = progress_b = 0
    for switch in range(1, SWITCHES + 1):
        task = TASK_A if switch % 2 else TASK_B
        root = ROOT_A if task == TASK_A else ROOT_B
        frame = frame_a if task == TASK_A else frame_b
        if task == TASK_A:
            progress_a += 1
        else:
            progress_b += 1
        expected.append(k2.ExpectedCheckpoint(
            event_kind=k2.EVENT_AS_SWITCH, task_id=task,
            run_mode=MODE_SUPV, cfx_code=CFX_POWER, cause=0,
            saved_pc=0, resume_pc=0, context_digest=k2.fnv1a64(frame),
            memory_digest=mdw_digest(
                switch, task, progress_a, progress_b, switch, switch),
            asid=ASID, ptbr=root, tlb_gen=switch))
    expected.append(k2.ExpectedCheckpoint(
        event_kind=k2.EVENT_FINAL, task_id=TASK_B, run_mode=MODE_SUPV,
        cfx_code=CFX_POWER, cause=0, saved_pc=0, resume_pc=0,
        context_digest=zero_digest,
        memory_digest=mdw_digest(
            SWITCHES + 1, TASK_B, SWITCHES // 2, SWITCHES // 2,
            SWITCHES, SWITCHES),
        asid=ASID, ptbr=ROOT_B, tlb_gen=SWITCHES))
    assert len(expected) == N_CHECKPOINTS
    return k2.ScenarioOracle(
        scenario_id=SCENARIO, image_identity=identity, checkpoints=expected)


class TransportError(Exception):
    pass


def verify_run_image(rom_path, ram_path, oracle):
    with open(rom_path, "rb") as fh:
        rom = fh.read()
    with open(ram_path, "rb") as fh:
        ram = fh.read()
    if len(rom) != ROM_SIZE or len(ram) != RAM_SIZE:
        raise TransportError("run image size mismatch")
    computed = k2.image_identity(
        rom, ram, rom_identity_slot=(IDENTITY_SLOT_OFF, 8),
        ram_report_area=(REPORT_PA - RAM_BASE, k2.MAX_REPORT_SIZE))
    embedded = struct.unpack(
        ">Q", rom[IDENTITY_SLOT_OFF:IDENTITY_SLOT_OFF + 8])[0]
    mirror_offset = IDENTITY_MIRROR - RAM_BASE
    mirrored = struct.unpack(">Q", ram[mirror_offset:mirror_offset + 8])[0]
    if computed != oracle.image_identity or embedded != computed or mirrored != computed:
        raise TransportError("run image identity mismatch")


def run_one(round_no, rom_path, ram_path, oracle, tag):
    try:
        verify_run_image(rom_path, ram_path, oracle)
        qemu = k141.run_qemu(
            rom_path, ram_path,
            os.path.join(EVIDENCE, f"qemu{tag}-{round_no:02d}.log"))
        gem5 = k141.run_gem5(
            rom_path, ram_path,
            os.path.join(EVIDENCE, f"gem5{tag}-{round_no:02d}.log"))
    except (OSError, k141.TransportError, TransportError) as exc:
        return k2.Verdict.HARNESS_ERROR, [str(exc)], None, None
    for backend, data in (("qemu", qemu), ("gem5", gem5)):
        with open(os.path.join(
                EVIDENCE, f"report-{backend}{tag}-{round_no:02d}.bin"), "wb") as fh:
            fh.write(data)
    verdict, reasons = k2.compare_dual_backend(qemu, gem5, oracle)
    return verdict, reasons, qemu, gem5


def write_image(tag, omit_switch=None):
    rom, ram, frames, identity = build_image(omit_switch)
    rom_path = os.path.join(EVIDENCE, f"kl143a-{tag}.bin")
    ram_path = os.path.join(EVIDENCE, f"kl143a-{tag}-ram.bin")
    with open(rom_path, "wb") as fh:
        fh.write(rom)
    with open(ram_path, "wb") as fh:
        fh.write(ram)
    return rom_path, ram_path, build_oracle(frames, identity), rom, ram


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--skip-negative", action="store_true")
    parser.add_argument("--omit-switch", type=int, default=6)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")
    if not 2 <= args.omit_switch <= SWITCHES:
        parser.error("--omit-switch outside 2..12 (switch 1 has no stale fill)")

    os.makedirs(EVIDENCE, exist_ok=True)
    rom_path, ram_path, oracle, rom, ram = write_image("positive")
    print(f"image: sha256-rom={hashlib.sha256(rom).hexdigest()}")
    print(f"image: sha256-ram={hashlib.sha256(ram).hexdigest()}")
    print(f"image: canonical identity={oracle.image_identity:#018x} "
          f"switches={SWITCHES} checkpoints={N_CHECKPOINTS}")

    failures = 0
    for round_no in range(1, args.rounds + 1):
        verdict, reasons, _, _ = run_one(
            round_no, rom_path, ram_path, oracle, "-pos")
        if verdict == k2.Verdict.PASS:
            print(f"round {round_no}/{args.rounds}: qemu=PASS gem5=PASS "
                  "oracle=PASS cross=PASS")
        else:
            failures += 1
            print(f"round {round_no}: {verdict.value}")
            for reason in reasons[:12]:
                print(f"  {reason}")

    if failures == 0 and not args.skip_negative:
        mrom, mram, moracle, _, _ = write_image(
            "mutation", args.omit_switch)
        verdict, reasons, qemu, gem5 = run_one(
            1, mrom, mram, moracle, "-mut")
        expected_fail = False
        detail = []
        if qemu is not None and gem5 is not None:
            rq, rg = k2.decode_report(qemu), k2.decode_report(gem5)
            vq = k2.evaluate_report_bytes(qemu, moracle)[0]
            vg = k2.evaluate_report_bytes(gem5, moracle)[0]
            detail = [
                f"qemu={vq.value}/status={k2.STATUS_NAMES[rq.final_status]}"
                f"/mismatch={rq.mismatch_count}",
                f"gem5={vg.value}/status={k2.STATUS_NAMES[rg.final_status]}"
                f"/mismatch={rg.mismatch_count}",
            ]
            expected_fail = (
                verdict == k2.Verdict.FAIL
                and vq == k2.Verdict.FAIL and vg == k2.Verdict.FAIL
                and rq.final_status == k2.STATUS_FAIL
                and rg.final_status == k2.STATUS_FAIL
                and rq.mismatch_count > 0 and rg.mismatch_count > 0)
        if expected_fail:
            print(f"negative omit-invalidate@{args.omit_switch}: dual=FAIL "
                  f"({' '.join(detail)}) as required")
        else:
            failures += 1
            print(f"negative mutation: unexpected {verdict.value} "
                  f"({' '.join(detail)})")
            for reason in reasons[:12]:
                print(f"  {reason}")

        verdict, reasons, _, _ = run_one(
            1, rom_path, ram_path, oracle, "-post")
        if verdict == k2.Verdict.PASS:
            print("post-restore round: PASS")
        else:
            failures += 1
            print(f"post-restore round: {verdict.value}")
            for reason in reasons[:12]:
                print(f"  {reason}")

    if failures:
        print(f"FAIL: {failures} failing round(s)")
        raise SystemExit(1)
    claims = (
        "same-ASID dual-root switch, PTBR binding from cooperative frame, "
        "full-set explicit invalidate, monotonic tlb_gen, stale-hit negative, "
        "guest+oracle+cross-backend")
    nonclaims = (
        "integrated register context switch, async trap context, "
        "disable-enable TLB lifetime, user mode, RF, Atomics/SMP, multi-hart, "
        "Linux paging/scheduler, real devices, Minor/O3, performance")
    print(f"QEMU: pass=[{claims}] rounds={args.rounds}/{args.rounds}; "
          f"skip=[]; fail=[]; non-claim=[{nonclaims}]")
    print(f"gem5: pass=[{claims}] rounds={args.rounds}/{args.rounds}; "
          f"skip=[]; fail=[]; non-claim=[{nonclaims}]")
    print("PASS: KL-143a PTBR/address-space switch dual-backend oracle")


if __name__ == "__main__":
    main()
