# Definition of Done

A foundation feature is complete only when:

1. Its specification clause is named and in the locked scope.
2. Independent positive, boundary, and invalid vectors exist.
3. LLVM MC and QEMU agree with those vectors independently.
4. LLVM CodeGen, when applicable, reaches the expected MachineInstr form.
5. The emitted bytes execute correctly in QEMU.
6. Unsupported adjacent behavior fails explicitly.
7. The repository can reproduce the result from clean source commits.

Compilation success, an assembler round trip, or a QEMU-only test is not
sufficient evidence by itself.
