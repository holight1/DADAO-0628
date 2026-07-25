# gcc-c-torture compiler-correctness milestone (2026-07-24 ~ 07-25)

Review reports for the ADR-0012 D5 gcc-c-torture push (ML-019a through
ML-041a), closed 2026-07-25 by explicit user decision (see
`docs/development-roadmap.md`'s "Milestone: gcc-c-torture compiler-
correctness push — closed" section for the final numbers and summary).
Moved here via `git mv` — full history preserved.

- `ML-026a-gcc-c-torture-sweep-2026-07-24.md` — first full 1708-file scan
  and classification (baseline PASS=1328).
- `ML-029a-independent-review-20260724.md` — independent review of the
  frame-offset `imms12` silent-wraparound fix.
- `ML-031a-independent-review-20260724.md` /
  `ML-031a-independent-rereview-20260724.md` — aggregate/struct ABI
  parameter passing, first review (4 blocking findings) and re-review
  (accepted after fixes).
- `ML-032a-embench-functional-suite-2026-07-24.md` /
  `ML-032a-independent-review-20260724.md` — Embench-IoT functional
  corpus integration and its review.
- `ML-035a-gcc-torture-gap-rescan-2026-07-24.md` — refreshed gap
  classification after ML-027a-034a, found the P0 `-O0` negative-polarity
  AND-mask-drop miscompile (fixed by ML-036a).

Task files for this arc (`code-agent/tasks/ML-019a` through `ML-041a`)
remain in place, not archived in this pass.
