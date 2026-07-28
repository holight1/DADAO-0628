#!/usr/bin/env python3
"""KL-137a dual-backend probes for the test-machine-only K1_EXT0 level source.

K1_EXT0 is not a UART device.  It is backend test infrastructure whose level
is asserted/deasserted at configured retired-instruction boundaries and routed
through the frozen architectural carrier:

  cfx_uart source0 private pending (cg8/rc0 bit0)
      -> cfx_uart common UART0 pending (cg4/rc7 bit32)
      -> KL-131a mask/priority/async-entry machinery.

Every result is guest-self-checked.  A successful backend process exit is not
accepted unless its architectural halt code equals the scenario's pass code;
gem5 additionally must print exactly one matching SIM_END record.

Scenarios:
  lifecycle -- cfx_uart exist/reset, masked assertion, private/common pending,
               premature W0C re-latch while asserted, precise delivery
               boundary/cause fields, deassert-without-clear, and required
               private-then-common acknowledgement.
  priority  -- TIMER and K1_EXT0 are simultaneously pending when one shared
               global-mask write makes both eligible; cfx_timer(18) must enter
               before cfx_uart(62), proven by the two saved cause_ip values.
"""

import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_kl131a_async_dispatch_probes as k131  # noqa: E402
import run_kl133a_cfx_timer_probes as k133  # noqa: E402
from build_test_binary import load_reg, UNIMP_ENCODING  # noqa: E402

REPO = k131.REPO
QEMU = k131.QEMU
GEM5 = k131.GEM5
GEM5_FS_CFG = k131.GEM5_FS_CFG
EVIDENCE = os.path.join(REPO, ".work", "evidence", "kl137a-probes")

ROM_BASE = k131.ROM_BASE
SUPV_ENTRY_OFFSET = k131.SUPV_ENTRY_OFFSET
BOOT_INSN_COUNT = k133.BOOT_INSN_COUNT
MASK_ALL = k131.MASK_ALL
MODE_SUPV = k131.MODE_SUPV

CFX_PTW = k131.CFX_PTW
CFX_TIMER = k131.CFX_TIMER
CFX_UART = k131.CFX_UART
CFX_POWER = k131.CFX_POWER

CG_COMMON = k131.CG_COMMON
RC_PENDING = k131.RC_PENDING
RC_EXCP_ASYNC_NUM = k131.RC_EXCP_ASYNC_NUM
CG_FRAME = k131.CG_FRAME
RC_FRAME_CAUSE_ID = k131.RC_FRAME_CAUSE_ID
RC_FRAME_CAUSE_IP = k131.RC_FRAME_CAUSE_IP
RC_FRAME_CAUSE_INFO = k131.RC_FRAME_CAUSE_INFO
RC_EXCP_CAUSE_MASK = k131.RC_EXCP_CAUSE_MASK

CG_UART = 8
RC_UART_PENDING = 0
RC_UART_EXIST = 1
CAUSE_UART0 = 1 << 32

CG_TIMER = k133.CG_TIMER
RC_TIMER_PENDING = k133.RC_TIMER_PENDING
RC_TIMER_MASK = k133.RC_TIMER_MASK
RC_TIMER_CTRL = k133.RC_TIMER_CTRL
RC_TIMER_REG0 = k133.RC_TIMER_REG0
CAUSE_TIMER = k133.CAUSE_TIMER
TIMER_CTRL_ENABLE = k133.TIMER_CTRL_ENABLE

OP_CFX2RC = k131.OP_CFX2RC
OP_ESCAPE = k131.OP_ESCAPE

TRAMP_OFFSET = 0x1000
TRAMP_SLOT = 0x40
ALLONES_REG = 10

PASS_LIFECYCLE = 137
FAIL_LIFECYCLE = 0xA1
PASS_PRIORITY = 138
FAIL_PRIORITY = 0xA2


def ticks_before_next(out):
    """Retired count before the next straight-line instruction.

    The only non-executed bytes before supv_entry are the boot-stub padding.
    Callers use this only before their first interrupt detour.
    """
    assert len(out) >= SUPV_ENTRY_OFFSET
    assert (len(out) - SUPV_ENTRY_OFFSET) % 4 == 0
    return BOOT_INSN_COUNT + (len(out) - SUPV_ENTRY_OFFSET) // 4


def filler(out):
    k131.write_orrr(out, k131.MISC_ORR, 3, 3, 3)


def write_uart_private(out, value_reg):
    k131.write_crrr(
        out, OP_CFX2RC, CFX_UART, CG_UART, RC_UART_PENDING, value_reg)


def read_uart_check(out, rc, expected):
    k131.read_reg_check(out, CFX_UART, CG_UART, rc, expected)


def begin_probe():
    out = bytearray()
    k131.emit_boot_stub(out, ROM_BASE + SUPV_ENTRY_OFFSET)
    load_reg(out, "rd", 29, 0)
    return out


def pad_to(out, offset):
    if len(out) > offset:
        raise ValueError(f"main body overflow: {len(out):#x} > {offset:#x}")
    while len(out) < offset:
        out.extend(struct.pack(">I", UNIMP_ENCODING))


def gen_lifecycle():
    out = begin_probe()
    tramp_uart = ROM_BASE + TRAMP_OFFSET

    # Architectural register pair: reset-zero private pending and exist=1.
    read_uart_check(out, RC_UART_PENDING, 0)
    read_uart_check(out, RC_UART_EXIST, 1)
    # exist is RO.
    k131.write_crrr(out, OP_CFX2RC, CFX_UART, CG_UART, RC_UART_EXIST, 0)
    read_uart_check(out, RC_UART_EXIST, 1)

    # Keep the source blocked while observing latches and exercising W0C.
    k131.set_vector(out, CFX_UART, tramp_uart)
    k131.set_excp_cause_mask(out, CFX_UART, MODE_SUPV, MASK_ALL)
    k131.set_global_mask(out, MODE_SUPV, MASK_ALL)
    k131.set_escape_mask(
        out, CFX_POWER, MODE_SUPV, MASK_ALL & ~(1 << CFX_PTW))
    k131.craft_inner_cfx_mask(
        out, CFX_PTW, MASK_ALL & ~(1 << CFX_UART))
    load_reg(out, "rd", ALLONES_REG, MASK_ALL)

    assert_at = ticks_before_next(out) + 2
    filler(out)
    filler(out)
    assert ticks_before_next(out) == assert_at

    # Assertion is level-driven and independent of masks.
    read_uart_check(out, RC_UART_PENDING, 1)
    k131.read_reg_check(out, CFX_UART, CG_COMMON, RC_PENDING, CAUSE_UART0)

    # Premature ACK while the electrical source remains asserted: each
    # following boundary must restore both the private and common latches.
    write_uart_private(out, 0)
    k131.write_crrr(out, OP_CFX2RC, CFX_UART, CG_COMMON, RC_PENDING, 0)
    read_uart_check(out, RC_UART_PENDING, 1)
    k131.read_reg_check(out, CFX_UART, CG_COMMON, RC_PENDING, CAUSE_UART0)

    # Cause-mask opens first; the shared global mask is the final gate.  Its
    # retirement boundary must deliver before the poison instruction.
    k131.set_excp_cause_mask(
        out, CFX_UART, MODE_SUPV, MASK_ALL & ~CAUSE_UART0)
    mark = ROM_BASE + len(out) + 5 * 4  # load_reg + global-mask cfx2rc
    k131.set_global_mask(
        out, MODE_SUPV, MASK_ALL & ~(1 << CFX_UART))
    assert ROM_BASE + len(out) == mark
    delivery_tick = ticks_before_next(out)
    out.extend(struct.pack(">I", UNIMP_ENCODING))

    # The two-instruction handler masks self first, then escape,1 skips the
    # poison. Deassert exactly at the boundary after escape: neither latch
    # may clear merely because the electrical level dropped.
    deassert_at = delivery_tick + 2
    k131.read_reg_check(
        out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_UART0)
    k131.read_reg_check(out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_INFO, 0)
    k131.read_reg_check(out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_IP, mark)
    k131.read_reg_check(out, CFX_UART, CG_COMMON, RC_EXCP_ASYNC_NUM, 1)
    read_uart_check(out, RC_UART_PENDING, 1)
    k131.read_reg_check(out, CFX_UART, CG_COMMON, RC_PENDING, CAUSE_UART0)

    # Required order after deassert: private source latch first, then common
    # cause latch.  With the level gone, both must remain clear.
    write_uart_private(out, 0)
    k131.write_crrr(out, OP_CFX2RC, CFX_UART, CG_COMMON, RC_PENDING, 0)
    read_uart_check(out, RC_UART_PENDING, 0)
    k131.read_reg_check(out, CFX_UART, CG_COMMON, RC_PENDING, 0)
    k131.emit_final_halt(out, PASS_LIFECYCLE, FAIL_LIFECYCLE)

    pad_to(out, TRAMP_OFFSET)
    # First instruction must mask this self-target cause before another
    # boundary can redeliver the still-asserted level.
    k131.write_crrr(
        out, OP_CFX2RC, CFX_UART, MODE_SUPV,
        RC_EXCP_CAUSE_MASK, ALLONES_REG)
    k131.write_ciii(out, OP_ESCAPE, CFX_UART, 1)
    return bytes(out), assert_at, deassert_at


def gen_priority():
    out = begin_probe()
    tramp_timer = ROM_BASE + TRAMP_OFFSET
    tramp_uart = tramp_timer + TRAMP_SLOT

    k131.set_vector(out, CFX_TIMER, tramp_timer)
    k131.set_vector(out, CFX_UART, tramp_uart)
    # Cause masks are open, but shared global and inner routing masks retain
    # both causes until one final shared-mask write.
    k131.set_excp_cause_mask(
        out, CFX_TIMER, MODE_SUPV, MASK_ALL & ~CAUSE_TIMER)
    k131.set_excp_cause_mask(
        out, CFX_UART, MODE_SUPV, MASK_ALL & ~CAUSE_UART0)
    k131.set_global_mask(out, MODE_SUPV, MASK_ALL)
    k131.set_escape_mask(
        out, CFX_POWER, MODE_SUPV, MASK_ALL & ~(1 << CFX_PTW))
    k131.craft_inner_cfx_mask(
        out, CFX_PTW,
        MASK_ALL & ~(1 << CFX_TIMER) & ~(1 << CFX_UART))

    # Arm one-shot timer0; subsequent setup instructions ensure it has
    # expired while global routing remains blocked. K1_EXT0 is asserted from
    # cycle zero by this scenario's backend schedule.
    k133.set_timer_mask(out, 0)
    k133.set_timer_counter0(out, 1)
    k133.set_timer_ctrl(out, TIMER_CTRL_ENABLE)
    load_reg(out, "rd", ALLONES_REG, MASK_ALL)
    k131.read_reg_check(out, CFX_TIMER, CG_COMMON, RC_PENDING, CAUSE_TIMER)
    k131.read_reg_check(out, CFX_UART, CG_COMMON, RC_PENDING, CAUSE_UART0)
    read_uart_check(out, RC_UART_PENDING, 1)

    mark_timer = ROM_BASE + len(out) + 5 * 4
    mark_uart = mark_timer + 4
    k131.set_global_mask(
        out, MODE_SUPV,
        MASK_ALL & ~(1 << CFX_TIMER) & ~(1 << CFX_UART))
    assert ROM_BASE + len(out) == mark_timer
    out.extend(struct.pack(">I", UNIMP_ENCODING))
    out.extend(struct.pack(">I", UNIMP_ENCODING))

    # cfx18 must win lexicographically over cfx62. The timer handler skips
    # the first poison; UART must then save the second poison's PC.
    k131.read_reg_check(
        out, CFX_TIMER, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_TIMER)
    k131.read_reg_check(
        out, CFX_TIMER, CG_FRAME, RC_FRAME_CAUSE_IP, mark_timer)
    k131.read_reg_check(
        out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_ID, CAUSE_UART0)
    k131.read_reg_check(
        out, CFX_UART, CG_FRAME, RC_FRAME_CAUSE_IP, mark_uart)
    k131.read_reg_check(out, CFX_TIMER, CG_COMMON, RC_EXCP_ASYNC_NUM, 1)
    k131.read_reg_check(out, CFX_UART, CG_COMMON, RC_EXCP_ASYNC_NUM, 1)
    k131.emit_final_halt(out, PASS_PRIORITY, FAIL_PRIORITY)

    pad_to(out, TRAMP_OFFSET)
    # TIMER: mask self, drain private then common, skip poison A.
    k131.write_crrr(
        out, OP_CFX2RC, CFX_TIMER, MODE_SUPV,
        RC_EXCP_CAUSE_MASK, ALLONES_REG)
    k131.write_crrr(
        out, OP_CFX2RC, CFX_TIMER, CG_TIMER, RC_TIMER_PENDING, 0)
    k131.write_crrr(
        out, OP_CFX2RC, CFX_TIMER, CG_COMMON, RC_PENDING, 0)
    k131.write_ciii(out, OP_ESCAPE, CFX_TIMER, 1)
    pad_to(out, TRAMP_OFFSET + TRAMP_SLOT)
    # UART: mask self before the still-asserted source can redeliver, then
    # skip poison B. No ACK is needed before terminal halt in this scenario.
    k131.write_crrr(
        out, OP_CFX2RC, CFX_UART, MODE_SUPV,
        RC_EXCP_CAUSE_MASK, ALLONES_REG)
    k131.write_ciii(out, OP_ESCAPE, CFX_UART, 1)
    return bytes(out)


def run_qemu(name, raw, assert_at, deassert_at):
    os.makedirs(EVIDENCE, exist_ok=True)
    path = os.path.join(EVIDENCE, name + "-qemu.bin")
    with open(path, "wb") as stream:
        stream.write(raw)
    command = [
        QEMU, "-M", "dadao-m1",
        "-global", "dadao-cpu.k1-ext0-test-enable=on",
        "-global", f"dadao-cpu.k1-ext0-assert-retired={assert_at}",
        "-global", f"dadao-cpu.k1-ext0-deassert-retired={deassert_at}",
        "-bios", path, "-display", "none", "-serial", "none", "-d", "int",
    ]
    result = subprocess.run(
        command, capture_output=True, timeout=60, text=True)
    with open(os.path.join(EVIDENCE, name + "-qemu.log"), "w") as stream:
        stream.write("=== command ===\n" + " ".join(command))
        stream.write("\n=== stdout ===\n" + result.stdout)
        stream.write("\n=== stderr ===\n" + result.stderr)
    return result


def run_gem5(name, raw, assert_at, deassert_at):
    os.makedirs(EVIDENCE, exist_ok=True)
    path = os.path.join(EVIDENCE, name + "-gem5.bin")
    with open(path, "wb") as stream:
        stream.write(raw)
    outdir = tempfile.mkdtemp(prefix="gem5_kl137a_")
    command = [
        GEM5, "--outdir=" + outdir, GEM5_FS_CFG, path,
        "--k1-ext0-schedule", str(assert_at), str(deassert_at),
    ]
    result = subprocess.run(
        command, capture_output=True, timeout=120, text=True)
    with open(os.path.join(EVIDENCE, name + "-gem5.log"), "w") as stream:
        stream.write("=== command ===\n" + " ".join(command))
        stream.write("\n=== stdout ===\n" + result.stdout)
        stream.write("\n=== stderr ===\n" + result.stderr)
    return result


def require(name, qemu, gem5, expected):
    assert qemu.returncode == expected, (
        f"QEMU {name}: rc={qemu.returncode}, expected={expected}\n"
        f"{qemu.stderr[-5000:]}")
    assert gem5.returncode == expected, (
        f"gem5 {name}: rc={gem5.returncode}, expected={expected}\n"
        f"{gem5.stdout[-3000:]}\n{gem5.stderr[-3000:]}")
    assert k131.gem5_code(gem5.stdout) == expected, gem5.stdout[-3000:]


def main():
    lifecycle, assert_at, deassert_at = gen_lifecycle()
    priority = gen_priority()
    q_life = run_qemu("lifecycle", lifecycle, assert_at, deassert_at)
    g_life = run_gem5("lifecycle", lifecycle, assert_at, deassert_at)
    require("lifecycle", q_life, g_life, PASS_LIFECYCLE)

    q_prio = run_qemu("priority", priority, 0, MASK_ALL)
    g_prio = run_gem5("priority", priority, 0, MASK_ALL)
    require("priority", q_prio, g_prio, PASS_PRIORITY)
    print(
        "PASS: lifecycle(assert/mask/relatch/deliver/deassert/ack)="
        f"{PASS_LIFECYCLE}/{PASS_LIFECYCLE}; "
        "priority(timer-cfx18-before-ext0-cfx62)="
        f"{PASS_PRIORITY}/{PASS_PRIORITY}")


if __name__ == "__main__":
    main()
