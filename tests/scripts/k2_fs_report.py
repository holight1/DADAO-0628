# KL-141a K2 report-transport gem5 FullSystem config (reusable for
# KL-142a..145a).  Mirrors tests/dadao/dadao_fs.py's machine description and
# adds the K2 report retrieval path: the guest writes its structured report
# plus a doorbell and then executes architectural halt; this config simulates
# in bounded tick chunks and writes one physical-memory checkpoint only after
# the guest's terminal event (or after the harness limit, which lacks a
# doorbell and therefore fails closed).  The config never interprets report
# bytes.
#
# Usage: gem5.opt --outdir=<dir> tests/scripts/k2_fs_report.py <rom> <ram> \
#          [chunk_ticks] [max_chunks]

import os
import sys

import m5
from m5.objects import *


binary = sys.argv[1]
data_image = sys.argv[2]
chunk_ticks = int(sys.argv[3]) if len(sys.argv) > 3 else 50000000
max_chunks = int(sys.argv[4]) if len(sys.argv) > 4 else 200

system = DADAOSystem()
system.clk_domain = SrcClockDomain(
    clock="1GHz", voltage_domain=VoltageDomain())
system.mem_mode = "atomic"
backing_ranges = [
    AddrRange(0x00000000, size="16MiB"),
    AddrRange(0x80000000, size="16MiB"),
    AddrRange(0x84000000, size="64KiB"),
    AddrRange(0x94030000, size="64KiB"),
    AddrRange(0x87FEF000, size="12KiB"),
]
ptw_alias_ranges = [
    AddrRange(0x0003000085000000, size="64KiB"),
    AddrRange(0x0004000080600000, size="64KiB"),
]
ptw_alias_backings = [
    AddrRange(0x80200000, size="64KiB"),
    AddrRange(0x80400000, size="64KiB"),
]
system.mem_ranges = backing_ranges + ptw_alias_ranges
system.cpu = DADAOAtomicSimpleCPU()
system.membus = IOXBar()
system.cpu.icache_port = system.membus.cpu_side_ports
system.cpu.dcache_port = system.membus.cpu_side_ports
system.cpu.createInterruptController()
system.mem_ctrls = [
    SimpleMemory(range=memory_range, port=system.membus.mem_side_ports)
    for memory_range in backing_ranges
]
system.ptw_alias = RangeAddrMapper(
    original_ranges=ptw_alias_ranges,
    remapped_ranges=ptw_alias_backings,
    cpu_side_port=system.membus.mem_side_ports,
    mem_side_port=system.membus.cpu_side_ports,
)
system.system_port = system.membus.cpu_side_ports

system.workload = DADAOBareMetal(
    image=binary, load_addr=0x00100000, data_image=data_image,
    data_load_addr=0x80000000)
system.cpu.createThreads()

root = Root(full_system=True, system=system)
m5.instantiate()
cpt_dir = os.path.join(m5.options.outdir, "k2cpt")
os.makedirs(cpt_dir, exist_ok=True)
print("SIM_START", flush=True)
terminal_cause = None
for chunk in range(max_chunks):
    exit_event = m5.simulate(chunk_ticks)
    cause = exit_event.getCause()
    print(f"SIM_CHUNK {chunk}: {cause}", flush=True)
    if "limit reached" not in cause:
        terminal_cause = cause
        break
if terminal_cause != "halt":
    raise RuntimeError(
        f"guest did not terminate via halt (cause={terminal_cause!r})")
m5.checkpoint(cpt_dir)
print("SIM_CHECKPOINT", flush=True)
print("SIM_END_LOOP", flush=True)
