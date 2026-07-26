# QEMU Component

M1 owns a clean CPU model, decode, scalar execution, and a bare-metal test
machine. KL-125a/KL-127a provide the PTW walk for prebuilt superpage and
two-level page tables, precise walk-fault delivery, and leaf A/D updates;
KL-129a adds the K1 64-set × 16-way true-LRU architectural TLB, explicit
invalidation, seven hit faults, and the bounded cfx_tlb→cfx_ptw→cfx_tlb E1
delegation return. The remaining privileged cfx surface, complete SBI/HBI,
and Linux user-mode remain deferred.
