# musl Component

Enabled at musl 1.2.5 (upstream tag `v1.2.5`,
`0784374d561435f7c787a555aeab8ede699ed298`), pinned via
`manifests/components.lock.toml`.

`patches/0001-dadao-add-arch-dadao-compile-time-skeleton-ML-009a.patch`
(ML-009a) adds `arch/dadao/` -- the compile-time skeleton (syscall_arch.h,
reloc.h, bits/*.h, kstat.h) that lets `./configure --target=dadao` and
`clang --target=dadao` recognize `dadao` as a build target. No legacy arch
files were imported (see ML-006a `docs/reviews/musl-recon-2026-07-16.md`
SS1.2 for why the old `~/toolchain/musl/arch/dadao/` ABI numbering cannot be
reused). This does not yet produce a linkable/runnable libc -- crt/pthread
integration, atomic_arch.h, and configure/Makefile wiring are follow-up
work (see the recon doc SS5 phase B task list).
