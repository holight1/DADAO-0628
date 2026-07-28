#!/usr/bin/env python3
"""K2 bare-metal guest report schema, codec, and oracle comparison.

Frozen by KL-140a; the normative text is
`docs/reviews/k2-baremetal-regression-contract-20260728.md`.  KL-141a..145a
reuse this module for every K2 privileged scenario and must not grow a
parallel implementation.

Wire format (all fields u64 big-endian, 8-byte aligned):

* header (9 words): magic, schema_version, scenario_id, image_identity,
  final_status, mismatch_count, checkpoint_count, flags,
  checkpoint_capacity;
* checkpoint record (11 words): seq, event_kind, task_id, mode_cfx
  (bits[7:0]=run_mode, bits[15:8]=cfx_code, bits[63:16] MBZ), cause,
  saved_pc, resume_pc, context_digest, memory_digest, ptbr_asid
  (bits[63:48]=asid, bits[47:0]=ptbr), tlb_gen.

Verdict vocabulary (contract §3.5): PASS, FAIL, SKIP, HARNESS-ERROR.  Every
non-PASS outcome is fail-closed: a clean backend exit, dual-backend
agreement, or identical logs alone never constitute PASS.  PASS strictly
requires guest final_status=PASS and mismatch_count=0 -- no oracle
configuration can upgrade a guest FAIL.  SKIP exists only at the run
    scheduling layer: a pre-declared-skipped backend does not run and produces
    no report (modeled as None bytes in compare_dual_backend); every produced
    report is always fully validated.  A dual-backend scenario with either
    backend skipped remains SKIP rather than being upgraded by the other
    backend's PASS.
"""

import enum
import hashlib
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Schema constants (contract §3.1-§3.3)

MAGIC = 0x4444414F4B325250  # ASCII "DDAOK2RP"
SCHEMA_VERSION = 1
MAX_CHECKPOINTS = 64
HEADER_WORDS = 9
CHECKPOINT_WORDS = 11
WORD_SIZE = 8
HEADER_SIZE = HEADER_WORDS * WORD_SIZE            # 72
CHECKPOINT_SIZE = CHECKPOINT_WORDS * WORD_SIZE    # 88
MAX_REPORT_SIZE = HEADER_SIZE + MAX_CHECKPOINTS * CHECKPOINT_SIZE  # 5704
BYTE_ORDER = "big"

MASK64 = (1 << 64) - 1
MASK48 = (1 << 48) - 1

# final_status (contract §3.2 w4)
STATUS_NONE = 0
STATUS_PASS = 1
STATUS_FAIL = 2
STATUS_SKIP = 3
STATUS_NAMES = {
    STATUS_NONE: "NONE",
    STATUS_PASS: "PASS",
    STATUS_FAIL: "FAIL",
    STATUS_SKIP: "SKIP",
}

# event_kind (contract §3.3 w1)
EVENT_INIT = 1
EVENT_COOP_SAVE = 2
EVENT_COOP_RESTORE = 3
EVENT_TRAP_ENTER = 4
EVENT_TRAP_RETURN = 5
EVENT_AS_SWITCH = 6
EVENT_TIMER = 7
EVENT_FINAL = 8
EVENT_KINDS = frozenset(
    (EVENT_INIT, EVENT_COOP_SAVE, EVENT_COOP_RESTORE, EVENT_TRAP_ENTER,
     EVENT_TRAP_RETURN, EVENT_AS_SWITCH, EVENT_TIMER, EVENT_FINAL))

# flags (contract §3.2 w7)
FLAG_CHECKPOINT_OVERFLOW = 1 << 0
FLAGS_KNOWN_MASK = FLAG_CHECKPOINT_OVERFLOW

# Architectural widths used by content validation.
MODE_MAX = 3     # run modes U/J/S/H
CFX_MAX = 63     # 6-bit cfxcode
ASID_MAX = 63    # 6-bit VA[47:42] set/PTBR index

# Digest algorithm (contract §3.4): word-level FNV-1a-64.
FNV1A64_OFFSET = 0xCBF29CE484222325
FNV1A64_PRIME = 0x100000001B3


def fnv1a64(words) -> int:
    """Word-level FNV-1a-64 over an iterable of u64 words (contract §3.4)."""
    h = FNV1A64_OFFSET
    for w in words:
        if w < 0 or w > MASK64:
            raise ValueError(f"digest input word out of u64 range: {w:#x}")
        h = ((h ^ w) * FNV1A64_PRIME) & MASK64
    return h


def _canonicalize(data: bytes, region: Optional[Tuple[int, int]]) -> bytes:
    if region is None:
        return bytes(data)
    offset, length = region
    if offset < 0 or length < 0 or offset + length > len(data):
        raise ValueError(
            f"canonicalization region (offset={offset}, length={length}) "
            f"outside image of {len(data)} bytes")
    return data[:offset] + b"\0" * length + data[offset + length:]


def image_identity(rom_bytes: bytes, ram_bytes: bytes, *,
                   rom_identity_slot: Optional[Tuple[int, int]] = None,
                   ram_report_area: Optional[Tuple[int, int]] = None) -> int:
    """Canonical image identity (contract §3.2 w3): SHA-256 over
    canonicalized ROM ‖ canonicalized RAM, first 8 bytes big-endian.

    Canonicalization zeroes `rom_identity_slot`=(offset, length) in the ROM
    and `ram_report_area`=(offset, length) in the RAM before hashing, so
    that embedding the identity into the slot and letting the guest write
    the report area does not change the hash.  The image generator, the
    guest-visible constant, and host verification must all use the same
    regions; this removes the self-reference of a naive whole-image hash."""
    canonical = (
        _canonicalize(rom_bytes, rom_identity_slot)
        + _canonicalize(ram_bytes, ram_report_area))
    digest = hashlib.sha256(canonical).digest()
    return struct.unpack(">Q", digest[:8])[0]


def embed_image_identity(rom_bytes: bytes, slot_offset: int,
                         identity: int) -> bytes:
    """Write identity (u64 big-endian) into the ROM image's identity slot
    and return the final ROM bytes.  The slot region must match the
    `rom_identity_slot` used when computing the identity."""
    if slot_offset < 0 or slot_offset + WORD_SIZE > len(rom_bytes):
        raise ValueError(
            f"identity slot offset {slot_offset:#x} outside ROM image of "
            f"{len(rom_bytes)} bytes")
    _check_u64("identity", identity)
    out = bytearray(rom_bytes)
    struct.pack_into(">Q", out, slot_offset, identity)
    return bytes(out)


def scenario_id_for(task_tag: str) -> int:
    """Contract §3.2 w2 scenario_id for a six-byte, hyphen-free K2 task tag
    such as ``KL141a``."""
    try:
        raw = task_tag.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(
            f"task tag must be six ASCII bytes KLnnna: {task_tag!r}") from exc
    if (len(raw) != 6 or raw[:2] != b"KL" or not raw[2:5].isdigit()
            or not (ord("a") <= raw[5] <= ord("z"))):
        raise ValueError(
            f"task tag must be six ASCII bytes KLnnna: {task_tag!r}")
    return struct.unpack(">Q", raw.ljust(WORD_SIZE, b"\0"))[0]


class Verdict(enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    HARNESS_ERROR = "HARNESS-ERROR"


class ReportStructureError(Exception):
    """The byte stream is not a trustworthy K2 report (-> HARNESS-ERROR)."""


# ---------------------------------------------------------------------------
# Data model

@dataclass
class Checkpoint:
    """One checkpoint record, raw wire fields (contract §3.3)."""
    seq: int
    event_kind: int
    task_id: int
    mode_cfx: int
    cause: int
    saved_pc: int
    resume_pc: int
    context_digest: int
    memory_digest: int
    ptbr_asid: int
    tlb_gen: int

    @property
    def run_mode(self) -> int:
        return self.mode_cfx & 0xFF

    @property
    def cfx_code(self) -> int:
        return (self.mode_cfx >> 8) & 0xFF

    @property
    def mode_cfx_mbz(self) -> int:
        return self.mode_cfx >> 16

    @property
    def asid(self) -> int:
        return self.ptbr_asid >> 48

    @property
    def ptbr(self) -> int:
        return self.ptbr_asid & MASK48

    def words(self) -> Tuple[int, ...]:
        return (
            self.seq, self.event_kind, self.task_id, self.mode_cfx,
            self.cause, self.saved_pc, self.resume_pc, self.context_digest,
            self.memory_digest, self.ptbr_asid, self.tlb_gen)


def build_checkpoint(seq, event_kind, task_id, run_mode, cfx_code, cause,
                     saved_pc, resume_pc, context_digest, memory_digest,
                     asid, ptbr, tlb_gen) -> Checkpoint:
    """Checkpoint constructor from unpacked fields, with range checks."""
    for name, value, limit in (
            ("run_mode", run_mode, 0xFF), ("cfx_code", cfx_code, 0xFF),
            ("asid", asid, 0xFFFF), ("ptbr", ptbr, MASK48)):
        if value < 0 or value > limit:
            raise ValueError(f"{name} out of range: {value:#x}")
    return Checkpoint(
        seq=seq, event_kind=event_kind, task_id=task_id,
        mode_cfx=run_mode | (cfx_code << 8), cause=cause,
        saved_pc=saved_pc, resume_pc=resume_pc,
        context_digest=context_digest, memory_digest=memory_digest,
        ptbr_asid=(asid << 48) | ptbr, tlb_gen=tlb_gen)


@dataclass
class Report:
    scenario_id: int
    image_identity: int
    final_status: int
    mismatch_count: int
    flags: int
    checkpoints: List[Checkpoint] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Encode / decode

def _check_u64(name: str, value: int) -> None:
    if value < 0 or value > MASK64:
        raise ValueError(f"{name} out of u64 range: {value:#x}")


def encode_report(report: Report) -> bytes:
    """Encode a report.  Enforces u64 ranges and capacity only; semantic
    validation lives in decode_report/validate_content so that negative
    test vectors can also be constructed with this encoder."""
    if len(report.checkpoints) > MAX_CHECKPOINTS:
        raise ValueError(
            f"checkpoint count {len(report.checkpoints)} exceeds "
            f"capacity {MAX_CHECKPOINTS}")
    header = (
        MAGIC, report.schema_version, report.scenario_id,
        report.image_identity, report.final_status, report.mismatch_count,
        len(report.checkpoints), report.flags, MAX_CHECKPOINTS)
    for name, value in zip(
            ("magic", "schema_version", "scenario_id", "image_identity",
             "final_status", "mismatch_count", "checkpoint_count", "flags",
             "checkpoint_capacity"), header):
        _check_u64(name, value)
    out = bytearray(struct.pack(">9Q", *header))
    for ckpt in report.checkpoints:
        for value in ckpt.words():
            _check_u64("checkpoint field", value)
        out.extend(struct.pack(">11Q", *ckpt.words()))
    return bytes(out)


def decode_report(data: bytes) -> Report:
    """Decode a report.  Structural problems raise ReportStructureError,
    which callers map to Verdict.HARNESS_ERROR (contract §3.5)."""
    if len(data) < HEADER_SIZE:
        raise ReportStructureError(
            f"truncated header: {len(data)} bytes < {HEADER_SIZE}")
    (magic, version, scenario_id, identity, status, mismatches, count,
     flags, capacity) = struct.unpack(">9Q", data[:HEADER_SIZE])
    if magic != MAGIC:
        raise ReportStructureError(f"bad magic: {magic:#018x}")
    if version != SCHEMA_VERSION:
        raise ReportStructureError(f"bad schema version: {version}")
    if capacity != MAX_CHECKPOINTS:
        raise ReportStructureError(
            f"bad checkpoint capacity: {capacity} != {MAX_CHECKPOINTS}")
    if count > MAX_CHECKPOINTS:
        raise ReportStructureError(
            f"checkpoint count {count} exceeds capacity {MAX_CHECKPOINTS}")
    expected = HEADER_SIZE + count * CHECKPOINT_SIZE
    if len(data) != expected:
        relation = "truncated" if len(data) < expected else "trailing bytes"
        raise ReportStructureError(
            f"{relation}: {len(data)} bytes != header+{count} records "
            f"({expected})")
    checkpoints = []
    offset = HEADER_SIZE
    for _ in range(count):
        checkpoints.append(Checkpoint(*struct.unpack(
            ">11Q", data[offset:offset + CHECKPOINT_SIZE])))
        offset += CHECKPOINT_SIZE
    return Report(
        scenario_id=scenario_id, image_identity=identity,
        final_status=status, mismatch_count=mismatches, flags=flags,
        checkpoints=checkpoints, schema_version=version)


# ---------------------------------------------------------------------------
# Content validation (problems map to Verdict.FAIL)

def validate_sequence(report: Report) -> List[str]:
    """seq must be exactly 0..count-1, contiguous and ordered (§3.3 w0)."""
    problems = []
    for index, ckpt in enumerate(report.checkpoints):
        if ckpt.seq != index:
            problems.append(
                f"checkpoint[{index}].seq={ckpt.seq}, expected {index}")
    return problems


def validate_content(report: Report) -> List[str]:
    """Semantic legality of a structurally decoded report (§3.2/§3.3)."""
    problems = []
    if report.schema_version != SCHEMA_VERSION:
        problems.append(f"schema_version={report.schema_version}")
    if report.final_status not in STATUS_NAMES:
        problems.append(f"unknown final_status={report.final_status}")
    if report.flags & ~FLAGS_KNOWN_MASK:
        problems.append(f"flags MBZ bits set: {report.flags:#x}")
    for index, ckpt in enumerate(report.checkpoints):
        if ckpt.event_kind not in EVENT_KINDS:
            problems.append(
                f"checkpoint[{index}] unknown event_kind={ckpt.event_kind}")
        if ckpt.cause and (ckpt.cause & (ckpt.cause - 1)):
            problems.append(
                f"checkpoint[{index}] cause={ckpt.cause:#x} not one-hot")
        if ckpt.mode_cfx_mbz:
            problems.append(
                f"checkpoint[{index}] mode_cfx MBZ bits set: "
                f"{ckpt.mode_cfx:#x}")
        if ckpt.run_mode > MODE_MAX:
            problems.append(
                f"checkpoint[{index}] run_mode={ckpt.run_mode} > {MODE_MAX}")
        if ckpt.cfx_code > CFX_MAX:
            problems.append(
                f"checkpoint[{index}] cfx_code={ckpt.cfx_code} > {CFX_MAX}")
        if ckpt.asid > ASID_MAX:
            problems.append(
                f"checkpoint[{index}] asid={ckpt.asid} > {ASID_MAX}")
        if ckpt.saved_pc > MASK48:
            problems.append(
                f"checkpoint[{index}] saved_pc={ckpt.saved_pc:#x} > 48-bit")
        if ckpt.resume_pc > MASK48:
            problems.append(
                f"checkpoint[{index}] resume_pc={ckpt.resume_pc:#x} > 48-bit")
    return problems


# ---------------------------------------------------------------------------
# Oracle comparison

@dataclass
class ExpectedCheckpoint:
    """Independent host-side expectation; None fields are wildcards."""
    event_kind: Optional[int] = None
    task_id: Optional[int] = None
    run_mode: Optional[int] = None
    cfx_code: Optional[int] = None
    cause: Optional[int] = None
    saved_pc: Optional[int] = None
    resume_pc: Optional[int] = None
    context_digest: Optional[int] = None
    memory_digest: Optional[int] = None
    asid: Optional[int] = None
    ptbr: Optional[int] = None
    tlb_gen: Optional[int] = None


@dataclass
class ScenarioOracle:
    """Independent scenario expectation (contract §4 step 3).

    There is deliberately no expected_status/expected_mismatch_count knob:
    PASS strictly requires guest final_status=PASS and mismatch_count=0
    (contract §3.5), so a guest FAIL can never be upgraded by oracle
    configuration.  There is also no skip knob: SKIP exists only at the run
    scheduling layer -- a pre-declared-skipped backend does not run and
    produces no report (None bytes in compare_dual_backend); every produced
    report is always fully validated (§3.5)."""
    scenario_id: int
    image_identity: Optional[int]
    checkpoints: List[ExpectedCheckpoint] = field(default_factory=list)
    expected_flags: int = 0


_ORACLE_FIELDS = (
    "event_kind", "task_id", "run_mode", "cfx_code", "cause", "saved_pc",
    "resume_pc", "context_digest", "memory_digest", "asid", "ptbr",
    "tlb_gen")


def compare_with_oracle(report: Report,
                        oracle: ScenarioOracle) -> Tuple[Verdict, List[str]]:
    """Compare one decoded report against the independent oracle (§4.3).

    PASS requires guest final_status=PASS and mismatch_count=0 as hard
    conditions (contract §3.5); no oracle configuration upgrades a guest
    FAIL.  This function never returns SKIP -- skip is a scheduling-layer
    decision made before a backend runs, not a property of a produced
    report."""
    reasons = []
    if report.scenario_id != oracle.scenario_id:
        reasons.append(
            f"scenario_id={report.scenario_id:#x} != oracle "
            f"{oracle.scenario_id:#x}")
    if oracle.image_identity is not None and (
            report.image_identity != oracle.image_identity):
        reasons.append(
            f"image_identity={report.image_identity:#018x} != run image "
            f"{oracle.image_identity:#018x}")
        return Verdict.HARNESS_ERROR, reasons
    reasons.extend(validate_content(report))
    reasons.extend(validate_sequence(report))
    if report.final_status == STATUS_NONE:
        reasons.append("guest never finalized: final_status=NONE")
    elif report.final_status != STATUS_PASS:
        reasons.append(
            f"final_status={STATUS_NAMES.get(report.final_status)} != PASS "
            f"(contract §3.5 hard condition, no upgrade)")
    if report.mismatch_count != 0:
        reasons.append(
            f"mismatch_count={report.mismatch_count} != 0 "
            f"(contract §3.5 hard condition, no upgrade)")
    if report.flags != oracle.expected_flags:
        reasons.append(
            f"flags={report.flags:#x} != expected {oracle.expected_flags:#x}")
    if len(report.checkpoints) != len(oracle.checkpoints):
        reasons.append(
            f"checkpoint count={len(report.checkpoints)} != oracle "
            f"{len(oracle.checkpoints)}")
    for index, (ckpt, expected) in enumerate(
            zip(report.checkpoints, oracle.checkpoints)):
        for name in _ORACLE_FIELDS:
            want = getattr(expected, name)
            if want is None:
                continue
            got = getattr(ckpt, name)
            if got != want:
                reasons.append(
                    f"checkpoint[{index}].{name}={got:#x} != oracle {want:#x}")
    if reasons:
        return Verdict.FAIL, reasons
    return Verdict.PASS, []


def evaluate_report_bytes(data: bytes,
                          oracle: ScenarioOracle) -> Tuple[Verdict, List[str]]:
    """Decode then compare; structural problems are HARNESS-ERROR."""
    try:
        report = decode_report(data)
    except ReportStructureError as exc:
        return Verdict.HARNESS_ERROR, [str(exc)]
    return compare_with_oracle(report, oracle)


# ---------------------------------------------------------------------------
# Dual-backend comparison (contract §4 step 4)

_CHECKPOINT_COMPARE_FIELDS = (
    "seq", "event_kind", "task_id", "mode_cfx", "cause", "saved_pc",
    "resume_pc", "context_digest", "memory_digest", "ptbr_asid", "tlb_gen")

_HEADER_COMPARE_FIELDS = (
    "schema_version", "scenario_id", "image_identity", "final_status",
    "mismatch_count", "flags")


def compare_backend_reports(first: Report,
                            second: Report) -> Tuple[Verdict, List[str]]:
    """Normalized field-by-field dual-backend comparison.  The frozen schema
    has no legitimately backend-specific field, so every field must match."""
    diffs = []
    for name in _HEADER_COMPARE_FIELDS:
        if getattr(first, name) != getattr(second, name):
            diffs.append(
                f"header.{name}: {getattr(first, name)!r} != "
                f"{getattr(second, name)!r}")
    if len(first.checkpoints) != len(second.checkpoints):
        diffs.append(
            f"checkpoint count: {len(first.checkpoints)} != "
            f"{len(second.checkpoints)}")
    for index, (ckpt_a, ckpt_b) in enumerate(
            zip(first.checkpoints, second.checkpoints)):
        for name in _CHECKPOINT_COMPARE_FIELDS:
            if getattr(ckpt_a, name) != getattr(ckpt_b, name):
                diffs.append(
                    f"checkpoint[{index}].{name}: {getattr(ckpt_a, name):#x}"
                    f" != {getattr(ckpt_b, name):#x}")
    if diffs:
        return Verdict.FAIL, diffs
    return Verdict.PASS, []


def compare_dual_backend(qemu_bytes: Optional[bytes],
                         gem5_bytes: Optional[bytes],
                         oracle: ScenarioOracle,
                         backends=("qemu", "gem5")) -> Tuple[Verdict, List[str]]:
    """Full contract §4.4 flow: each backend's report is compared with the
    independent oracle first; only if both pass are the normalized reports
    compared with each other.  Backend agreement can never rescue an oracle
    violation, and oracle agreement can never rescue a backend mismatch.

    Each *_bytes argument is the raw report bytes, or None when that
    backend was pre-declared skipped at the scheduling layer (it did not
    run and produced no report, contract §3.5).  Every produced report is
    fully validated, so a skip on one side can never mask a failure
    observed on the other.  A K2 dual-backend scenario is complete only when
    both backends ran and passed; if either backend was pre-declared skipped,
    the scenario remains SKIP.  Verdict precedence:
    HARNESS-ERROR > FAIL > SKIP > PASS."""
    verdicts = {}
    reports = {}
    reasons = []
    for name, data in zip(backends, (qemu_bytes, gem5_bytes)):
        if data is None:
            verdicts[name] = Verdict.SKIP
            reasons.append(
                f"{name}: pre-declared skip (not run, no report produced)")
            continue
        try:
            report = decode_report(data)
        except ReportStructureError as exc:
            verdicts[name] = Verdict.HARNESS_ERROR
            reasons.append(f"{name}: HARNESS-ERROR: {exc}")
            continue
        reports[name] = report
        verdict, found = compare_with_oracle(report, oracle)
        verdicts[name] = verdict
        reasons.extend(f"{name}: {item}" for item in found)
    if any(v == Verdict.HARNESS_ERROR for v in verdicts.values()):
        return Verdict.HARNESS_ERROR, reasons
    if any(v == Verdict.FAIL for v in verdicts.values()):
        return Verdict.FAIL, reasons
    ran = [name for name in backends if name in reports]
    if len(ran) == 2:
        verdict, diffs = compare_backend_reports(
            reports[ran[0]], reports[ran[1]])
        if diffs:
            reasons.extend(
                "backends agree with oracle but differ from each other: "
                + item for item in diffs)
        return verdict, reasons
    if ran:
        # Exactly one backend ran and passed its oracle comparison.  This is
        # useful partial evidence, but it cannot satisfy the frozen
        # dual-backend K2 gate because no cross-backend comparison exists.
        return Verdict.SKIP, reasons
    return Verdict.SKIP, reasons
