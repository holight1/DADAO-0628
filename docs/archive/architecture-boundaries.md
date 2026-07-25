# Architecture Boundaries

| Contract | Producer | Consumers | Initial Evidence |
|---|---|---|---|
| Instruction encoding | Locked SPEC/vector generator | LLVM MC, QEMU decode | Independent raw vectors |
| Instruction semantics | Locked SPEC/oracle | QEMU, LLVM runtime tests | State-before/state-after cases |
| Register model | AEE/ABI contract | LLVM CodeGen, QEMU CPU | MIR classes and QEMU state dump |
| Scalar calling convention | ABI contract | LLVM caller/callee | Same-TU and cross-object tests |
| ELF/object ABI | Object ABI ADR | LLVM MC, LLD, loaders | Header, fixup, relocation vectors |
| Exception behavior | SEE contract | QEMU, firmware, Kernel | Deferred from M1 |
| MMU/PTE behavior | SEE contract | QEMU, Kernel | Deferred from M1 |

Component ownership does not replace interface ownership. Changes to a shared
contract require an ADR and tests in every consuming layer.
