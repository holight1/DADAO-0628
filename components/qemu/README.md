# QEMU Component

M1 owns a clean CPU model, decode, scalar execution, and a bare-metal test
machine. KL-125a/KL-127a provide the PTW walk for prebuilt superpage and
two-level page tables, precise walk-fault delivery, and leaf A/D updates.
Architectural TLB caching/delegation, the remaining privileged cfx surface,
SBI/HBI, and Linux user-mode remain deferred.
