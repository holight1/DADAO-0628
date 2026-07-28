#!/usr/bin/env python3
"""KL-129b dual-backend TLB invalidation and fault-LRU probes.

Every scenario decides success inside the guest before halting.  Backend logs
are supporting evidence only; matching QEMU/gem5 exit codes are not treated as
an architectural oracle.
"""

import os

import run_kl129a_tlb_probes as base


EVIDENCE = os.path.join(base.REPO, ".work", "evidence",
                        "kl129b-tlb-review-fixes")
base.EVIDENCE = EVIDENCE

NEXT_SET = base.SET + 1
EDGE_L1_INDEX = 0x1FFF
EDGE_L2_INDEX = 0x1FFF
EDGE_L2_BASE = 0x80030000
NEXT_L1_BASE = 0x80040000
NEXT_L2_BASE = 0x80050000
FAULT_MARKER = 0x129BFA0170C4ED01


def normal_va_at(set_index, l1_index, l2_index, fragment=3, offset=0x100):
    return (set_index << 42) | (l1_index << 29) | (l2_index << 16) | \
        (fragment << 13) | offset


def populate_two_cached_pages(image, out):
    entries = []
    for index, old_pa, new_pa in (
            (13, 0x80100000, 0x80120000),
            (14, 0x80110000, 0x80130000)):
        va = base.normal_va(index)
        pte_addr = base.L2_BASE + index * 8
        old_value = 0x129B100000000000 | index
        new_value = 0x129B200000000000 | index
        base.put_qword(
            image, pte_addr,
            base.normal_pte(old_pa, [3], base.PERM_R))
        base.put_qword(image, old_pa + (va & 0xFFFF), old_value)
        base.put_qword(image, new_pa + (va & 0xFFFF), new_value)
        entries.append((va, pte_addr, new_pa, old_value, new_value))
        base.read_va(out, va)
        base.emit_value_check(out, 3, old_value)
    for _, pte_addr, new_pa, _, _ in entries:
        base.write_pte(
            out, pte_addr,
            base.normal_pte(new_pa, [3], base.PERM_R))
    return entries


def gen_low16_alignment_probe():
    image = base.base_image()
    out = bytearray()
    base.setup(out)
    entries = populate_two_cached_pages(image, out)

    page13_start = entries[0][0] & ~0xFFFF
    base.cfx_write(
        out, base.CFX_TLB, base.TLB_CONTROL_CG,
        base.TLB_ADDR_START_RC, page13_start + 0xF000)
    base.cfx_write(
        out, base.CFX_TLB, base.TLB_CONTROL_CG,
        base.TLB_ADDR_SIZE_RC, 0x2000)
    base.cfx_write(
        out, base.CFX_TLB, base.TLB_CONTROL_CG,
        base.TLB_CONTROL_RC, 2)

    # addr_start[15:0] is ignored: [page13,page13+0x2000) intersects only
    # page13, rather than the buggy unaligned interval crossing into page14.
    base.read_va(out, entries[0][0])
    base.emit_value_check(out, 3, entries[0][4])
    base.read_va(out, entries[1][0])
    base.emit_value_check(out, 3, entries[1][3])
    base.emit_result(out)
    return bytes(out), bytes(image)


def gen_zero_size_probe():
    image = base.base_image()
    out = bytearray()
    base.setup(out)
    entries = populate_two_cached_pages(image, out)

    base.cfx_write(
        out, base.CFX_TLB, base.TLB_CONTROL_CG,
        base.TLB_ADDR_START_RC, entries[0][0] & ~0xFFFF)
    base.cfx_write(
        out, base.CFX_TLB, base.TLB_CONTROL_CG,
        base.TLB_ADDR_SIZE_RC, 0)
    base.cfx_write(
        out, base.CFX_TLB, base.TLB_CONTROL_CG,
        base.TLB_CONTROL_RC, 2)

    # A zero-sized range is a no-op, so both stale cached translations remain.
    for entry in entries:
        base.read_va(out, entry[0])
        base.emit_value_check(out, 3, entry[3])
    base.emit_result(out)
    return bytes(out), bytes(image)


def gen_set_end_clamp_probe():
    image = base.base_image()
    out = bytearray()
    base.setup(out)
    base.cfx_write(
        out, base.CFX_PTW, base.PTW_PTBR_CG, NEXT_SET,
        NEXT_L1_BASE >> 16)
    base.cfx_write(out, base.CFX_PTW, base.PTW_PTHI_CG, NEXT_SET, 0)
    base.cfx_write(out, base.CFX_PTW, base.PTW_PAHI_CG, NEXT_SET, 0)
    base.cfx_write(
        out, base.CFX_PTW, base.PTW_PERM_CG, base.PTW_ENABLE_RC,
        (1 << base.SET) | (1 << NEXT_SET))

    edge_va = normal_va_at(
        base.SET, EDGE_L1_INDEX, EDGE_L2_INDEX)
    next_va = normal_va_at(NEXT_SET, base.L1_INDEX, 13)
    edge_pte_addr = EDGE_L2_BASE + EDGE_L2_INDEX * 8
    next_pte_addr = NEXT_L2_BASE + 13 * 8
    base.put_qword(
        image, base.L1_BASE + EDGE_L1_INDEX * 8,
        (EDGE_L2_BASE & 0x0000FFFFFFFF0000) | 1)
    base.put_qword(
        image, NEXT_L1_BASE + base.L1_INDEX * 8,
        (NEXT_L2_BASE & 0x0000FFFFFFFF0000) | 1)

    entries = (
        (edge_va, edge_pte_addr, 0x80100000, 0x80120000,
         0x129B300000000006, 0x129B310000000006),
        (next_va, next_pte_addr, 0x80110000, 0x80130000,
         0x129B300000000007, 0x129B310000000007),
    )
    for va, pte_addr, old_pa, new_pa, old_value, new_value in entries:
        base.put_qword(
            image, pte_addr,
            base.normal_pte(old_pa, [3], base.PERM_R))
        base.put_qword(image, old_pa + (va & 0xFFFF), old_value)
        base.put_qword(image, new_pa + (va & 0xFFFF), new_value)
        base.read_va(out, va)
        base.emit_value_check(out, 3, old_value)
        base.write_pte(
            out, pte_addr,
            base.normal_pte(new_pa, [3], base.PERM_R))

    base.cfx_write(
        out, base.CFX_TLB, base.TLB_CONTROL_CG,
        base.TLB_ADDR_START_RC, edge_va & ~0xFFFF)
    base.cfx_write(
        out, base.CFX_TLB, base.TLB_CONTROL_CG,
        base.TLB_ADDR_SIZE_RC, 0xFFFFFFFFFFFFFFFF)
    base.cfx_write(
        out, base.CFX_TLB, base.TLB_CONTROL_CG,
        base.TLB_CONTROL_RC, 2)

    # The oversized range is clamped to set6's 4-TiB end.  It invalidates the
    # last page in set6 but cannot spill into the cached entry in set7.
    base.read_va(out, edge_va)
    base.emit_value_check(out, 3, entries[0][5])
    base.read_va(out, next_va)
    base.emit_value_check(out, 3, entries[1][4])
    base.emit_result(out)
    return bytes(out), bytes(image)


def gen_fault_hit_lru_probe():
    image = base.base_image()
    out = bytearray()
    base.setup(out)
    handler_offset = 0x1800
    base.cfx_write(
        out, base.CFX_TLB, 2, 10, base.ROM_BASE + handler_offset)

    entries = []
    for way in range(17):
        l2_index = 20 + way
        va = base.normal_va(l2_index)
        pa = 0x80100000 + way * 0x10000
        value = 0x129B400000000000 | way
        pte_addr = base.L2_BASE + l2_index * 8
        base.put_qword(
            image, pte_addr,
            base.normal_pte(pa, [3], base.PERM_R))
        base.put_qword(image, pa + (va & 0xFFFF), value)
        entries.append((va, pte_addr, pa, value))

    for entry in entries[:16]:
        base.read_va(out, entry[0])
        base.emit_value_check(out, 3, entry[3])

    # The same cached normal-page entry is addressed through fragment4, which
    # is deliberately absent.  The resulting cfx_tlb fault must still touch
    # way0's true-LRU timestamp.
    fault_va = base.normal_va(20, fragment=4)
    base.load_reg(out, "rb", 3, fault_va)
    base.write_rrii(out, base.OP_LDO, 3, 3, 0)

    # Make a later miss walk succeed without changing the cached entry.  If the
    # fault-hit did not touch LRU, filling way16 evicts way0 and the second
    # fault_va access walks this updated PTE instead of entering the handler.
    base.write_pte(
        out, entries[0][1],
        base.normal_pte(entries[0][2], [3, 4], base.PERM_R))
    base.read_va(out, entries[16][0])
    base.emit_value_check(out, 3, entries[16][3])
    base.load_reg(out, "rd", 29, 0)
    base.read_va(out, fault_va)
    base.emit_value_check(out, 29, FAULT_MARKER)
    base.emit_result(out)

    base.pad_to(out, handler_offset)
    for rc, expected in (
            (2, base.CAUSES["DGPFTRAP"]), (4, fault_va)):
        base.write_crrr(out, base.OP_CFX2RD, base.CFX_TLB, 5, rc, 3)
        base.emit_value_check(out, 3, expected)
    base.load_reg(out, "rd", 29, FAULT_MARKER)
    base.write_ciii(out, base.OP_ESCAPE, base.CFX_TLB, 1)
    return bytes(out), bytes(image)


def main():
    probes = (
        ("low16-alignment", gen_low16_alignment_probe()),
        ("zero-size-noop", gen_zero_size_probe()),
        ("set-end-clamp", gen_set_end_clamp_probe()),
        ("fault-hit-lru", gen_fault_hit_lru_probe()),
    )
    for name, (rom, ram) in probes:
        base.run(name, rom, ram)
    print("PASS: 4 guest-decided KL-129b probes; low16 alignment + "
          "size0 no-op + 4-TiB set-end clamp + fault-hit true-LRU; "
          "QEMU=gem5")


if __name__ == "__main__":
    main()
