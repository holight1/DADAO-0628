# LLVM Component

M1 owns target registration, MC, and basic CodeGen. Use same-version upstream
targets as API/style references; do not copy the legacy DADAO backend.

The patch series (`components/llvm/patches/series`) now carries 66 patches on
top of the pinned upstream baseline; this paragraph predates that growth and
is left as-is rather than rewritten wholesale out of task scope.

KL-153a (`0066-DADAO-promote-i1-loads-to-byte-sized-loads-KL-153a.patch`)
fixes the DADAO backend's `-O0` bool/i1 stack-slot root cause: an i1
load-extension action was never declared, so `_Bool`/i1 stack temporaries
were byte-stored (`stb`) but reloaded with a full 8-byte, non-extending
`ldo` at the same offset -- misaligned and reading past the 1-byte object.
See `code-agent/tasks/KL-153a-llvm-o0-bool-stack-slot-root-fix.md` for the
full root-cause writeup and verification record.
