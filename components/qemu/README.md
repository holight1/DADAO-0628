# QEMU Component

M1 owns a clean CPU model, decode, scalar execution, and a bare-metal test
machine. KL-125a/KL-127a provide the PTW walk for prebuilt superpage and
two-level page tables, precise walk-fault delivery, and leaf A/D updates;
KL-129a adds the K1 64-set × 16-way true-LRU architectural TLB, explicit
invalidation, seven hit faults, and the bounded cfx_tlb→cfx_ptw→cfx_tlb E1
delegation return. KL-131a adds SEE §5 steps 2-6 (nonmaskable bypass,
inner_cfx_mask/global_cfx_mask/excp_cause_mask arbitration, trap/sync/async
counters) in front of the KL-122a precise-entry carrier, plus the project's
first real instruction-boundary asynchronous interrupt dispatch mechanism.
KL-133a adds cfx_hart_cycle_lo (a new per-instruction-retired counter) and
the cfx_timer counter0 decrement/one-shot/periodic state machine, the first
real (non-test-only) source to drive KL-131a's async dispatch core. Its final
retirement hook runs after successful instruction semantics; precise faults
do not advance cycle/timer, and timer expiry is delivered at the following
instruction boundary. While private timer pending remains asserted, every
boundary re-latches the common TIMER cause independent of enable and masks.
Patch 0034 records the main-acceptance and independent-review repairs,
including exact retirement of successful terminal syscalls.
KL-129b follow-up patch 0035 corrects range invalidation to use only
`addr_start[41:16]` as its 64-KiB-aligned in-set start; zero size remains a
no-op and oversized ranges are overflow-safely clamped to the selected
4-TiB set.
KL-137a patch 0036 adds the K1 test-machine-only synthetic level source
`K1_EXT0`: default-off retired-instruction schedule properties drive
assert/deassert, cfx_uart private source0 pending relatches common UART0, and
delivery reuses KL-131a's generic mask/priority carrier. This is external-
interrupt acceptance evidence only; it does not implement cg32-63 UART
device registers, UART, or PLIC.
The remaining privileged cfx surface, complete SBI/HBI, and Linux user-mode
remain deferred.
