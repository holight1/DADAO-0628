# Greenfield Charter

## Objective

Build a new DADAO LLVM, QEMU, runtime, and Kernel stack whose behavior can be
traced to a frozen specification and independent executable tests.

## Non-Reuse Rule

Legacy DADAO implementation code is not copied, cherry-picked, or used as the
starting branch. It may be inspected to identify failure modes, missing tests,
and useful repository-management patterns.

Current upstream versions provide API and style examples. DADAO semantics come
only from the locked specification and accepted contracts.

## Engineering Rules

1. Implement vertical slices with observable intermediate states.
2. Keep unsupported features explicit and test their rejection.
3. Bind every component baseline to a full Git commit.
4. Keep generated work outside the repository history.
5. Require an interface test whenever two components consume one contract.
6. Do not claim completion from compile-only or text-matching tests.

## Initial Product Boundary

The first milestone is a single-core, MMU-off, freestanding execution path.
It is not a Linux platform, complete ABI, or product-ready toolchain.
