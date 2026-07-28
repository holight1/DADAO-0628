#!/usr/bin/env python3
"""KL-140a self-test runner for the K2 report contract module.

Exercises `tests/scripts/k2_report.py` against the frozen contract
(`docs/reviews/k2-baremetal-regression-contract-20260728.md`):

* normal encode -> decode -> oracle/dual-backend compare round trip;
* bad magic/version/length/capacity/truncation -> HARNESS-ERROR;
* checkpoint overflow and truncation handling;
* sequence/event/task/mode/cfx/cause/PC/PTBR/asid/tlb_gen/digest field
  mismatches -> FAIL;
* dual-backend reports that agree with each other but violate the oracle
  must FAIL; reports that pass the oracle but differ between backends must
  FAIL (cross-compare-only detection);
* mutation sensitivity: flipping any single key field of a passing report
  must flip the verdict from PASS to FAIL;
* guest FAIL/mismatch is never upgraded to PASS by oracle configuration
  (there is no such knob); SKIP exists only at the scheduling layer
  (None bytes), can never relabel a produced report, and never masks a
  failure observed on the other backend;
* image identity is the canonical hash: computed with the ROM identity
  slot and the RAM report area zeroed, then really embedded into the ROM
  fixture, verified stable after embedding, sensitive to tampering, and
  provably different from the naive self-referential whole-image hash;
* scenario ids accept only the frozen six-byte, hyphen-free ``KLnnna`` form;
  incomplete dual-backend evidence remains SKIP even when the one backend
  that ran passed.

Pure host-side: no backend is launched and no log string is consulted.
"""

import argparse
import copy
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import k2_report as k2  # noqa: E402


SCENARIO = k2.scenario_id_for("KL140a")

# ROM/RAM fixtures with a dedicated 8-byte ROM identity slot and a RAM
# report area, exactly like a real K2 image: the identity is computed over
# the canonicalized images and then embedded into the slot.
ROM_SLOT = (16, 8)
RAM_REPORT_AREA = (1024, k2.MAX_REPORT_SIZE)
ROM_PRE = bytes(
    (0x40 + index) & 0xFF for index in range(64))  # slot bytes nonzero
RAM_PRE = bytes(8192)
IDENTITY = k2.image_identity(
    ROM_PRE, RAM_PRE,
    rom_identity_slot=ROM_SLOT, ram_report_area=RAM_REPORT_AREA)
ROM = k2.embed_image_identity(ROM_PRE, ROM_SLOT[0], IDENTITY)
RAM = RAM_PRE

TASK0, TASK1, TASK2 = 1, 2, 3
MODE_SUPV = 2
CFX_POWER = 0
CFX_TIMER = 18
CAUSE_TIMER = 1 << 10

ASID6 = 6
ASID7 = 7
PTBR6 = 0x8001  # raw stored value: L1 base 0x80010000 >> 16
PTBR7 = 0x8002

PC_MAIN = 0x00100400
PC_TASK1 = 0x00100800
PC_TASK2 = 0x00100C00
PC_TRAP_VECTOR = 0x00102000
PC_TRAP_SITE = 0x00100840


def frame_words(task):
    """Deterministic stand-in for a 135-word cooperative frame."""
    return [((task << 56) | (index + 1)) for index in range(135)]


def trap_frame_words(task, level):
    return [((task << 56) | (level << 48) | (index + 1))
            for index in range(198)]


def mem_words(task):
    return [0xCAFE0000 + task * 16 + index for index in range(8)]


CTX0 = k2.fnv1a64(frame_words(TASK0))
CTX1 = k2.fnv1a64(frame_words(TASK1))
CTX2 = k2.fnv1a64(frame_words(TASK2))
TRAPCTX1 = k2.fnv1a64(trap_frame_words(TASK1, 1))
MEM0 = k2.fnv1a64(mem_words(TASK0))
MEM1 = k2.fnv1a64(mem_words(TASK1))
MEM2 = k2.fnv1a64(mem_words(TASK2))


def canonical_report():
    ckpts = [
        k2.build_checkpoint(0, k2.EVENT_INIT, TASK0, MODE_SUPV, CFX_POWER,
                            0, 0, 0, CTX0, MEM0, ASID6, PTBR6, 0),
        # Outgoing side of task0 -> task1, bound to task0's saved frame.
        k2.build_checkpoint(1, k2.EVENT_COOP_SAVE, TASK0, MODE_SUPV,
                            CFX_POWER, 0, PC_MAIN + 8, 0, CTX0, MEM0,
                            ASID6, PTBR6, 0),
        # Incoming side, bound to task1's restored frame and actual PC.
        k2.build_checkpoint(2, k2.EVENT_COOP_RESTORE, TASK1, MODE_SUPV,
                            CFX_POWER, 0, 0, PC_TASK1, CTX1, MEM1,
                            ASID6, PTBR6, 0),
        k2.build_checkpoint(3, k2.EVENT_TRAP_ENTER, TASK1, MODE_SUPV,
                            CFX_TIMER, CAUSE_TIMER, PC_TRAP_SITE,
                            PC_TRAP_VECTOR, TRAPCTX1, MEM1, ASID6, PTBR6, 0),
        k2.build_checkpoint(4, k2.EVENT_TRAP_RETURN, TASK1, MODE_SUPV,
                            CFX_TIMER, CAUSE_TIMER, PC_TRAP_SITE,
                            PC_TRAP_SITE + 4, CTX1, MEM1, ASID6, PTBR6, 0),
        k2.build_checkpoint(5, k2.EVENT_AS_SWITCH, TASK1, MODE_SUPV,
                            CFX_POWER, 0, PC_TRAP_SITE + 8,
                            PC_TRAP_SITE + 12, CTX1, MEM1, ASID7, PTBR7, 1),
        # Outgoing side of task1 -> task2.
        k2.build_checkpoint(6, k2.EVENT_COOP_SAVE, TASK1, MODE_SUPV,
                            CFX_POWER, 0, PC_TRAP_SITE + 16, 0, CTX1, MEM1,
                            ASID7, PTBR7, 1),
        k2.build_checkpoint(7, k2.EVENT_COOP_RESTORE, TASK2, MODE_SUPV,
                            CFX_POWER, 0, 0, PC_TASK2, CTX2, MEM2,
                            ASID7, PTBR7, 1),
        k2.build_checkpoint(8, k2.EVENT_TIMER, TASK2, MODE_SUPV, CFX_TIMER,
                            CAUSE_TIMER, PC_TASK2 + 20, PC_TRAP_VECTOR,
                            TRAPCTX1, MEM2, ASID7, PTBR7, 1),
        k2.build_checkpoint(9, k2.EVENT_FINAL, TASK2, MODE_SUPV, CFX_POWER,
                            0, 0, 0, CTX2, MEM2, ASID7, PTBR7, 1),
    ]
    return k2.Report(
        scenario_id=SCENARIO, image_identity=IDENTITY,
        final_status=k2.STATUS_PASS, mismatch_count=0, flags=0,
        checkpoints=ckpts)


def canonical_oracle():
    expect = [
        k2.ExpectedCheckpoint(event_kind=k2.EVENT_INIT, task_id=TASK0,
                              run_mode=MODE_SUPV, cfx_code=CFX_POWER,
                              context_digest=CTX0, asid=ASID6, ptbr=PTBR6,
                              tlb_gen=0),
        k2.ExpectedCheckpoint(event_kind=k2.EVENT_COOP_SAVE, task_id=TASK0,
                              saved_pc=PC_MAIN + 8, context_digest=CTX0),
        k2.ExpectedCheckpoint(event_kind=k2.EVENT_COOP_RESTORE,
                              task_id=TASK1, resume_pc=PC_TASK1,
                              context_digest=CTX1),
        k2.ExpectedCheckpoint(event_kind=k2.EVENT_TRAP_ENTER, task_id=TASK1,
                              cfx_code=CFX_TIMER, cause=CAUSE_TIMER,
                              saved_pc=PC_TRAP_SITE,
                              resume_pc=PC_TRAP_VECTOR,
                              context_digest=TRAPCTX1),
        k2.ExpectedCheckpoint(event_kind=k2.EVENT_TRAP_RETURN, task_id=TASK1,
                              resume_pc=PC_TRAP_SITE + 4),
        k2.ExpectedCheckpoint(event_kind=k2.EVENT_AS_SWITCH, task_id=TASK1,
                              asid=ASID7, ptbr=PTBR7, tlb_gen=1),
        k2.ExpectedCheckpoint(event_kind=k2.EVENT_COOP_SAVE, task_id=TASK1,
                              saved_pc=PC_TRAP_SITE + 16,
                              context_digest=CTX1),
        k2.ExpectedCheckpoint(event_kind=k2.EVENT_COOP_RESTORE,
                              task_id=TASK2, resume_pc=PC_TASK2,
                              memory_digest=MEM2, asid=ASID7),
        k2.ExpectedCheckpoint(event_kind=k2.EVENT_TIMER, task_id=TASK2,
                              cfx_code=CFX_TIMER, cause=CAUSE_TIMER),
        k2.ExpectedCheckpoint(event_kind=k2.EVENT_FINAL, task_id=TASK2),
    ]
    return k2.ScenarioOracle(
        scenario_id=SCENARIO, image_identity=IDENTITY, checkpoints=expect)


def set_word(data, index, value):
    out = bytearray(data)
    struct.pack_into(">Q", out, index * 8, value)
    return bytes(out)


def mutate(report, **changes):
    out = copy.deepcopy(report)
    for name, value in changes.items():
        setattr(out, name, value)
    return out


def mutate_ckpt(report, index, **changes):
    out = copy.deepcopy(report)
    for name, value in changes.items():
        setattr(out.checkpoints[index], name, value)
    return out


class Suite:
    def __init__(self):
        self.failures = []
        self.count = 0

    def check(self, name, condition, detail=""):
        self.count += 1
        if not condition:
            self.failures.append(f"{name}: {detail}")

    def expect(self, name, pair, verdict):
        got, reasons = pair
        self.check(
            name, got == verdict,
            f"expected {verdict.value}, got {got.value}; "
            f"reasons={reasons[:3]}")

    def run(self):
        report = canonical_report()
        oracle = canonical_oracle()
        encoded = k2.encode_report(report)

        # --- schema constants and round trip -----------------------------
        self.check("const header", k2.HEADER_SIZE == 72)
        self.check("const record", k2.CHECKPOINT_SIZE == 88)
        self.check("const max size", k2.MAX_REPORT_SIZE == 5704)
        self.check("encoded length", len(encoded) == 72 + 10 * 88)
        self.check("scenario_id encoding", SCENARIO == 0x4B4C313430610000)
        for bad_tag in ("KL-140a", "KL140"):
            try:
                k2.scenario_id_for(bad_tag)
            except ValueError:
                rejected = True
            else:
                rejected = False
            self.check(f"scenario_id rejects {bad_tag!r}", rejected)
        decoded = k2.decode_report(encoded)
        self.check("roundtrip equal", decoded == report)
        self.check("roundtrip bytes",
                   k2.encode_report(decoded) == encoded)
        self.expect("oracle PASS",
                    k2.compare_with_oracle(decoded, oracle), k2.Verdict.PASS)
        self.expect("dual PASS",
                    k2.compare_dual_backend(encoded, encoded, oracle),
                    k2.Verdict.PASS)

        # --- canonical image identity (embedded for real) -----------------
        self.check(
            "identity stable after embed",
            k2.image_identity(ROM, RAM, rom_identity_slot=ROM_SLOT,
                              ram_report_area=RAM_REPORT_AREA) == IDENTITY)
        naive = struct.unpack(
            ">Q", hashlib.sha256(ROM + RAM).digest()[:8])[0]
        self.check("naive whole-image hash self-references",
                   naive != IDENTITY)
        tampered_rom = bytearray(ROM)
        tampered_rom[0] ^= 1  # outside the identity slot
        self.check(
            "identity detects tamper",
            k2.image_identity(bytes(tampered_rom), RAM,
                              rom_identity_slot=ROM_SLOT,
                              ram_report_area=RAM_REPORT_AREA) != IDENTITY)
        tampered_slot = k2.embed_image_identity(ROM, ROM_SLOT[0],
                                                IDENTITY ^ 1)
        self.check(
            "identity slot content is normalized away",
            k2.image_identity(tampered_slot, RAM,
                              rom_identity_slot=ROM_SLOT,
                              ram_report_area=RAM_REPORT_AREA) == IDENTITY)
        ram_with_guest_report = bytearray(RAM)
        ram_with_guest_report[1024:1080] = encoded[:56]
        self.check(
            "report area writes do not change identity",
            k2.image_identity(ROM, bytes(ram_with_guest_report),
                              rom_identity_slot=ROM_SLOT,
                              ram_report_area=RAM_REPORT_AREA) == IDENTITY)
        ram_tampered = bytearray(RAM)
        ram_tampered[7000] ^= 1  # outside the 1024..6728 report area
        self.check(
            "identity detects RAM tamper outside report area",
            k2.image_identity(ROM, bytes(ram_tampered),
                              rom_identity_slot=ROM_SLOT,
                              ram_report_area=RAM_REPORT_AREA) != IDENTITY)

        # --- digest algorithm pinned to published FNV-1a-64 vectors ------
        self.check("fnv empty", k2.fnv1a64([]) == 0xCBF29CE484222325)
        self.check("fnv [0]", k2.fnv1a64([0]) == 0xAF63BD4C8601B7DF)
        self.check("fnv [1]", k2.fnv1a64([1]) == 0xAF63BC4C8601B62C)
        self.check("fnv [1,2]", k2.fnv1a64([1, 2]) == 0x082F2407B4E8902A)
        self.check("fnv order",
                   k2.fnv1a64([1, 2]) != k2.fnv1a64([2, 1]))

        # --- structural failures must be HARNESS-ERROR --------------------
        self.expect("bad magic",
                    k2.evaluate_report_bytes(
                        set_word(encoded, 0, 0xDEADBEEF), oracle),
                    k2.Verdict.HARNESS_ERROR)
        self.expect("bad version",
                    k2.evaluate_report_bytes(set_word(encoded, 1, 2), oracle),
                    k2.Verdict.HARNESS_ERROR)
        self.expect("bad capacity",
                    k2.evaluate_report_bytes(set_word(encoded, 8, 63),
                                             oracle),
                    k2.Verdict.HARNESS_ERROR)
        self.expect("count over capacity",
                    k2.evaluate_report_bytes(set_word(encoded, 6, 65),
                                             oracle),
                    k2.Verdict.HARNESS_ERROR)
        self.expect("count/length mismatch",
                    k2.evaluate_report_bytes(set_word(encoded, 6, 5), oracle),
                    k2.Verdict.HARNESS_ERROR)
        self.expect("truncated record",
                    k2.evaluate_report_bytes(encoded[:-1], oracle),
                    k2.Verdict.HARNESS_ERROR)
        self.expect("truncated header",
                    k2.evaluate_report_bytes(encoded[:40], oracle),
                    k2.Verdict.HARNESS_ERROR)
        self.expect("trailing garbage",
                    k2.evaluate_report_bytes(encoded + b"\0" * 8, oracle),
                    k2.Verdict.HARNESS_ERROR)
        self.expect("image identity mismatch",
                    k2.compare_with_oracle(
                        mutate(decoded, image_identity=IDENTITY ^ 1), oracle),
                    k2.Verdict.HARNESS_ERROR)
        self.expect("dual harness precedence",
                    k2.compare_dual_backend(encoded[:-1], encoded, oracle),
                    k2.Verdict.HARNESS_ERROR)

        # --- content mismatches must be FAIL, never SKIP/PASS -------------
        self.expect("seq gap",
                    k2.compare_with_oracle(
                        mutate_ckpt(decoded, 3, seq=9), oracle),
                    k2.Verdict.FAIL)
        swapped = copy.deepcopy(decoded)
        swapped.checkpoints[2].seq, swapped.checkpoints[3].seq = 3, 2
        self.expect("seq reordered",
                    k2.compare_with_oracle(swapped, oracle), k2.Verdict.FAIL)
        self.expect("guest status NONE",
                    k2.compare_with_oracle(
                        mutate(decoded, final_status=k2.STATUS_NONE), oracle),
                    k2.Verdict.FAIL)
        self.expect("guest status FAIL dominates",
                    k2.compare_with_oracle(
                        mutate(decoded, final_status=k2.STATUS_FAIL), oracle),
                    k2.Verdict.FAIL)
        self.expect("guest fail never upgraded",
                    k2.compare_with_oracle(
                        mutate(decoded, final_status=k2.STATUS_FAIL,
                               mismatch_count=3), oracle),
                    k2.Verdict.FAIL)
        self.expect("unknown status",
                    k2.compare_with_oracle(
                        mutate(decoded, final_status=9), oracle),
                    k2.Verdict.FAIL)
        self.expect("mismatch count",
                    k2.compare_with_oracle(
                        mutate(decoded, mismatch_count=1), oracle),
                    k2.Verdict.FAIL)
        self.expect("unexpected overflow flag",
                    k2.compare_with_oracle(
                        mutate(decoded, flags=k2.FLAG_CHECKPOINT_OVERFLOW),
                        oracle),
                    k2.Verdict.FAIL)
        self.expect("flags MBZ",
                    k2.compare_with_oracle(
                        mutate(decoded, flags=1 << 5), oracle),
                    k2.Verdict.FAIL)
        self.expect("unknown event kind",
                    k2.compare_with_oracle(
                        mutate_ckpt(decoded, 1, event_kind=99), oracle),
                    k2.Verdict.FAIL)
        # checkpoint[1]'s oracle wildcards cause, so only the content-level
        # one-hot validation (contract §3.3 w4) can catch this.
        self.expect("cause not one-hot",
                    k2.compare_with_oracle(
                        mutate_ckpt(decoded, 1,
                                    cause=CAUSE_TIMER | (CAUSE_TIMER << 1)),
                        oracle),
                    k2.Verdict.FAIL)
        self.expect("mode_cfx MBZ",
                    k2.compare_with_oracle(
                        mutate_ckpt(decoded, 1,
                                    mode_cfx=decoded.checkpoints[1].mode_cfx
                                    | (1 << 40)), oracle),
                    k2.Verdict.FAIL)
        self.expect("bad run mode",
                    k2.compare_with_oracle(
                        mutate_ckpt(decoded, 1, mode_cfx=5), oracle),
                    k2.Verdict.FAIL)
        self.expect("asid out of range",
                    k2.compare_with_oracle(
                        mutate_ckpt(decoded, 5, ptbr_asid=(64 << 48) | PTBR7),
                        oracle),
                    k2.Verdict.FAIL)
        self.expect("pc over 48-bit",
                    k2.compare_with_oracle(
                        mutate_ckpt(decoded, 2, resume_pc=1 << 48), oracle),
                    k2.Verdict.FAIL)

        # --- mutation sensitivity: every key field flips PASS -> FAIL -----
        key_mutations = {
            "mut scenario_id": mutate(decoded, scenario_id=SCENARIO ^ 1),
            "mut event_kind": mutate_ckpt(
                decoded, 1, event_kind=k2.EVENT_TIMER),
            "mut task_id": mutate_ckpt(decoded, 1, task_id=99),
            "mut run_mode": mutate_ckpt(decoded, 0, mode_cfx=0),
            "mut cfx_code": mutate_ckpt(decoded, 3, mode_cfx=MODE_SUPV),
            "mut cause": mutate_ckpt(decoded, 3, cause=CAUSE_TIMER << 1),
            "mut saved_pc": mutate_ckpt(
                decoded, 1, saved_pc=PC_MAIN + 12),
            "mut resume_pc": mutate_ckpt(
                decoded, 2, resume_pc=PC_TASK1 + 4),
            "mut context_digest": mutate_ckpt(
                decoded, 2, context_digest=CTX1 ^ 1),
            "mut memory_digest": mutate_ckpt(
                decoded, 7, memory_digest=MEM2 ^ 1),
            "mut asid": mutate_ckpt(
                decoded, 5, ptbr_asid=((ASID6) << 48) | PTBR7),
            "mut ptbr": mutate_ckpt(
                decoded, 5, ptbr_asid=(ASID7 << 48) | PTBR6),
            "mut tlb_gen": mutate_ckpt(decoded, 5, tlb_gen=2),
        }
        for name, broken in key_mutations.items():
            self.expect(name,
                        k2.compare_with_oracle(broken, oracle),
                        k2.Verdict.FAIL)

        # --- dual-backend semantics --------------------------------------
        both_wrong = k2.encode_report(
            mutate_ckpt(decoded, 2, resume_pc=PC_TASK1 + 4))
        verdict, reasons = k2.compare_dual_backend(
            both_wrong, both_wrong, oracle)
        self.check("dual agree-but-wrong", verdict == k2.Verdict.FAIL,
                   f"verdict={verdict.value}")
        self.check("dual agree-but-wrong tags both",
                   any(r.startswith("qemu:") for r in reasons)
                   and any(r.startswith("gem5:") for r in reasons))

        # Oracle wildcards tlb_gen; backends disagree on it.  Each passes
        # the oracle, so only the cross-backend comparison can catch it.
        wild = canonical_oracle()
        for expected in wild.checkpoints:
            expected.tlb_gen = None
        gem5_variant = k2.encode_report(mutate_ckpt(decoded, 5, tlb_gen=7))
        self.expect("dual oracle-pass cross-fail",
                    k2.compare_dual_backend(encoded, gem5_variant, wild),
                    k2.Verdict.FAIL)
        self.expect("dual one-side oracle fail",
                    k2.compare_dual_backend(encoded, both_wrong, oracle),
                    k2.Verdict.FAIL)

        # --- overflow handling --------------------------------------------
        full = k2.Report(
            scenario_id=SCENARIO, image_identity=IDENTITY,
            final_status=k2.STATUS_PASS, mismatch_count=0,
            flags=k2.FLAG_CHECKPOINT_OVERFLOW,
            checkpoints=[copy.deepcopy(decoded.checkpoints[i % 10])
                         for i in range(k2.MAX_CHECKPOINTS)])
        for index, ckpt in enumerate(full.checkpoints):
            ckpt.seq = index
        full_oracle = k2.ScenarioOracle(
            scenario_id=SCENARIO, image_identity=IDENTITY,
            checkpoints=[k2.ExpectedCheckpoint()
                         for _ in range(k2.MAX_CHECKPOINTS)],
            expected_flags=k2.FLAG_CHECKPOINT_OVERFLOW)
        self.expect("overflow at capacity accepted",
                    k2.compare_with_oracle(full, full_oracle),
                    k2.Verdict.PASS)
        self.expect("overflow dropped count fails",
                    k2.compare_with_oracle(full, oracle),
                    k2.Verdict.FAIL)

        # --- skip exists only at the scheduling layer ----------------------
        self.expect("dual both pre-declared skip",
                    k2.compare_dual_backend(None, None, oracle),
                    k2.Verdict.SKIP)
        self.expect("dual one skip one pass",
                    k2.compare_dual_backend(None, encoded, oracle),
                    k2.Verdict.SKIP)
        self.expect("skip never masks fail",
                    k2.compare_dual_backend(None, both_wrong, oracle),
                    k2.Verdict.FAIL)
        self.expect("skip never masks harness error",
                    k2.compare_dual_backend(None, encoded[:-1], oracle),
                    k2.Verdict.HARNESS_ERROR)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=1)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")
    for round_no in range(1, args.rounds + 1):
        suite = Suite()
        suite.run()
        if suite.failures:
            for failure in suite.failures:
                print(f"FAIL: {failure}")
            print(f"round {round_no}: {suite.count - len(suite.failures)}"
                  f"/{suite.count} checks passed")
            sys.exit(1)
        print(f"round {round_no}/{args.rounds}: "
              f"{suite.count}/{suite.count} checks passed")
    print("PASS: k2_report schema/codec/oracle/dual-backend self-test "
          "(fail-closed; no backend log consulted)")


if __name__ == "__main__":
    main()
