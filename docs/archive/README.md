# docs/archive/

Point-in-time project artifacts (dated snapshots, freeze-time impact analyses,
audit handoff packages) that are no longer the current source of truth but
are kept for project history. Moved here via `git mv` (2026-07-25) — full
history is preserved (`git log --follow <file>` shows the pre-move history).

Current, actively-maintained equivalents:

- Project status/history: `docs/development-roadmap.md`
- Architecture/scope decisions: `docs/adr/`
- Wiki-vs-spec deviations and self-decided ABI/ISA calls: `docs/wiki-deviations.md`
- Open wiki questions: `docs/wiki-questions.md`
- Issue tracking: `docs/issues.yaml` / `docs/issues-archive.yaml`

## Contents

- `architecture-boundaries.md` — 2026-06-28 contract/producer/consumer
  boundary table. Some rows (e.g. "Exception behavior: Deferred from M1")
  are now stale — that work is active under K1 kernel bring-up
  (`docs/adr/0015-kernel-bringup-charter.md`).
- `consistency-coverage-analysis.md` — 2026-06-30 versioned wiki→spec
  coverage audit (v0.2.0).
- `impact-matrix.md` — 2026-06-29 spec-freeze impact matrix
  (`manifests/spec.lock.toml` freeze).
- `progress-2026-07-07.md` — 2026-07-07 development progress snapshot.
- `wiki-team-review.md` — 2026-07-07 wiki-team review handoff package
  (ADR-0009 verification-chain audit export).
