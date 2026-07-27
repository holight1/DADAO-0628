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
The remaining privileged cfx surface, complete SBI/HBI, and Linux user-mode
remain deferred.
