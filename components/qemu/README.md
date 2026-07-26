# QEMU Component

M1 owns a clean CPU model, decode, scalar execution, and a bare-metal test
machine. KL-125a adds the successful PTW walk for prebuilt superpage and
two-level page tables; PTW faults/A-D updates, architectural TLB caching,
the remaining privileged cfx surface, SBI/HBI, and Linux user-mode remain
deferred.
