# Open Specification Issues

These issues do not block the M1 foundation because M1 excludes their behavior.
They block later milestones and must not be guessed in implementation code.

| Area | Open issue | Blocks |
|---|---|---|
| TLB fault return | Successful repair currently appears to skip instead of retry the faulting instruction | System QEMU, Kernel |
| PTW SBI ABI | PTE/PTHI/PAHI register-bank classification is inconsistent with scalar ABI | SBI, Kernel |
| VA2PA result | Signed error encoding conflicts with full 64-bit physical addresses | SBI, MMU tools |
| Varargs | Save area, overflow area, aggregate values, and incoming-SP base need one layout | Complete ABI, libc |
| Cross-cfx escape | Previous cfx state and nested return policy are not fully specified | Exception nesting |
| Multiple returns | Mixed RD/RB/RF ordering is ambiguous | Advanced CodeGen |
| ELF/object ABI | Machine ID, flags, relocations, and formulas need a frozen table | LLD, cross-object execution |
